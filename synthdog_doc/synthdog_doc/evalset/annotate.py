"""Real-document eval set, step 6: three-model page annotation into OmniDocBench format.

Design (CCG round 2, docs/ccg_phase2_synthesis.md on the phase2 branch):
  * Geometry never comes from a language model: regions are PP-DocLayoutV3 proposals (layout_detect.py) plus text-layer
    blocks the detector missed; line boxes come from the PDF text layer.
  * Text comes from the PDF text layer when the annotators confirm it matches the printed page; otherwise (scans,
    broken ToUnicode maps) from the annotators' transcriptions.
  * Three annotators -- Gemini-4-Argon (not one of the benchmarked models), GPT-6-Astra and Claude Opus 5.5, strongest
    effort -- each see the page twice (clean, and with numbered region marks) plus the region list, and independently
    return per-region category / text check / transcription / LaTeX / table HTML and the reading order. They never
    see each other's answers.
  * Consensus: majority category (detector label breaks ties), text-layer text if >= 2 annotators confirm it, else the
    medoid transcription; medoid LaTeX / HTML; reading order by mean rank (Borda). Every annotator's raw answer is
    kept so leave-one-out ground truth can be rebuilt when that annotator is itself being evaluated.

  python3 -m synthdog_doc.evalset.annotate --pages /data/synthdog-doc/evalset/pages \
      --pdfs /data/synthdog-doc/evalset/pdfs --workers 12

Outputs under <pages>/: marks/<page_id>.jpg, raw/<annotator>/<page_id>.json, gt/<page_id>.json (OmniDocBench page),
agreement.jsonl (per-page agreement statistics), omnidocbench_gt.json (all pages).
"""
import argparse
import collections
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from synthdog_doc import llm  # noqa: E402

DET2CAT = {"abstract": "text_block", "algorithm": "text_block", "aside_text": "text_block", "chart": "figure",
           "content": "text_block", "display_formula": "equation_isolated", "doc_title": "title",
           "figure_title": "figure_caption", "footer": "footer", "footnote": "page_footnote",
           "formula_number": "equation_caption", "header": "header", "image": "figure", "inline_formula": None,
           "number": "page_number", "paragraph_title": "title", "reference": "title",
           "reference_content": "reference", "seal": "abandon", "table": "table", "text": "text_block",
           "vision_footnote": "figure_footnote"}
CATS = ["title", "text_block", "reference", "figure", "figure_caption", "figure_footnote", "table", "table_caption",
        "table_footnote", "equation_isolated", "equation_caption", "header", "footer", "page_number", "page_footnote",
        "abandon"]
TEXT_CATS = {"title", "text_block", "reference", "figure_caption", "figure_footnote", "table_caption",
             "table_footnote", "equation_caption", "header", "footer", "page_number", "page_footnote"}
NON_ORDER = {"header", "footer", "page_number", "abandon", "figure"}
ODB_SOURCE = {"ppt": "PPT2PDF", "exam": "exam_paper", "paper_single": "academic_literature",
              "paper_double": "academic_literature", "newspaper": "newspaper", "magazine": "magazine",
              "book": "book", "textbook": "colorful_textbook", "report": "research_report"}
LNAME = {"hi": "Hindi", "es": "Spanish", "ar": "Arabic", "fr": "French", "bn": "Bengali", "pt": "Portuguese",
         "id": "Indonesian", "ur": "Urdu", "ru": "Russian", "de": "German", "en": "English",
         "zh-Hans": "Simplified Chinese", "zh-Hant": "Traditional Chinese", "ja": "Japanese", "ko": "Korean",
         "vi": "Vietnamese", "th": "Thai", "tr": "Turkish", "fa": "Persian", "it": "Italian", "pl": "Polish",
         "nl": "Dutch"}
RTL = {"ar", "ur", "fa"}
ANNOTATORS = {   # name -> (model id, key, effort)
    "gemini": (None, "mid", "high"),
    "astra": ("gpt-6-astra", "main", "max"),
    "opus": ("claude-opus-5-5-pretrain", "main", "max"),
}

PROMPT = """You are an expert annotator building a ground-truth benchmark for document parsing (OmniDocBench format).
Language of the page: {lname}. Image 1 is the clean page; image 2 is the same page with numbered region boxes.
The regions below were proposed by a layout detector; "tl" is the text extracted from the PDF text layer for that
region (it can be wrong: broken font encodings, wrong character order, missing diacritics) or empty for scans.

Regions:
{regions}

For EVERY region return an object with:
- "id": the region number
- "category": one of {cats}, or "drop" if the box is spurious / duplicates another box.
  Use header / footer / page_number for running heads, running feet and folios; figure for photos, charts and
  diagrams; equation_isolated for display formulas; equation_caption for formula numbers like (3).
- "text_ok": true if "tl" matches the printed text exactly (ignore line-break whitespace), else false
- "text": only if text_ok is false (or tl is empty) and the category holds text: the exact printed text, in reading
  order, in the original script, no translation, keep the digits as printed; otherwise ""
- "latex": for equation_isolated only: the formula in LaTeX (no $$ delimiters); otherwise ""
- "html": for table only: the full table as HTML (<table>, <tr>, <td>/<th>, rowspan / colspan), cell text exactly as
  printed; otherwise ""
Then "order": the ids of all content regions (everything except header, footer, page_number, abandon, figure and
dropped regions) in natural reading order{rtl_note}.
Then "missed": text visible on the page that no region covers, as [{{"near_id": n, "category": "...", "text": "..."}}]
(empty list if none).
Return ONLY JSON: {{"regions": [...], "order": [...], "missed": [...]}}"""

_lock = threading.Lock()


def norm_box(b, w, h):
    return [round(1000 * b[0] / w), round(1000 * b[1] / h), round(1000 * b[2] / w), round(1000 * b[3] / h)]


def text_layer(pdf, page_index, scale):
    import fitz  # noqa: PLC0415
    doc = fitz.open(pdf)
    words = doc[page_index].get_text("words")     # x0, y0, x1, y1, word, block, line, word_no
    return [(w[0] * scale, w[1] * scale, w[2] * scale, w[3] * scale, w[4], w[5], w[6], w[7]) for w in words]


def build_regions(m, layout, words):
    regs = []
    for b in sorted(layout, key=lambda b: (b["box"][1], b["box"][0])):
        cat = DET2CAT.get(b["label"], "text_block")
        if cat is None:
            continue
        regs.append({"id": len(regs) + 1, "det": b["label"], "cat0": cat, "box": b["box"], "words": []})
    unassigned = []
    for w in words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        best = None
        for r in regs:
            x0, y0, x1, y1 = r["box"]
            if x0 - 2 <= cx <= x1 + 2 and y0 - 2 <= cy <= y1 + 2:
                area = (x1 - x0) * (y1 - y0)
                if best is None or area < best[0]:
                    best = (area, r)
        if best:
            best[1]["words"].append(w)
        else:
            unassigned.append(w)
    # text-layer blocks the detector missed become extra text regions
    blocks = collections.defaultdict(list)
    for w in unassigned:
        blocks[w[5]].append(w)
    for ws in blocks.values():
        if sum(len(w[4]) for w in ws) < 8:
            continue
        box = [min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws)]
        regs.append({"id": len(regs) + 1, "det": "text_layer_block", "cat0": "text_block", "box": box, "words": ws})
    for r in regs:
        ws = sorted(r["words"], key=lambda w: (w[5], w[6], w[7]))
        lines = collections.OrderedDict()
        for w in ws:
            lines.setdefault((w[5], w[6]), []).append(w)
        r["lines"] = [{"poly": [min(x[0] for x in lw), min(x[1] for x in lw), max(x[2] for x in lw),
                                max(x[3] for x in lw)], "text": " ".join(x[4] for x in lw)} for lw in lines.values()]
        r["tl"] = " ".join(l["text"] for l in r["lines"]).strip()
    return regs


def draw_marks(img_path, regs, out):
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415
    im = Image.open(img_path).convert("RGB")
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/data/synthdog-doc/fonts/gf/ofl/notosans/NotoSans[wdth,wght].ttf",
                                  max(14, im.width // 70))
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    for r in regs:
        x0, y0, x1, y1 = r["box"]
        d.rectangle([x0, y0, x1, y1], outline=(220, 30, 30), width=max(2, im.width // 600))
        tag = str(r["id"])
        tw = d.textlength(tag, font=font)
        d.rectangle([x0, y0 - font.size - 4, x0 + tw + 8, y0], fill=(220, 30, 30))
        d.text((x0 + 4, y0 - font.size - 3), tag, fill="white", font=font)
    im.save(out, quality=88)


def ask(name, m, regs, img, marks):
    model, key, effort = ANNOTATORS[name]
    if model is None:
        model = llm.gemini_model_for_key(key)
    w, h = m["width"], m["height"]
    rl = [{"id": r["id"], "det": r["det"], "box": norm_box(r["box"], w, h),
           "tl": (r["tl"][:700] + " …") if len(r["tl"]) > 700 else r["tl"]} for r in regs]
    prompt = PROMPT.format(lname=LNAME[m["lang"]], regions=json.dumps(rl, ensure_ascii=False), cats=", ".join(CATS),
                           rtl_note=(" (this script is written right-to-left: on multi-column pages the RIGHT "
                                     "column comes first)" if m["lang"] in RTL else ""))
    t0 = time.time()
    try:
        text, meta = llm.call(model, prompt, images=[img, marks], max_tokens=48000, effort=effort, key=key,
                              timeout=1800, retries=6)
    except RuntimeError as e:
        if name == "opus" and ("max_tokens" in str(e) or "empty response" in str(e)):
            text, meta = llm.call(model, prompt, images=[img, marks], max_tokens=48000, effort="xhigh", key=key,
                                  timeout=1800, retries=6)
            meta["effort_fallback"] = "xhigh"
        else:
            raise
    out = llm.extract_json(text)
    return {"answer": out, "model": meta.get("model"), "stop": meta.get("stop"), "usage": meta.get("usage"),
            "sec": round(time.time() - t0, 1), "effort_fallback": meta.get("effort_fallback")}


def ned(a, b):
    from rapidfuzz.distance import Levenshtein  # noqa: PLC0415
    a, b = re.sub(r"\s+", "", a or ""), re.sub(r"\s+", "", b or "")
    if not a and not b:
        return 0.0
    return Levenshtein.distance(a, b) / max(len(a), len(b))


def medoid(cands):
    cands = [c for c in cands if c and c.strip()]
    if not cands:
        return ""
    if len(cands) <= 2:
        return cands[0]
    return min(cands, key=lambda c: sum(ned(c, o) for o in cands))


def consensus(m, regs, answers):
    """answers: {annotator: parsed json}. Returns (ODB page dict, agreement stats)."""
    per = {r["id"]: {} for r in regs}
    orders = {}
    for name, ans in answers.items():
        for it in (ans.get("regions") or []):
            try:
                rid = int(it.get("id"))
            except (TypeError, ValueError):
                continue
            if rid in per:
                per[rid][name] = it
        orders[name] = [int(x) for x in (ans.get("order") or []) if str(x).isdigit() and int(x) in per]
    dets, agree_cat, text_src = [], [], collections.Counter()
    kept = {}
    for r in regs:
        votes = [str(v.get("category", "")).strip() for v in per[r["id"]].values()]
        cnt = collections.Counter(v for v in votes if v in CATS or v == "drop")
        if cnt:
            top, k = cnt.most_common(1)[0]
            cat = top if k >= 2 else (per[r["id"]].get("gemini", {}).get("category") if
                                      per[r["id"]].get("gemini", {}).get("category") in CATS else r["cat0"])
            agree_cat.append(k / max(1, len(votes)))
        else:
            cat = r["cat0"]
        if cat == "drop":
            continue
        rec = {"cat": cat, "box": r["box"], "id": r["id"], "lines": r["lines"]}
        if cat in TEXT_CATS:
            oks = sum(1 for v in per[r["id"]].values() if v.get("text_ok") is True)
            if r["tl"] and oks >= 2:
                rec["text"], src = r["tl"], "text_layer"
            else:
                rec["text"] = medoid([v.get("text", "") for v in per[r["id"]].values()]) or r["tl"]
                src = "annotators" if rec["text"] != r["tl"] else "text_layer_fallback"
                rec["lines"] = [] if src == "annotators" else rec["lines"]
            text_src[src] += 1
        elif cat == "equation_isolated":
            rec["latex"] = medoid([v.get("latex", "") for v in per[r["id"]].values()])
        elif cat == "table":
            rec["html"] = medoid([v.get("html", "") for v in per[r["id"]].values()])
        if cat in TEXT_CATS and not re.search(r"\w", rec.get("text") or ""):
            rec["cat"] = "abandon"                 # answer lines, leader dots: nothing to transcribe
        kept[r["id"]] = rec
    # text no region covers, reported by >= 2 annotators: added with the box of the region it sits next to (flagged
    # approximate; the end-to-end metrics match text, not boxes) so models that read it are not penalised
    missed = [(n, it) for n, a in answers.items() for it in (a.get("missed") or [])
              if isinstance(it, dict) and re.search(r"\w", str(it.get("text") or ""))]
    used, after = [False] * len(missed), {}
    for i, (n, it) in enumerate(missed):
        if used[i]:
            continue
        grp, used[i] = [(n, it)], True
        for j in range(i + 1, len(missed)):
            if not used[j] and missed[j][0] not in {g[0] for g in grp} and ned(it["text"], missed[j][1]["text"]) < 0.3:
                grp.append(missed[j])
                used[j] = True
        try:
            near = int(it.get("near_id"))
        except (TypeError, ValueError):
            near = None
        if len(grp) < 2 or near not in kept:
            continue
        cats = collections.Counter(g[1].get("category") for g in grp if g[1].get("category") in TEXT_CATS)
        rid = 10000 + len(after)
        kept[rid] = {"cat": cats.most_common(1)[0][0] if cats else "text_block", "box": kept[near]["box"], "id": rid,
                     "lines": [], "text": medoid([g[1]["text"] for g in grp]), "approx_box": True}
        after[rid] = near
        text_src["missed_added"] += 1
    # reading order: mean rank over annotators (regions an annotator omitted get its last rank + 1)
    content = [i for i, rec in kept.items() if rec["cat"] not in NON_ORDER]
    ranks = collections.defaultdict(list)
    for name, od in orders.items():
        od = [i for i in od if i in content]
        pos = {i: k for k, i in enumerate(od)}
        for i in content:
            ranks[i].append(pos[after[i]] + 0.5 if i in after and after[i] in pos else pos.get(i, len(od)))
    order = sorted(content, key=lambda i: (sum(ranks[i]) / max(1, len(ranks[i])), kept[i]["box"][1]))
    # pairwise order agreement (Kendall-style) between annotators
    def kendall(a, b):
        common = [i for i in a if i in b]
        pa, pb = {i: k for k, i in enumerate(a)}, {i: k for k, i in enumerate(b)}
        n = conc = 0
        for x in range(len(common)):
            for y in range(x + 1, len(common)):
                i, j = common[x], common[y]
                n += 1
                conc += (pa[i] - pa[j]) * (pb[i] - pb[j]) > 0
        return conc / n if n else 1.0
    names = list(orders)
    ord_agree = [kendall(orders[a], orders[b]) for k, a in enumerate(names) for b in names[k + 1:]]
    rank_of = {i: k for k, i in enumerate(order)}
    for k, (rid, rec) in enumerate(sorted(kept.items(), key=lambda kv: (kv[1]["box"][1], kv[1]["box"][0]))):
        x0, y0, x1, y1 = rec["box"]
        det = {"category_type": rec["cat"], "poly": [x0, y0, x1, y0, x1, y1, x0, y1], "ignore": False,
               "order": rank_of.get(rid), "anno_id": f"box_id_{k}",
               "attribute": {"box_approx": True, "source": "annotators_missed"} if rec.get("approx_box") else {}}
        if "text" in rec:
            det["text"] = rec["text"]
            det["line_with_spans"] = [{"poly": [l["poly"][0], l["poly"][1], l["poly"][2], l["poly"][1], l["poly"][2],
                                                l["poly"][3], l["poly"][0], l["poly"][3]], "text": l["text"]}
                                      for l in rec["lines"]]
        if "latex" in rec:
            det["latex"] = f"$${rec['latex']}$$"
            det["text"] = det["latex"]
        if "html" in rec:
            det["html"] = rec["html"]
        dets.append(det)
    page = {"layout_dets": dets,
            "page_info": {"page_no": 0, "height": m["height"], "width": m["width"],
                          "image_path": f"{m['page_id']}.jpg",
                          "page_attribute": {"data_source": ODB_SOURCE[m["doc_type"]], "language": LNAME[m["lang"]].lower(),
                                             "layout": "double_column" if m["doc_type"] == "paper_double" else "other",
                                             "sdd_doc_type": m["doc_type"], "sdd_lang": m["lang"],
                                             "born_digital": m.get("born_digital")}},
            "extra": {"relation": []}}
    stats = {"page_id": m["page_id"], "n_regions": len(regs), "n_kept": len(kept),
             "cat_agree": round(sum(agree_cat) / len(agree_cat), 3) if agree_cat else None,
             "order_agree": round(sum(ord_agree) / len(ord_agree), 3) if ord_agree else None,
             "text_source": dict(text_src), "annotators": sorted(answers),
             "missed_reports": {n: len(a.get("missed") or []) for n, a in answers.items()}}
    return page, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--annotators", default="gemini,astra,opus")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--workers-per", default="", help="per-annotator concurrency, e.g. gemini=12,astra=16,opus=24")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--consensus-only", action="store_true")
    ap.add_argument("--gt-dir", default=None, help="write consensus here instead of --pages (e.g. leave-one-out GT)")
    a = ap.parse_args()
    root = Path(a.pages)
    man = [json.loads(x) for x in (root / "manifest.jsonl").read_text().splitlines() if x.strip()]
    man = [m for m in man if (root / "layout" / f"{m['page_id']}.json").exists()]
    if a.limit:
        man = man[:a.limit]
    names = a.annotators.split(",")
    for sub in ["marks", "gt", "regions"] + [f"raw/{n}" for n in names]:
        (root / sub).mkdir(parents=True, exist_ok=True)

    def prep(m):
        rp = root / "regions" / f"{m['page_id']}.json"
        if rp.exists():
            return json.loads(rp.read_text())
        layout = json.loads((root / "layout" / f"{m['page_id']}.json").read_text())
        words = text_layer(str(Path(a.pdfs) / m["lang"] / f"{m['doc_id']}.pdf"), m["page_index"], m["dpi"] / 72.0) \
            if m.get("born_digital") else []
        regs = build_regions(m, layout, words)
        draw_marks(root / "images" / m["lang"] / f"{m['page_id']}.jpg", regs, root / "marks" / f"{m['page_id']}.jpg")
        rp.write_text(json.dumps(regs, ensure_ascii=False))
        return regs

    jobs = []
    for m in man:
        for n in names:
            if not (root / "raw" / n / f"{m['page_id']}.json").exists():
                jobs.append((m, n))
    print(f"{len(man)} pages, {len(jobs)} annotator calls pending", flush=True)

    def work(job):
        m, n = job
        regs = prep(m)
        res = ask(n, m, regs, root / "images" / m["lang"] / f"{m['page_id']}.jpg", root / "marks" / f"{m['page_id']}.jpg")
        (root / "raw" / n / f"{m['page_id']}.json").write_text(json.dumps(res, ensure_ascii=False))
        return n

    if not a.consensus_only:
        stats = collections.Counter()
        # one pool per annotator: a slow model (long max-effort thinking) must not starve the others
        per = dict(kv.split("=") for kv in a.workers_per.split(",") if "=" in kv) if a.workers_per else {}
        pools = {n: ThreadPoolExecutor(int(per.get(n, a.workers))) for n in names}
        futs = {}
        for j in sorted(jobs, key=lambda j: j[0]["page_id"]):
            futs[pools[j[1]].submit(work, j)] = j
        if True:
            for k, f in enumerate(as_completed(futs), 1):
                m, n = futs[f]
                try:
                    f.result()
                    stats[n + ":ok"] += 1
                except Exception as e:  # noqa: BLE001
                    stats[n + ":fail"] += 1
                    with _lock, open(root / "annotate_errors.jsonl", "a") as fh:
                        fh.write(json.dumps({"page_id": m["page_id"], "annotator": n, "error": repr(e)[:400]}) + "\n")
                if k % 25 == 0:
                    print(f"  {k}/{len(jobs)} {dict(stats)}", flush=True)
        for pl in pools.values():
            pl.shutdown()
    gdir = Path(a.gt_dir) if a.gt_dir else root
    (gdir / "gt").mkdir(parents=True, exist_ok=True)
    pages, agree = [], []
    for m in man:
        answers = {}
        for n in names:
            p = root / "raw" / n / f"{m['page_id']}.json"
            if p.exists():
                answers[n] = json.loads(p.read_text())["answer"]
        if len(answers) < 2:
            continue
        page, st = consensus(m, prep(m), answers)
        (gdir / "gt" / f"{m['page_id']}.json").write_text(json.dumps(page, ensure_ascii=False))
        pages.append(page)
        agree.append(st)
    (gdir / "omnidocbench_gt.json").write_text(json.dumps(pages, ensure_ascii=False))
    (gdir / "agreement.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in agree))
    print(f"ANNOTATE_DONE pages_with_gt={len(pages)}", flush=True)


if __name__ == "__main__":
    main()

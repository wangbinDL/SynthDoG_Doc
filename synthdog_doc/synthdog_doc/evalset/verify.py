"""Real-document eval set, step 4: visual verification of fetched PDFs, cell selection and page sampling.

For every fetched PDF a 2x2 thumbnail sheet (first page + up to 3 interior pages) goes to a VLM, which confirms the
layout family, column count, language and legibility. Per (language, layout) cell up to --per-cell documents are kept
(at most 2 per web domain), then --pages-per-doc pages are sampled per document and rendered (long side ~2000 px).

  python3 -m synthdog_doc.evalset.verify --pdfs /data/synthdog-doc/evalset/pdfs --out /data/synthdog-doc/evalset/pages

Outputs: <out>/verify.jsonl (VLM verdict per PDF), <out>/images/<lang>/<page_id>.jpg, <out>/manifest.jsonl with
{"page_id","lang","doc_type","doc_id","page_index","n_pages","url","domain","pdf_sha256","width","height","dpi",
 "born_digital","text_chars"}.
"""
import argparse
import collections
import hashlib
import io
import json
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from synthdog_doc import llm  # noqa: E402

TYPES9 = ["ppt", "exam", "paper_single", "paper_double", "newspaper", "magazine", "book", "textbook", "report"]
TRIAGE2TYPE = {"slides": "ppt", "exam": "exam", "academic_paper": "paper", "newspaper": "newspaper",
               "magazine": "magazine", "book": "book", "textbook": "textbook", "report": "report"}
PROMPT = """The image shows up to 4 pages of one PDF document (2x2 grid, first page top-left). Expected language: {lname}.
Classify the document:
- "type": one of slides, exam, academic_paper, newspaper, magazine, book, textbook, report, other
  (slides = presentation deck; exam = test / question paper; academic_paper = scholarly article / thesis;
   report = research, annual, financial, government or NGO report; other = forms, manuals, catalogs, letters, laws...)
- "columns": number of text columns on typical body pages (1, 2 or 3 for 3+)
- "lang_ok": true if the body text is mainly in {lname}
- "legible": true if the pages are readable printed documents (not blank, not mostly photos, not handwriting,
  not garbled characters / boxes)
- "scanned": true if the pages look like scans or photos of paper
Return ONLY JSON: {{"type": "...", "columns": 1, "lang_ok": true, "legible": true, "scanned": false}}"""
LNAME = {"hi": "Hindi", "es": "Spanish", "ar": "Arabic", "fr": "French", "bn": "Bengali", "pt": "Portuguese",
         "id": "Indonesian", "ur": "Urdu", "ru": "Russian", "de": "German", "en": "English",
         "zh-Hans": "Simplified Chinese", "zh-Hant": "Traditional Chinese", "ja": "Japanese", "ko": "Korean",
         "vi": "Vietnamese", "th": "Thai", "tr": "Turkish", "fa": "Persian", "it": "Italian", "pl": "Polish",
         "nl": "Dutch"}
_lock = threading.Lock()


def render_page(doc, i, long_side=2000, max_dpi=220):
    import fitz  # noqa: PLC0415
    pg = doc[i]
    w, h = pg.rect.width, pg.rect.height                     # points (1/72 in)
    dpi = min(max_dpi, long_side * 72.0 / max(w, h))
    pix = pg.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
    return pix, round(dpi, 1)


def sheet(pdf_path, out_jpg, rnd):
    import fitz  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    doc = fitz.open(pdf_path)
    idx = [0] + sorted(rnd.sample(range(1, doc.page_count), min(3, doc.page_count - 1))) if doc.page_count > 1 else [0]
    tiles = []
    for i in idx:
        pix, _ = render_page(doc, i, long_side=700)
        tiles.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
    tw = max(t.width for t in tiles)
    th = max(t.height for t in tiles)
    img = Image.new("RGB", (tw * 2, th * 2), "white")
    for k, t in enumerate(tiles):
        img.paste(t, ((k % 2) * tw, (k // 2) * th))
    img.save(out_jpg, quality=85)
    return doc.page_count


def doc_type9(v, triage_type):
    t = TRIAGE2TYPE.get(v.get("type"))
    if not t:
        return None
    if t == "paper":
        return "paper_double" if int(v.get("columns") or 1) >= 2 else "paper_single"
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="gpt-6.1-sol")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--per-cell", type=int, default=5)
    ap.add_argument("--pages-per-doc", type=int, default=2)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--seed", type=int, default=20261128)
    ap.add_argument("--select-only", action="store_true", help="reuse verify.jsonl, only (re)select and render")
    ap.add_argument("--verify-only", action="store_true", help="verify new PDFs, keep the current selection untouched")
    a = ap.parse_args()
    pdfs, out = Path(a.pdfs), Path(a.out)
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    fetched = {}
    for line in (pdfs / "fetch_log.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r.get("status") == "ok":
            fetched[r["id"]] = r
    done = {}
    vpath = out / "verify.jsonl"
    if vpath.exists():
        for line in vpath.read_text().splitlines():
            r = json.loads(line)
            done[r["id"]] = r
    todo = [r for i, r in fetched.items() if i not in done]
    print(f"{len(fetched)} fetched PDFs, {len(done)} verified, {len(todo)} to verify", flush=True)

    def work(r):
        rnd = random.Random(f"{a.seed}-{r['id']}")
        sp = out / "sheets" / f"{r['id']}.jpg"
        n = sheet(str(pdfs / r["lang"] / f"{r['id']}.pdf"), sp, rnd)
        text, meta = llm.call(a.model, PROMPT.format(lname=LNAME[r["lang"]]), images=[sp], max_tokens=1500,
                              effort=a.effort, timeout=300)
        v = llm.extract_json(text)
        res = {**r, "verdict": v, "n_pages_pdf": n, "usage": meta.get("usage")}
        with _lock, open(vpath, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
        return res

    if not a.select_only:
        with ThreadPoolExecutor(a.workers) as ex:
            futs = [ex.submit(work, r) for r in todo]
            for k, f in enumerate(as_completed(futs), 1):
                try:
                    res = f.result()
                    done[res["id"]] = res
                except Exception as e:  # noqa: BLE001
                    print("FAIL", repr(e)[:200], flush=True)
                if k % 50 == 0:
                    print(f"  verified {k}/{len(todo)}", flush=True)

    if a.verify_only:
        print(f"VERIFY_ONLY_DONE verified={len(done)}", flush=True)
        return
    # ---- select documents per (lang, type9)
    import fitz  # noqa: PLC0415
    cells = collections.defaultdict(list)
    for r in done.values():
        v = r.get("verdict") or {}
        t9 = doc_type9(v, r.get("type"))
        if not t9 or not v.get("lang_ok") or not v.get("legible"):
            continue
        cells[(r["lang"], t9)].append(r)
    rnd = random.Random(a.seed)
    man = []
    (out / "images").mkdir(exist_ok=True)
    cov = {}
    for (lang, t9), rs in sorted(cells.items()):
        rs.sort(key=lambda r: (TRIAGE2TYPE.get(r.get("type")) != t9.split("_")[0], -(r.get("text_chars") or 0)))
        per_dom, chosen = collections.Counter(), []
        for r in rs:
            if per_dom[r["domain"]] >= 2:
                continue
            per_dom[r["domain"]] += 1
            chosen.append(r)
            if len(chosen) >= a.per_cell:
                break
        cov[f"{lang}/{t9}"] = len(chosen)
        for r in chosen:
            doc = fitz.open(str(pdfs / lang / f"{r['id']}.pdf"))
            n = doc.page_count
            text_len = [len(doc[i].get_text("text")) for i in range(n)]
            pool = [i for i in range(n) if text_len[i] >= 200] or list(range(n))
            if t9 in ("book", "textbook", "report", "magazine") and len(pool) > a.pages_per_doc:
                pool = [i for i in pool if i != 0] or pool          # skip covers
            pick = sorted(rnd.sample(pool, min(a.pages_per_doc, len(pool))))
            for i in pick:
                pix, dpi = render_page(doc, i)
                pid = f"{t9}__{lang}__{hashlib.md5(r['id'].encode()).hexdigest()[:12]}__p{i:03d}"
                d = out / "images" / lang
                d.mkdir(parents=True, exist_ok=True)
                pix.save(str(d / f"{pid}.jpg"), jpg_quality=92)
                man.append({"page_id": pid, "lang": lang, "doc_type": t9, "doc_id": r["id"], "page_index": i,
                            "n_pages": n, "url": r["url"], "domain": r["domain"], "pdf_sha256": r.get("sha256"),
                            "width": pix.width, "height": pix.height, "dpi": dpi,
                            "born_digital": not (r.get("verdict") or {}).get("scanned", False) and text_len[i] >= 200,
                            "text_chars": text_len[i]})
    (out / "manifest.jsonl").write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in man))
    (out / "coverage.json").write_text(json.dumps(cov, ensure_ascii=False, indent=1))
    print(f"SELECT_DONE pages={len(man)} cells={len(cov)} full_cells={sum(1 for v in cov.values() if v >= a.per_cell)}",
          flush=True)


if __name__ == "__main__":
    main()

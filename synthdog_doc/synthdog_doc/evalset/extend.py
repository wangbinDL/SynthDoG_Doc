"""Real-document eval set, step 4b: extend an existing selection into cells that have fewer than --per-cell documents.

The v1 selection (verify.py) is frozen while it is being annotated; PDFs fetched later only fill the gaps:

  python3 -m synthdog_doc.evalset.extend --pdfs /data/synthdog-doc/evalset/pdfs --pages /data/synthdog-doc/evalset/pages

For every (language, layout) cell with fewer than --per-cell documents, verified PDFs not yet used are added in the same
preference order as verify.py (VLM type agrees with the text triage, then more text), at most 2 per web domain counting
the documents already in the cell; --pages-per-doc pages per document are sampled and rendered the same way. New pages
are appended to manifest.jsonl (old entries untouched) and listed in manifest_ext_<tag>.jsonl.
"""
import argparse
import collections
import hashlib
import json
import random
from pathlib import Path

from .verify import TRIAGE2TYPE, doc_type9, render_page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--per-cell", type=int, default=5)
    ap.add_argument("--pages-per-doc", type=int, default=2)
    ap.add_argument("--seed", type=int, default=20261128)
    ap.add_argument("--tag", default="v11")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    import fitz  # noqa: PLC0415
    pdfs, root = Path(a.pdfs), Path(a.pages)
    man = [json.loads(x) for x in (root / "manifest.jsonl").read_text().splitlines() if x.strip()]
    have_docs, have_dom = collections.defaultdict(set), collections.defaultdict(collections.Counter)
    used = set()
    for m in man:
        key = (m["lang"], m["doc_type"])
        if m["doc_id"] not in have_docs[key]:
            have_docs[key].add(m["doc_id"])
            have_dom[key][m["domain"]] += 1
        used.add(m["doc_id"])
    verdicts = {}
    for line in (root / "verify.jsonl").read_text().splitlines():
        r = json.loads(line)
        verdicts[r["id"]] = r
    cells = collections.defaultdict(list)
    for r in verdicts.values():
        v = r.get("verdict") or {}
        t9 = doc_type9(v, r.get("type"))
        if not t9 or not v.get("lang_ok") or not v.get("legible") or r["id"] in used:
            continue
        cells[(r["lang"], t9)].append(r)
    new, plan = [], {}
    for key, rs in sorted(cells.items()):
        need = a.per_cell - len(have_docs[key])
        if need <= 0:
            continue
        rs.sort(key=lambda r: (TRIAGE2TYPE.get(r.get("type")) != key[1].split("_")[0], -(r.get("text_chars") or 0)))
        dom = have_dom[key]
        chosen = []
        for r in rs:
            if dom[r["domain"]] >= 2:
                continue
            dom[r["domain"]] += 1
            chosen.append(r)
            if len(chosen) >= need:
                break
        if chosen:
            plan[f"{key[0]}/{key[1]}"] = (len(have_docs[key]), len(have_docs[key]) + len(chosen))
        if a.dry_run:
            continue
        lang, t9 = key
        for r in chosen:
            rnd = random.Random(f"{a.seed}-ext-{r['id']}")
            doc = fitz.open(str(pdfs / lang / f"{r['id']}.pdf"))
            n = doc.page_count
            text_len = [len(doc[i].get_text("text")) for i in range(n)]
            pool = [i for i in range(n) if text_len[i] >= 200] or list(range(n))
            if t9 in ("book", "textbook", "report", "magazine") and len(pool) > a.pages_per_doc:
                pool = [i for i in pool if i != 0] or pool
            for i in sorted(rnd.sample(pool, min(a.pages_per_doc, len(pool)))):
                pix, dpi = render_page(doc, i)
                pid = f"{t9}__{lang}__{hashlib.md5(r['id'].encode()).hexdigest()[:12]}__p{i:03d}"
                d = root / "images" / lang
                d.mkdir(parents=True, exist_ok=True)
                pix.save(str(d / f"{pid}.jpg"), jpg_quality=92)
                new.append({"page_id": pid, "lang": lang, "doc_type": t9, "doc_id": r["id"], "page_index": i,
                            "n_pages": n, "url": r["url"], "domain": r["domain"], "pdf_sha256": r.get("sha256"),
                            "width": pix.width, "height": pix.height, "dpi": dpi,
                            "born_digital": not (r.get("verdict") or {}).get("scanned", False) and text_len[i] >= 200,
                            "text_chars": text_len[i], "added": a.tag})
    full_before = sum(1 for k in have_docs if len(have_docs[k]) >= a.per_cell)
    full_after = full_before + sum(1 for b, e in plan.values() if b < a.per_cell <= e)
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    print(f"cells extended={len(plan)} full cells {full_before} -> {full_after}", flush=True)
    if a.dry_run or not new:
        print(f"EXTEND_DONE dry_run={a.dry_run} new_pages={len(new)}", flush=True)
        return
    tmp = root / "manifest.jsonl.tmp"
    tmp.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in man + new))
    tmp.rename(root / "manifest.jsonl")
    (root / f"manifest_ext_{a.tag}.jsonl").write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in new))
    print(f"EXTEND_DONE new_pages={len(new)}", flush=True)


if __name__ == "__main__":
    main()

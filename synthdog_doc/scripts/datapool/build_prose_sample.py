"""Prose sample from the FinePDFs pool for page synthesis (book / report / magazine body text).

FinePDFs page text keeps the PDF's line structure (and docling's markdown marks). For each language this keeps
documents with >= 3 usable pages and rebuilds paragraphs: blank-line splits, de-hyphenated line joins, table rows /
digit-heavy lines / short fragments dropped, markdown headings kept as section headings. The output is small enough
to load in every renderer process:

  python3 build_prose_sample.py --pool /mnt/wangbin02-jfs/processed/synthdog_doc/datapool/v1 --max-docs 4000

writes <pool>/<lang>/prose_sample.jsonl: {"doc_id","url","title","sections":[{"heading","paras":[...]}]}
"""
import argparse
import json
import random
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pyarrow.parquet as pq

CJK = {"zh-Hans", "zh-Hant", "ja", "th"}
_TABLEISH = re.compile(r"\|.*\||^\s*[-=_.·•]{5,}\s*$")
_HEAD = re.compile(r"^\s{0,3}#{1,4}\s+(.{2,120})$")
_LIST = re.compile(r"^\s*(?:[-•*·]|\d{1,3}[.)])\s+")


def paragraphs(text, cjk):
    out, heads = [], []
    for block in re.split(r"\n\s*\n", text):
        lines = [l.rstrip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        m = _HEAD.match(lines[0])
        if m and len(lines) == 1:
            out.append(("H", m.group(1).strip()))
            continue
        keep = []
        for l in lines:
            if _TABLEISH.search(l):
                keep = []
                break
            digits = sum(ch.isdigit() for ch in l)
            if digits > 0.3 * max(1, len(l)):
                continue
            keep.append(_LIST.sub("", l).strip())
        if not keep:
            continue
        para = ""
        for l in keep:
            if para.endswith("-") and not cjk:
                para = para[:-1] + l
            elif cjk:
                para += l
            else:
                para = (para + " " + l).strip()
        para = re.sub(r"\s+", " ", para).strip()
        if len(para) >= (60 if cjk else 120) and not para.lower().startswith(("figure", "table", "fig.")):
            out.append(("P", para))
    return out


def one(lang, pool, max_docs, seed):
    path = Path(pool) / lang / "finepdfs_pages.parquet"
    if not path.exists():
        return lang, 0
    cjk = lang in CJK
    pf = pq.ParquetFile(str(path))
    rnd = random.Random(f"{seed}-{lang}")
    groups = list(range(pf.num_row_groups))
    rnd.shuffle(groups)
    docs, out = {}, []
    for g in groups:
        for r in pf.read_row_group(g, columns=["doc_id", "page", "text", "url"]).to_pylist():
            docs.setdefault(r["doc_id"], {"url": r["url"], "pages": []})["pages"].append((r["page"], r["text"]))
        if len(docs) > max_docs * 6:
            break
    ids = [d for d, v in docs.items() if len(v["pages"]) >= 3]
    rnd.shuffle(ids)
    for d in ids:
        v = docs[d]
        items = []
        for _, t in sorted(v["pages"])[1:]:          # skip the first page (covers, title pages)
            items += paragraphs(t, cjk)
        paras = [x for k, x in items if k == "P"]
        if len(paras) < 4 or sum(len(p) for p in paras) < (1500 if cjk else 3000):
            continue
        sections, cur = [], {"heading": "", "paras": []}
        for k, x in items:
            if k == "H":
                if cur["paras"]:
                    sections.append(cur)
                cur = {"heading": x, "paras": []}
            else:
                cur["paras"].append(x)
        if cur["paras"]:
            sections.append(cur)
        title = next((s["heading"] for s in sections if s["heading"]), "")
        out.append({"doc_id": d, "url": v["url"], "title": title, "sections": sections})
        if len(out) >= max_docs:
            break
    with open(Path(pool) / lang / "prose_sample.jsonl", "w", encoding="utf-8") as fh:
        for o in out:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return lang, len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--max-docs", type=int, default=4000)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20261128)
    a = ap.parse_args()
    langs = sorted(p.name for p in Path(a.pool).iterdir() if p.is_dir())
    with ProcessPoolExecutor(a.workers) as ex:
        futs = [ex.submit(one, lg, a.pool, a.max_docs, a.seed) for lg in langs]
        for f in as_completed(futs):
            print(*f.result(), flush=True)
    print("PROSE_DONE", flush=True)


if __name__ == "__main__":
    main()

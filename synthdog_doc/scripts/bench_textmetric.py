"""Supplementary multilingual text metric for page -> Markdown predictions.

OmniDocBench's text normaliser keeps only `\\w` and CJK characters, which silently deletes combining marks
(Devanagari / Bengali vowel signs, Arabic harakat, Thai vowels and tone marks). For non-Latin scripts its text edit
distance therefore ignores a whole class of recognition errors. This script reports, per page and aggregated by
language / doc type / imaging branch:

  ned_strict : normalised edit distance on NFC text keeping letters, combining marks and digits (punctuation,
               symbols and whitespace removed)
  ned_odb    : the same pages with the OmniDocBench-style normaliser (marks dropped), for comparison

Page text, both sides, is the body text in reading order: GT blocks except header / footer / page number / abandon /
figure / table / display formula; predictions with tables, display and inline formulas and Markdown markup stripped.
It is order-sensitive (a page-level CER), unlike ODB's block-matched text score.

  python3 scripts/bench_textmetric.py --gt <omnidocbench_gt.json> --pred name=<md dir> [--pred ...] --out metric.json
"""
import argparse
import collections
import json
import re
import unicodedata
from pathlib import Path

from rapidfuzz.distance import Levenshtein

SKIP = {"header", "footer", "page_number", "abandon", "figure", "table", "equation_isolated"}
_TABLE = re.compile(r"<table.*?</table>", re.S | re.I)
_DISPLAY = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]", re.S)
_INLINE = re.compile(r"\$[^$\n]+\$|\\\(.*?\\\)")
_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_TAG = re.compile(r"<[^>]+>")
_ODB = re.compile(r"[^\w一-鿿]")


def strict_norm(s):
    s = unicodedata.normalize("NFC", s)
    return "".join(c for c in s if unicodedata.category(c)[0] in "LMN")


def odb_norm(s):
    return _ODB.sub("", re.sub(r"\s+", "", s))


def gt_text(page):
    blocks = [b for b in page["layout_dets"] if b.get("category_type") not in SKIP and not b.get("ignore")]
    blocks.sort(key=lambda b: (b.get("order") is None, b.get("order") or 0))
    return _INLINE.sub("", "\n".join(b.get("text") or "" for b in blocks))


def pred_text(md):
    md = _TABLE.sub("", md)
    md = _DISPLAY.sub("", md)
    md = _INLINE.sub("", md)
    md = _IMG.sub("", md)
    md = _TAG.sub("", md)
    return md


def ned(a, b):
    if not a and not b:
        return 0.0
    return Levenshtein.distance(a, b) / max(len(a), len(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True)
    ap.add_argument("--pred", action="append", required=True, help="name=dir of <image stem>.md files")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pages = json.loads(Path(a.gt).read_text())
    res = {}
    for spec in a.pred:
        name, d = spec.split("=", 1)
        rows = []
        for p in pages:
            stem = Path(p["page_info"]["image_path"]).stem
            g = gt_text(p)
            if not strict_norm(g):
                continue
            f = Path(d) / f"{stem}.md"
            pr = pred_text(f.read_text(encoding="utf-8")) if f.exists() else ""
            attr = p["page_info"].get("page_attribute", {})
            rows.append({"page": stem, "lang": attr.get("sdd_lang") or attr.get("language"),
                         "doc_type": attr.get("sdd_doc_type") or attr.get("data_source"),
                         "branch": attr.get("sdd_branch", ""), "missing": not f.exists(),
                         "ned_strict": round(ned(strict_norm(g), strict_norm(pr)), 4),
                         "ned_odb": round(ned(odb_norm(g), odb_norm(pr)), 4)})
        agg = {}
        for key in ("all", "lang", "doc_type", "branch"):
            groups = collections.defaultdict(list)
            for r in rows:
                groups["all" if key == "all" else r[key]].append(r)
            agg[key] = {k: {"n": len(v), "ned_strict": round(sum(r["ned_strict"] for r in v) / len(v), 4),
                            "ned_odb": round(sum(r["ned_odb"] for r in v) / len(v), 4)} for k, v in sorted(groups.items())}
        res[name] = {"agg": agg, "pages": rows}
        print(name, json.dumps(agg["all"]["all"]))
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

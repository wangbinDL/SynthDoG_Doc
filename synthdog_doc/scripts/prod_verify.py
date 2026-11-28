"""Acceptance check of a parquet production run (generate.py --format parquet) + stage timing summary.

  python3 scripts/prod_verify.py --root /mnt/wangbin02-jfs/processed/synthdog_doc/prod200k --groups g1,g2,g3,g4 \
      --n 1111 --version 7 --out /data/synthdog-doc/portal_src/prod200k_verify.json

Per group: rows vs the expected (type x lang x index) key set (missing / unexpected / duplicate names), a random
sample read back in full (JPEG decodes at the recorded size, OmniDocBench JSON parses with blocks, Markdown not
empty), imaging-branch mix, shard sizes, and per-stage page timings from _gen_log.jsonl (the first page of each
process carries the browser start-up in "open"; that stage is summarised separately).
"""
import argparse
import collections
import io
import json
import random
import statistics
from pathlib import Path

import pyarrow.parquet as pq

NO_TEXT = {"abandon", "figure", "header", "footer", "page_number"}
TYPES = ["ppt", "exam", "paper_single", "paper_double", "newspaper", "magazine", "book", "textbook", "report"]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def check_group(gdir, n, version, sample, rnd):
    from PIL import Image  # noqa: PLC0415
    shards = sorted((gdir / "shards").glob("*.parquet"))
    names, langs, branches, rows_of = collections.Counter(), collections.Counter(), collections.Counter(), []
    empty_md, size = collections.Counter(), 0
    for sp in shards:
        size += sp.stat().st_size
        t = pq.read_table(sp, columns=["name", "lang", "doc_type", "branch", "markdown", "meta"]).to_pylist()
        for k, r in enumerate(t):
            names[r["name"]] += 1
            langs[r["lang"]] += 1
            branches[r["branch"]] += 1
            rows_of.append((sp, k))
            if not (r["markdown"] or "").strip():
                empty_md[f'{r["doc_type"]}/{json.loads(r["meta"]).get("page_role") or "-"}'] += 1
    expected = {f"{t}__{lg}__v{version}__{i:04d}" for lg in langs for t in TYPES for i in range(n)}
    got = set(names)
    bad = []
    for sp, k in rnd.sample(rows_of, min(sample, len(rows_of))):
        r = pq.read_table(sp).slice(k, 1).to_pylist()[0]
        try:
            im = Image.open(io.BytesIO(r["image"]))
            im.load()
            assert im.size == (r["width"], r["height"]), f"size {im.size} != {(r['width'], r['height'])}"
            odb = json.loads(r["odb"])
            assert odb["layout_dets"], "no layout_dets"
            # empty Markdown is right only when nothing on the page is transcribed (full-page ads are "abandon")
            assert (r["markdown"] or "").strip() or all(b["category_type"] in NO_TEXT for b in odb["layout_dets"]), \
                "empty markdown"
            json.loads(r["meta"])
        except Exception as e:  # noqa: BLE001
            bad.append({"name": r.get("name"), "error": repr(e)[:200]})
    return {"shards": len(shards), "bytes": size, "rows": sum(names.values()), "unique": len(got),
            "duplicates": sum(v - 1 for v in names.values() if v > 1), "expected": len(expected),
            "missing": len(expected - got), "unexpected": len(got - expected),
            "missing_examples": sorted(expected - got)[:5], "langs": dict(langs), "branches": dict(branches),
            "empty_markdown": dict(empty_md), "sample_read": min(sample, len(rows_of)), "sample_bad": bad}


def timings(gdir):
    stages, first_open, per_lang = collections.defaultdict(list), [], collections.defaultdict(list)
    for line in open(gdir / "_gen_log.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r.get("error") or r.get("skipped") or not r.get("timing"):
            continue
        tm = r["timing"]
        (first_open if tm.get("open", 0) > 2 else stages["open"]).append(tm.get("open", 0))
        for k, v in tm.items():
            if k != "open":
                stages[k].append(v)
        per_lang[r["name"].split("__")[1]].append(r.get("sec") or 0)
    return {"stages": {k: {"median": round(statistics.median(v), 3), "p90": round(pct(v, 0.9), 3),
                           "mean": round(statistics.mean(v), 3)} for k, v in stages.items() if v},
            "browser_starts": len(first_open),
            "browser_start_sec_median": round(statistics.median(first_open), 1) if first_open else None,
            "page_sec_median_by_lang": {k: round(statistics.median(v), 2) for k, v in sorted(per_lang.items())}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--groups", required=True)
    ap.add_argument("--n", type=int, default=1111)
    ap.add_argument("--version", type=int, default=7)
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rnd = random.Random(20261128)
    res = {}
    for g in a.groups.split(","):
        gdir = Path(a.root) / g
        res[g] = {**check_group(gdir, a.n, a.version, a.sample, rnd), "timing": timings(gdir)}
        print(g, json.dumps({k: v for k, v in res[g].items() if k not in ("timing", "langs")}, ensure_ascii=False),
              flush=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    ok = all(r["missing"] == 0 and r["duplicates"] == 0 and r["unexpected"] == 0 and not r["sample_bad"]
             for r in res.values())
    print("VERIFY_DONE all_ok=" + str(ok), flush=True)


if __name__ == "__main__":
    main()

"""Merge benchmark runs (disjoint page sets, same models) into one run directory for a single scoring pass.

  python3 scripts/bench_merge_runs.py --runs /data/synthdog-doc/bench/runs/bench900,/data/synthdog-doc/bench/runs/bench1080 \
      --out /data/synthdog-doc/bench/runs/bench1980 --name bench1980

Writes <out>/gt/<name>.json (concatenated OmniDocBench GT), <out>/md/<model>/*.md (copied: the scorer mounts the
prediction parent read-only, so symlinks out of it would not resolve) and <out>/collect_stats.json (counts summed,
mean latency page-weighted). Fails on duplicate page names or models missing from a run.
"""
import argparse
import collections
import json
import shutil
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    a = ap.parse_args()
    runs = [Path(r) for r in a.runs.split(",")]
    out = Path(a.out)
    gt, seen = [], set()
    for r in runs:
        for p in json.loads(next((r / "gt").glob("*.json")).read_text()):
            img = p["page_info"]["image_path"]
            assert img not in seen, f"duplicate page {img}"
            seen.add(img)
            gt.append(p)
    (out / "gt").mkdir(parents=True, exist_ok=True)
    (out / "gt" / f"{a.name}.json").write_text(json.dumps(gt, ensure_ascii=False))
    models = sorted(set.intersection(*[{d.name for d in (r / "md").iterdir() if d.is_dir()} for r in runs]))
    for m in models:
        dst = out / "md" / m
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True)
        n = 0
        for r in runs:
            for f in (r / "md" / m).glob("*.md"):
                shutil.copyfile(f, dst / f.name)
                n += 1
        print(m, n, flush=True)
    stats = {}
    for m in models:
        agg = {"pages": 0, "status": collections.Counter(), "first_attempt": collections.Counter(),
               "empty_after_clean": 0, "usage_total": collections.Counter()}
        sec_w = sec_n = 0
        for r in runs:
            s = json.loads((r / "collect_stats.json").read_text()).get(m) or {}
            agg["pages"] += s.get("pages") or 0
            agg["status"].update(s.get("status") or {})
            agg["first_attempt"].update(s.get("first_attempt") or {})
            agg["empty_after_clean"] += s.get("empty_after_clean") or 0
            agg["usage_total"].update(s.get("usage_total") or {})
            if s.get("sec_mean") is not None:
                sec_w += s["sec_mean"] * (s.get("pages") or 0)
                sec_n += s.get("pages") or 0
        agg = {k: dict(v) if isinstance(v, collections.Counter) else v for k, v in agg.items()}
        agg["sec_mean"] = round(sec_w / sec_n, 1) if sec_n else None
        stats[m] = agg
    (out / "collect_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    print(f"MERGE_DONE pages={len(gt)} models={len(models)}", flush=True)


if __name__ == "__main__":
    main()

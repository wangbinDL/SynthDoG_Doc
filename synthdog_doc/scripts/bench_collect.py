"""Collect raw page predictions of all benchmark models into per-page Markdown directories + run statistics.

  python3 scripts/bench_collect.py --run /data/synthdog-doc/bench/runs/bench900 --manifest <bench>/manifest.jsonl

Inputs under <run>/raw/: <model>.jsonl from bench_api.py (gateway VLMs), docparse vllm_infer (Qwen) or
mineru_infer.py (MinerU); PaddleOCR-VL's two-stage client writes <run>/md/PaddleOCR-VL-1.6/ directly.
Per page the best row wins (ok > truncated > other; later rows win ties). Reasoning blocks (<think>...</think>) and a
fence wrapping the whole answer are stripped. Missing / failed pages get an empty .md (they score 0, never dropped).
Writes <run>/md/<model>/<page>.md and <run>/collect_stats.json (status counts, coverage, tokens, latency).
"""
import argparse
import collections
import json
import re
from pathlib import Path

RANK = {"ok": 3, "truncated": 2}
_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*?)\n```\s*$", re.S)


def strip_think(t):
    if "</think>" in t:
        return t.rsplit("</think>", 1)[1]
    if "<think>" in t:
        return ""                      # reasoning never closed: no answer
    return t


def clean(t):
    t = strip_think(t or "")
    m = _FENCE.match(t)
    return (m.group(1) if m else t).strip()


def response_of(r):
    for k in ("response", "raw", "text", "output", "prediction", "generated_text"):
        if isinstance(r.get(k), str):
            return r[k]
    for k in ("outputs", "choices"):
        v = r.get(k)
        if isinstance(v, list) and v:
            x = v[0]
            return x.get("text") or (x.get("message") or {}).get("content") or ""
    return ""


def page_of(r):
    for k in ("record_id", "image_path", "image", "page"):
        if r.get(k):
            return Path(str(r[k])).stem
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--manifest", required=True)
    a = ap.parse_args()
    run = Path(a.run)
    pages = [json.loads(x)["name"] for x in Path(a.manifest).read_text().splitlines() if x.strip()]
    stats = {}
    for raw in sorted((run / "raw").glob("*.jsonl")):
        model = raw.stem
        if model.startswith("PaddleOCR-VL"):
            continue                    # its client writes Markdown itself
        best, first = {}, {}
        for line in raw.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            p = page_of(r)
            if not p:
                continue
            st = r.get("status") or ("ok" if response_of(r) else "empty")
            first.setdefault(p, st)            # first-attempt outcome, for refusal / truncation rates
            if p not in best or RANK.get(st, 1) >= RANK.get(best[p][0], 1):
                best[p] = (st, r)
        out = run / "md" / model
        out.mkdir(parents=True, exist_ok=True)
        st_count, usage, secs = collections.Counter(), collections.Counter(), []
        empty_after_clean = 0
        for p in pages:
            st, r = best.get(p, ("missing", {}))
            md = clean(response_of(r)) if st in ("ok", "truncated") else ""
            if st in ("ok", "truncated") and not md:
                empty_after_clean += 1
            (out / f"{p}.md").write_text(md + "\n", encoding="utf-8")
            st_count[st] += 1
            for k, v in (r.get("usage") or {}).items():
                if isinstance(v, (int, float)):
                    usage[k] += v
                elif isinstance(v, dict):
                    for k2, v2 in v.items():
                        if isinstance(v2, (int, float)):
                            usage[f"{k}.{k2}"] += v2
            if r.get("sec"):
                secs.append(r["sec"])
        first_count = collections.Counter(first.get(p, "missing") for p in pages)
        stats[model] = {"pages": len(pages), "status": dict(st_count), "first_attempt": dict(first_count),
                        "empty_after_clean": empty_after_clean,
                        "usage_total": dict(usage), "sec_mean": round(sum(secs) / len(secs), 1) if secs else None}
        print(model, stats[model]["status"], "empty_after_clean", empty_after_clean)
    pmd = run / "md" / "PaddleOCR-VL-1.6"
    if pmd.exists():
        have = {f.stem for f in pmd.glob("*.md")}
        for p in pages:
            if p not in have:
                (pmd / f"{p}.md").write_text("\n", encoding="utf-8")
        stats["PaddleOCR-VL-1.6"] = {"pages": len(pages), "status": {"ok": len(have & set(pages)),
                                                                     "missing": len(set(pages) - have)}}
    (run / "collect_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

"""Merge OmniDocBench scoring runs + supplementary text metric + run statistics into one benchmark report.

  python3 scripts/bench_report.py --run /data/synthdog-doc/bench/runs/bench900 --odb odb_a,odb_b,odb_c \
      --out /data/synthdog-doc/bench/runs/bench900/report.json --md /data/synthdog-doc/bench/runs/bench900/report.md

Per model: overall + element scores (text edit distance, formula CDM, table TEDS / TEDS-S, reading-order edit),
the same broken down by language / document type / imaging branch (overall per bucket uses the ODB formula
((1 - text_edit) * 100 + CDM * 100 + TEDS * 100) / 3 over the bucket's pages), first-attempt failure rates, token
usage and latency (collect_stats.json) and the page-level multilingual text metric (textmetric.json).
"""
import argparse
import json
from pathlib import Path

ORDER = ["MinerU2.5-Pro", "PaddleOCR-VL-1.6", "Qwen3.5-4B", "Qwen3.8-27B", "gpt-6.1-sol", "gpt-6-astra",
         "claude-opus-5-5-pretrain", "gt-oracle"]
DISPLAY = {"MinerU2.5-Pro": "MinerU2.5-Pro", "PaddleOCR-VL-1.6": "PaddleOCR-VL-1.6", "Qwen3.5-4B": "Qwen3.5-4B",
           "Qwen3.8-27B": "Qwen3.8-27B", "gpt-6.1-sol": "GPT-6.1-Sol", "gpt-6-astra": "GPT-6-Astra",
           "claude-opus-5-5-pretrain": "Claude Opus 5.5", "gt-oracle": "GT（自检）"}


def overall(te, cdm, teds):
    if te is None or cdm is None or teds is None:
        return None
    return ((1 - te) * 100 + cdm * 100 + teds * 100) / 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--odb", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", default=None)
    a = ap.parse_args()
    run = Path(a.run)
    jobs = {}
    for d in a.odb.split(","):
        s = json.loads((run / d / "summary.json").read_text())
        for j in s["jobs"]:
            jobs[j["name"]] = j
    stats = json.loads((run / "collect_stats.json").read_text()) if (run / "collect_stats.json").exists() else {}
    tm = json.loads((run / "textmetric.json").read_text()) if (run / "textmetric.json").exists() else {}
    rep = {"models": {}}
    for name in [n for n in ORDER if n in jobs] + [n for n in jobs if n not in ORDER]:
        j = jobs[name]
        bpa = j.get("by_page_attribute") or {}
        buckets = {}
        for key in bpa.get("text_edit", {}):
            te = bpa["text_edit"].get(key)
            cdm = (bpa.get("formula_cdm") or {}).get(key)
            teds = (bpa.get("table_teds") or {}).get(key)
            buckets[key] = {"text_edit": te, "formula_cdm": cdm, "table_teds": teds,
                            "table_teds_s": (bpa.get("table_teds_s") or {}).get(key),
                            "reading_order_edit": (bpa.get("reading_order_edit") or {}).get(key),
                            "overall": overall(te, cdm, teds)}
        rep["models"][name] = {
            "display": DISPLAY.get(name, name), "pages": j.get("page_count"), "overall": j.get("overall"),
            "text_edit": j.get("text_edit"), "formula_cdm": j.get("formula_cdm"), "table_teds": j.get("table_teds"),
            "table_teds_s": j.get("table_teds_s"), "reading_order_edit": j.get("reading_order_edit"),
            "healthy": j.get("healthy"), "buckets": buckets, "run": stats.get(name, {}),
            "text_metric": (tm.get(name) or {}).get("agg")}
    Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    if a.md:
        lines = ["| 模型 | Overall | 文本编辑距离↓ | 公式 CDM | 表格 TEDS | TEDS-S | 阅读顺序↓ | 页级字符错误率↓ |",
                 "|---|---|---|---|---|---|---|---|"]
        for name, m in rep["models"].items():
            ned = ((m["text_metric"] or {}).get("all") or {}).get("all", {}).get("ned_strict")
            lines.append(f"| {m['display']} | {m['overall']:.2f} | {m['text_edit']:.3f} | {m['formula_cdm'] * 100:.1f} | "
                         f"{m['table_teds'] * 100:.1f} | {m['table_teds_s'] * 100:.1f} | {m['reading_order_edit']:.3f} | "
                         f"{ned if ned is not None else '—'} |")
        langs = sorted({k.split(': ')[1] for m in rep["models"].values() for k in m["buckets"] if k.startswith("sdd_lang: ")})
        lines += ["", "| 模型 | " + " | ".join(langs) + " |", "|---|" + "---|" * len(langs)]
        for name, m in rep["models"].items():
            cells = []
            for lg in langs:
                o = (m["buckets"].get(f"sdd_lang: {lg}") or {}).get("overall")
                cells.append(f"{o:.1f}" if o is not None else "—")
            lines.append(f"| {m['display']} | " + " | ".join(cells) + " |")
        Path(a.md).write_text("\n".join(lines) + "\n")
        print("\n".join(lines))


if __name__ == "__main__":
    main()

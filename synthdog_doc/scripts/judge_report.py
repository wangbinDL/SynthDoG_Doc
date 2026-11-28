"""Aggregate judge results: fool rate, calibration, rubric scores, diversity, A/B win rate, issue digest.

  python3 scripts/judge_report.py /data/synthdog-doc/judge/r1   -> summary.json + issues.md
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

DIMS = ["layout_realism", "typography", "locale_conventions", "content_coherence", "overall_realism"]


def main(rdir):
    rdir = Path(rdir)
    recs = []
    for line in (rdir / "results.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        if isinstance(d.get("result"), list):   # a few judge outputs came back wrapped in a list
            d["result"] = next((x for x in d["result"] if isinstance(x, dict)), None)
        if "error" in d or not isinstance(d.get("result"), dict) or d["result"].get("parse_error"):
            continue
        recs.append(d)
    # keep the latest record per (task, judge)
    last = {}
    for d in recs:
        last[(d["task_id"], d["judge"])] = d
    recs = list(last.values())
    S = {"by_judge": {}, "by_type": {}, "by_lang": {}, "grid": {}, "pair": {}, "n_records": len(recs)}
    singles = [d for d in recs if d["kind"] == "single"]
    for j in sorted({d["judge"] for d in recs}):
        syn = [d for d in singles if d["judge"] == j and d["truth"] == "synthetic"]
        real = [d for d in singles if d["judge"] == j and d["truth"] == "real"]
        fool = sum(1 for d in syn if d["result"].get("verdict") == "real") / max(1, len(syn))
        rec_real = sum(1 for d in real if d["result"].get("verdict") == "real") / max(1, len(real))
        sc = {k: round(sum((d["result"].get("scores") or {}).get(k, 0) for d in syn) / max(1, len(syn)), 2) for k in DIMS}
        sc_real = {k: round(sum((d["result"].get("scores") or {}).get(k, 0) for d in real) / max(1, len(real)), 2)
                   for k in DIMS}
        S["by_judge"][j] = {"n_syn": len(syn), "n_real": len(real), "fool_rate": round(fool, 3),
                            "real_recall": round(rec_real, 3), "scores_syn": sc, "scores_real": sc_real}
    for key, field in (("by_type", "doc_type"), ("by_lang", "lang")):
        groups = defaultdict(list)
        for d in singles:
            if d["truth"] == "synthetic":
                groups[d[field]].append(d)
        for g, ds in sorted(groups.items()):
            S[key][g] = {"n": len(ds),
                         "fool_rate": round(sum(1 for d in ds if d["result"].get("verdict") == "real") / len(ds), 3),
                         "overall": round(sum((d["result"].get("scores") or {}).get("overall_realism", 0) for d in ds)
                                          / len(ds), 2),
                         "typography": round(sum((d["result"].get("scores") or {}).get("typography", 0) for d in ds)
                                             / len(ds), 2),
                         "locale": round(sum((d["result"].get("scores") or {}).get("locale_conventions", 0) for d in ds)
                                         / len(ds), 2)}
    for d in recs:
        if d["kind"] == "grid":
            r = d["result"]
            S["grid"].setdefault(d["doc_type"], {})[d["judge"]] = {
                "diversity": r.get("diversity_score"), "templates": r.get("estimated_distinct_templates"),
                "realism": r.get("realism_of_set"), "cluster": (r.get("largest_repeated_cluster") or {}).get("size")}
        if d["kind"] == "pair":
            w = d["result"].get("winner")
            st = S["pair"].setdefault(d["judge"], {"new": 0, "old": 0, "tie": 0})
            if w == "tie" or w not in ("A", "B"):
                st["tie"] += 1
            elif w == d["new_is"]:
                st["new"] += 1
            else:
                st["old"] += 1
    for j, st in S["pair"].items():
        n = st["new"] + st["old"] + st["tie"]
        st["new_win_rate"] = round((st["new"] + 0.5 * st["tie"]) / max(1, n), 3)
    (rdir / "summary.json").write_text(json.dumps(S, ensure_ascii=False, indent=1), encoding="utf-8")
    # issue digest per doc type (synthetic pages only)
    lines = [f"# Judge issues — {rdir.name}\n"]
    sev_w = {"blocker": 3, "major": 2, "minor": 1}
    for dt in sorted({d["doc_type"] for d in singles}):
        ds = [d for d in singles if d["doc_type"] == dt and d["truth"] == "synthetic"]
        if not ds:
            continue
        cnt = Counter()
        for d in ds:
            for f in d["result"].get("flaws") or []:
                cnt[f.get("issue_type", "other")] += sev_w.get(f.get("severity"), 1)
        lines.append(f"\n## {dt}  (pages={len(ds)}; weighted issue types: {dict(cnt.most_common())})\n")
        for d in sorted(ds, key=lambda x: (x["lang"], x["judge"])):
            r = d["result"]
            lines.append(f"\n**{d['lang']} / {d['judge']}** verdict={r.get('verdict')}({r.get('confidence')}) "
                         f"overall={(r.get('scores') or {}).get('overall_realism')} — {r.get('summary', '')}")
            for f in (r.get("flaws") or [])[:8]:
                lines.append(f"- [{f.get('severity')}/{f.get('issue_type')}] {f.get('region')}: {f.get('evidence')} "
                             f"→ FIX: {f.get('fix')}")
    for d in recs:
        if d["kind"] == "grid":
            r = d["result"]
            lines.append(f"\n## GRID {d['doc_type']} / {d['judge']}: diversity={r.get('diversity_score')} "
                         f"templates={r.get('estimated_distinct_templates')} cluster={r.get('largest_repeated_cluster')}")
            for m in r.get("repeated_motifs") or []:
                lines.append(f"- motif: {m}")
            for m in r.get("missing_structures") or []:
                lines.append(f"- missing: {m}")
            for m in r.get("top_recommendations") or []:
                lines.append(f"- rec: {m}")
    (rdir / "issues.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: S[k] for k in ("by_judge", "pair")}, ensure_ascii=False, indent=1))
    print("by_type:", json.dumps(S["by_type"], ensure_ascii=False))
    print("grid:", json.dumps(S["grid"], ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])

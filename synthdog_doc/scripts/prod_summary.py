"""Summarise the Top-20 x 10k production run for the portal (portal_src/production.json -> "run200k").

  python3 scripts/prod_summary.py --logs /data/synthdog-doc/logs --verify /data/synthdog-doc/portal_src/prod200k_verify.json \
      --out /data/synthdog-doc/portal_src/production.json

Reads the per-group worker logs (prod200k_g<k>.log: wall clock and CPU of all reaped descendants, page count, output
size) and the acceptance check (prod_verify.py), and merges them into the existing production.json.
"""
import argparse
import json
import re
from pathlib import Path

GROUP_LANGS = {"g1": "hi,es,ar,fr,bn", "g2": "pt,id,ur,ru,de", "g3": "en,zh-Hans,ja,vi,ko", "g4": "zh-Hant,tr,fa,th,it"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="/data/synthdog-doc/logs")
    ap.add_argument("--verify", default="/data/synthdog-doc/portal_src/prod200k_verify.json")
    ap.add_argument("--out", default="/data/synthdog-doc/portal_src/production.json")
    a = ap.parse_args()
    ver = json.loads(Path(a.verify).read_text()) if Path(a.verify).exists() else {}
    groups = []
    for g, langs in GROUP_LANGS.items():
        log = (Path(a.logs) / f"prod200k_{g}.log").read_text()
        m = re.search(r"PROD200K wall=([\d.]+)s cpu_user=(\d+)s cpu_sys=(\d+)s rc=(\d+) \| GEN_DONE ok=(\d+) err=(\d+)", log)
        size = re.search(r"\n([\d.]+)G\t", log)
        wall, cu, cs, rc, ok, err = float(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6])
        v = ver.get(g, {})
        groups.append({"group": g, "langs": langs, "pages": ok, "errors": err, "wall": wall, "cpu": cu + cs,
                       "pages_per_sec": round(ok / wall, 2), "core_sec_per_page": round((cu + cs) / ok, 2),
                       "gb": float(size[1]) if size else None, "shards": v.get("shards"),
                       "verify": {k: v.get(k) for k in ("rows", "unique", "duplicates", "missing", "unexpected",
                                                         "sample_read", "empty_markdown")},
                       "verify_bad": len(v.get("sample_bad") or []), "branches": v.get("branches"),
                       "timing": v.get("timing")})
    P = json.loads(Path(a.out).read_text()) if Path(a.out).exists() else {}
    tot_pages = sum(x["pages"] for x in groups)
    tot_cpu = sum(x["cpu"] for x in groups)
    P["run200k"] = {"groups": groups, "pages": tot_pages, "errors": sum(x["errors"] for x in groups),
                    "cpu_core_hours": round(tot_cpu / 3600, 1), "core_sec_per_page": round(tot_cpu / tot_pages, 2),
                    "gb": round(sum(x["gb"] or 0 for x in groups), 1),
                    "wall_max": max(x["wall"] for x in groups),
                    "workers": "4 × (64 核 / 256 GiB CPU worker，各跑 64 个渲染进程)"}
    Path(a.out).write_text(json.dumps(P, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in P["run200k"].items() if k != "groups"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

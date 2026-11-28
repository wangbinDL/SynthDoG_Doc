"""Stratified benchmark subset of a generated SynthDoG-Doc set (default: 10 pages per doc type x language cell).

Inside each (doc_type, lang) cell the pages are drawn so the imaging branches (digital / scan / photo) keep the
cell's own proportions (largest-remainder rounding), with a fixed seed.

  python3 scripts/sample_bench.py --pages /mnt/wangbin02-jfs/processed/synthdog_doc/sdd-v6/pages \
      --out /mnt/wangbin02-jfs/processed/synthdog_doc/bench900 --per-cell 10 --seed 20261128

Writes <out>/images/<name>.jpg, <out>/gt/<name>.{json,md,meta.json}, <out>/manifest.jsonl and
<out>/omnidocbench_gt.json (OmniDocBench list format; page_info.page_attribute keeps the ODB fields and adds
sdd_doc_type / sdd_lang / sdd_branch).
"""
import argparse
import collections
import json
import random
import shutil
from pathlib import Path


def alloc(counts, n):
    """Largest-remainder allocation of n draws over strata with the given sizes."""
    tot = sum(counts.values())
    raw = {k: n * v / tot for k, v in counts.items()}
    out = {k: min(counts[k], int(raw[k])) for k in counts}
    rest = sorted(counts, key=lambda k: raw[k] - int(raw[k]), reverse=True)
    i = 0
    while sum(out.values()) < min(n, tot):
        k = rest[i % len(rest)]
        if out[k] < counts[k]:
            out[k] += 1
        i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-cell", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20261128)
    a = ap.parse_args()
    src, out = Path(a.pages), Path(a.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "gt").mkdir(parents=True, exist_ok=True)

    cells = collections.defaultdict(lambda: collections.defaultdict(list))
    for mp in sorted(src.glob("*.meta.json")):
        m = json.loads(mp.read_text())
        name = mp.name[:-len(".meta.json")]
        if not (src / f"{name}.jpg").exists() or not (src / f"{name}.json").exists():
            continue
        cells[(m["doc_type"], m["lang"])][(m.get("degrade") or {}).get("branch", "digital")].append((name, m))

    rnd = random.Random(a.seed)
    manifest, odb = [], []
    for (dt, lang) in sorted(cells):
        strata = cells[(dt, lang)]
        take = alloc({b: len(v) for b, v in strata.items()}, a.per_cell)
        for b in sorted(strata):
            for name, m in rnd.sample(strata[b], take[b]):
                shutil.copy2(src / f"{name}.jpg", out / "images" / f"{name}.jpg")
                for ext in ("json", "md", "meta.json"):
                    if (src / f"{name}.{ext}").exists():
                        shutil.copy2(src / f"{name}.{ext}", out / "gt" / f"{name}.{ext}")
                page = json.loads((src / f"{name}.json").read_text())
                info = page.setdefault("page_info", {})
                info["image_path"] = f"{name}.jpg"
                attr = info.setdefault("page_attribute", {})
                attr.update({"sdd_doc_type": dt, "sdd_lang": lang, "sdd_branch": b})   # keep ODB data_source / language
                odb.append(page)
                manifest.append({"name": name, "doc_type": dt, "lang": lang, "branch": b,
                                 "paper": (m.get("page") or {}).get("paper"), "dpi": (m.get("page") or {}).get("dpi")})
    (out / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in manifest))
    (out / "omnidocbench_gt.json").write_text(json.dumps(odb, ensure_ascii=False))
    by = collections.Counter((r["doc_type"], r["lang"]) for r in manifest)
    br = collections.Counter(r["branch"] for r in manifest)
    print(f"cells={len(by)} pages={len(manifest)} min/max per cell={min(by.values())}/{max(by.values())} branches={dict(br)}")


if __name__ == "__main__":
    main()

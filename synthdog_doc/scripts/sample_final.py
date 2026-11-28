"""After the full generation: statistics + a small sample of pages (with box overlays drawn from the exported
ODB JSON) copied to /data for the portal.

  python3 scripts/sample_final.py --pages /mnt/wangbin02-jfs/processed/synthdog_doc/sdd-v4/pages \
      --out /data/synthdog-doc/portal_final_src --per-cell 2 --tag sdd-v4 --commit abc1234 --elapsed "26 min" \
      --worker "rlaunch CPU worker, 64 cores"
"""
import argparse
import collections
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

COLORS = {"title": (220, 40, 40), "text_block": (40, 90, 220), "figure": (30, 160, 60), "figure_caption": (120, 200, 60),
          "table": (230, 160, 20), "table_caption": (240, 200, 60), "equation_isolated": (160, 60, 200),
          "equation_caption": (200, 120, 230), "header": (120, 120, 120), "footer": (120, 120, 120),
          "page_number": (90, 90, 90), "page_footnote": (0, 170, 170), "reference": (0, 120, 160),
          "abandon": (150, 150, 150), "table_footnote": (200, 170, 90), "figure_footnote": (90, 170, 90)}


def overlay(img_path, odb, out):
    im = Image.open(img_path).convert("RGB")
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for b in odb.get("layout_dets", []):
        c = COLORS.get(b.get("category_type"), (200, 0, 200))
        p = b["poly"]
        pts = [(p[i], p[i + 1]) for i in range(0, len(p), 2)]
        d.polygon(pts, outline=c + (255,), fill=c + (38,))
        for ln in b.get("line_with_spans") or []:
            q = ln["poly"]
            d.polygon([(q[i], q[i + 1]) for i in range(0, len(q), 2)], outline=c + (150,))
    Image.alpha_composite(im.convert("RGBA"), lay).convert("RGB").save(out, quality=82)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-cell", type=int, default=2)
    ap.add_argument("--tag", default="")
    ap.add_argument("--commit", default="")
    ap.add_argument("--elapsed", default="")
    ap.add_argument("--worker", default="")
    a = ap.parse_args()
    src, out = Path(a.pages), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    metas = sorted(src.glob("*.meta.json"))
    by_type, by_lang, by_branch, by_role = (collections.Counter() for _ in range(4))
    for mf in metas:
        m = json.loads(mf.read_text())
        by_type[m.get("doc_type")] += 1
        by_lang[m.get("lang")] += 1
        by_branch[(m.get("degrade") or {}).get("branch", "digital")] += 1
        by_role[f'{m.get("doc_type")}:{m.get("page_role")}'] += 1
    errs = 0
    log = src / "_gen_log.jsonl"
    if log.exists():
        last = {}
        for x in log.read_text().splitlines():
            try:
                d = json.loads(x)
            except Exception:  # noqa: BLE001
                continue
            last[d.get("name")] = d
        errs = sum(1 for d in last.values() if d.get("error"))
    picked = []
    for mf in metas:
        name = mf.name[:-len(".meta.json")]
        idx = int(name.rsplit("__", 1)[1])
        if idx < a.per_cell:
            picked.append(name)
    for name in picked:
        for ext in (".jpg", ".json", ".meta.json"):
            shutil.copy2(src / f"{name}{ext}", out / f"{name}{ext}")
        overlay(src / f"{name}.jpg", json.loads((src / f"{name}.json").read_text()), out / f"{name}.overlay.jpg")
    size = subprocess.run(["du", "-sh", str(src)], capture_output=True, text=True).stdout.split("\t")[0]
    ex = json.loads((src / f"{picked[0]}.json").read_text()) if picked else {}
    if ex.get("layout_dets"):
        ex["layout_dets"] = ex["layout_dets"][:3]
        for b in ex["layout_dets"]:
            b["line_with_spans"] = (b.get("line_with_spans") or [])[:2]
            if isinstance(b.get("text"), str) and len(b["text"]) > 160:
                b["text"] = b["text"][:160] + "…"
    stats = {"tag": a.tag, "commit": a.commit, "path": str(src), "n_ok": len(metas), "n_err": errs,
             "per_cell": max(by_type.values()) // 10 if by_type else 0, "size": size, "elapsed": a.elapsed,
             "worker": a.worker, "by_type": dict(by_type), "by_lang": dict(by_lang), "by_branch": dict(by_branch),
             "by_role": dict(by_role), "n_sampled": len(picked),
             "json_example": json.dumps(ex, ensure_ascii=False, indent=1)[:2600]}
    lint = Path("/data/synthdog-doc/metrics/lint_final.json")
    if lint.exists():
        L = json.loads(lint.read_text())
        k = next(iter(L))
        stats["lint"] = L[k]["summary"]["all"]
    (out / "final_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print("sampled", len(picked), "pages; stats:", {k: stats[k] for k in ("n_ok", "n_err", "size")})


if __name__ == "__main__":
    main()

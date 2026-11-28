"""Cheap image-statistics prefilter of raw crops into candidate pools (no OCR).

photo candidates: few near-white pixels, colourful or tonal, little stroke texture; diagram candidates: mostly
white background with sparse strokes. Final usability/topic is decided by scripts/tag_photos.py (VLM).
  python3 scripts/prefilter_assets.py /data/synthdog-doc/assets_raw /data/synthdog-doc/assets_new 6
"""
import json
import shutil
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image


def stats(path):
    try:
        im = Image.open(path).convert("RGB")
        w, h = im.size
        a = np.asarray(im.resize((256, max(1, int(256 * h / w)))), dtype=np.float32)
        g = a.mean(axis=2)
        white = float((g > 235).mean())
        sat = float((a.max(axis=2) - a.min(axis=2)).mean())
        gx = np.abs(np.diff(g, axis=1))
        edges = float((gx > 60).mean())
        uniq = len(np.unique((a[::4, ::4] // 16).reshape(-1, 3), axis=0))
        return str(path), w, h, white, sat, edges, uniq
    except Exception:  # noqa: BLE001
        return str(path), 0, 0, None, None, None, None


def kind_of(w, h, white, sat, edges, uniq):
    if white is None or w < 300 or h < 220:
        return None
    if white < 0.18 and uniq > 140 and edges < 0.12:
        return "photo" if sat > 14 else "photo_gray"
    if white > 0.45 and edges < 0.10 and uniq < 120:
        return "diagram"
    return None


def main(raw, out, n):
    files = sorted(Path(raw).glob("*.jpg"))
    with Pool(n) as p:
        rows = p.map(stats, files, chunksize=64)
    pools = {}
    for path, w, h, white, sat, edges, uniq in rows:
        k = kind_of(w, h, white, sat, edges, uniq)
        if k:
            pools.setdefault(k, []).append({"path": path, "w": w, "h": h, "white": round(white, 3),
                                            "sat": round(sat, 1), "edges": round(edges, 3), "uniq": uniq,
                                            "src": Path(path).name.rsplit("_", 1)[0]})
    for k, lst in pools.items():
        d = Path(out) / k
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "index.jsonl", "w") as f:
            for row in lst:
                dst = d / Path(row["path"]).name
                shutil.copy2(row["path"], dst)
                row["path"] = str(dst)
                f.write(json.dumps(row) + "\n")
        print("pool", k, len(lst), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 6)

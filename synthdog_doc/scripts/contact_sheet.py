"""Tile rendered pages into a labelled contact sheet for quick visual review.

  python3 scripts/contact_sheet.py --renders /data/synthdog-doc/renders/v2 --types newspaper,ppt --out /tmp/cs.jpg
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders", required=True)
    ap.add_argument("--types", default="")
    ap.add_argument("--langs", default="")
    ap.add_argument("--max", type=int, default=24)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--th", type=int, default=560, help="thumbnail height")
    ap.add_argument("--overlay", action="store_true", help="use the .overlay.jpg files")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    types = set(filter(None, a.types.split(",")))
    langs = set(filter(None, a.langs.split(",")))
    files = []
    for f in sorted(Path(a.renders).glob("*.jpg")):
        if f.name.endswith(".overlay.jpg") != a.overlay:
            continue
        t, lang = f.name.split("__")[:2]
        if (types and t not in types) or (langs and lang not in langs):
            continue
        files.append(f)
    files = files[: a.max]
    if not files:
        raise SystemExit("no pages")
    thumbs = []
    for f in files:
        im = Image.open(f).convert("RGB")
        w = int(im.width * a.th / im.height)
        thumbs.append((f.name.replace(".overlay", "").rsplit(".", 1)[0], im.resize((w, a.th), Image.LANCZOS)))
    cw = max(t.width for _, t in thumbs)
    rows = (len(thumbs) + a.cols - 1) // a.cols
    sheet = Image.new("RGB", (a.cols * (cw + 12) + 12, rows * (a.th + 34) + 12), "white")
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for i, (name, t) in enumerate(thumbs):
        x = 12 + (i % a.cols) * (cw + 12)
        y = 12 + (i // a.cols) * (a.th + 34)
        sheet.paste(t, (x + (cw - t.width) // 2, y))
        d.rectangle([x + (cw - t.width) // 2 - 1, y - 1, x + (cw + t.width) // 2, y + a.th], outline=(160, 160, 160))
        d.text((x, y + a.th + 6), name, fill=(20, 20, 20), font=font)
    sheet.save(a.out, quality=85)
    print(a.out, sheet.size, len(thumbs))


if __name__ == "__main__":
    main()

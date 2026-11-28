"""Tag photo-pool images with a topic using a VLM on numbered 3x3 contact sheets (9 images per call).

  python3 scripts/tag_photos.py /data/synthdog-doc/assets_new photo,photo_gray,illustration --workers 14
Writes `topic`, `subject` and `ok` fields back into each pool's index.jsonl (original kept as index.raw.jsonl).
"""
import json
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synthdog_doc import llm  # noqa: E402

TOPICS = ["people", "crowd", "politics", "sports", "business", "industry", "health", "science", "technology",
          "nature", "city", "building", "transport", "food", "education", "culture", "agriculture", "weather",
          "military", "religion", "object", "other"]
PROMPT = f"""The image is a 3x3 grid of 9 numbered pictures (1-9, left-to-right, top-to-bottom).
For each picture return its best topic from {TOPICS}, a 3-8 word English description of what it shows, and
whether it is usable as an editorial photo/illustration in a newspaper, magazine, textbook or slide
("ok": false if it is mostly text, a table, a chart, a screenshot, a logo, a blank/abstract crop, a scanned page
fragment, or of very poor quality).
Return ONLY JSON: {{"items": [{{"n": 1, "topic": "...", "subject": "...", "ok": true}}, ...]}}"""
_lock = threading.Lock()


def sheet(paths, out, cell=360):
    im = Image.new("RGB", (cell * 3, cell * 3), "white")
    dr = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
    except OSError:
        font = None
    for i, p in enumerate(paths):
        t = Image.open(p).convert("RGB")
        t.thumbnail((cell - 12, cell - 12))
        x, y = (i % 3) * cell + 6, (i // 3) * cell + 6
        im.paste(t, (x, y))
        dr.rectangle([x, y, x + 46, y + 42], fill=(255, 230, 0))
        dr.text((x + 10, y + 2), str(i + 1), fill=(0, 0, 0), font=font)
    im.save(out, quality=85)


def main(root, kinds, workers=14):
    root = Path(root)
    tmp = root / "_tag_sheets"
    tmp.mkdir(exist_ok=True)
    for kind in kinds.split(","):
        idx = root / kind / "index.jsonl"
        if not idx.exists():
            continue
        raw = root / kind / "index.raw.jsonl"
        if not raw.exists():
            shutil.copy2(idx, raw)
        rows = [json.loads(x) for x in raw.read_text().splitlines()]
        tags_path = root / kind / "tags.jsonl"
        done = {}
        if tags_path.exists():
            for line in tags_path.read_text().splitlines():
                d = json.loads(line)
                done[d["path"]] = d
        todo = [r for r in rows if r["path"] not in done]
        groups = [todo[i:i + 9] for i in range(0, len(todo), 9)]
        print(kind, "rows", len(rows), "groups", len(groups), flush=True)

        def work(gi, grp):
            sp = tmp / f"{kind}_{gi}.jpg"
            sheet([r["path"] for r in grp], sp)
            text, _ = llm.call("gpt-6.1-sol", PROMPT, images=[sp], max_tokens=3000, effort="low", timeout=300)
            items = llm.extract_json(text)
            items = items.get("items", items) if isinstance(items, dict) else items
            out = []
            for it in items:
                n = int(it.get("n", 0)) - 1
                if 0 <= n < len(grp):
                    out.append({"path": grp[n]["path"], "topic": it.get("topic", "other"),
                                "subject": it.get("subject", ""), "ok": bool(it.get("ok", False))})
            with _lock:
                with open(tags_path, "a") as f:
                    for o in out:
                        f.write(json.dumps(o) + "\n")
            return len(out)

        n_ok = 0
        with ThreadPoolExecutor(workers) as ex:
            futs = [ex.submit(work, gi, g) for gi, g in enumerate(groups)]
            for k, f in enumerate(as_completed(futs)):
                try:
                    n_ok += f.result()
                except Exception as e:  # noqa: BLE001
                    print("FAIL", repr(e)[:150], flush=True)
                if k % 50 == 0:
                    print(kind, k, "/", len(groups), flush=True)
        tags = {}
        for line in tags_path.read_text().splitlines():
            d = json.loads(line)
            tags[d["path"]] = d
        with open(idx, "w") as f:
            for r in rows:
                t = tags.get(r["path"])
                if t:
                    r.update(topic=t["topic"], subject=t["subject"], ok=t["ok"])
                f.write(json.dumps(r) + "\n")
        print(kind, "tagged", len(tags), "ok", sum(1 for t in tags.values() if t["ok"]), flush=True)
    print("TAG_DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 14)

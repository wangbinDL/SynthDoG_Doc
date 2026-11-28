"""Second tagging pass over the photo pools: visible text and overlays inside each photo.

A photo that shows text (signs, captions baked into the crop, camera timestamps, GPS stamps, stock-agency credits)
puts unannotated -- often foreign-script -- text into a figure region. Pages should avoid such photos.

  python3 scripts/tag_photo_text.py /data/synthdog-doc/assets photo,photo_gray --workers 16
Adds `text` ("none" | "little" | "much"), `text_script` and `overlay` (bool) to each pool's index.jsonl.
"""
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synthdog_doc import llm  # noqa: E402
from tag_photos import sheet  # noqa: E402

PROMPT = """The image is a 3x3 grid of 9 numbered pictures (1-9, left-to-right, top-to-bottom).
For each picture report the readable TEXT that is visible inside it:
- "text": "none" (no readable text), "little" (a few small words, e.g. a shirt logo or a distant sign) or
  "much" (prominent words, captions, signs, subtitles, labels or paragraphs);
- "script": the writing system of that text ("latin", "cyrillic", "arabic", "devanagari", "bengali", "cjk", "other",
  or "none");
- "overlay": true if the picture carries a camera date/time stamp, GPS / map / compass overlay, watermark, or a stock
  agency / photographer credit printed on it.
Return ONLY JSON: {"items": [{"n": 1, "text": "none", "script": "none", "overlay": false}, ...]}"""
_lock = threading.Lock()


def main(root, kinds, workers=16):
    root = Path(root)
    tmp = root / "_tag_sheets"
    tmp.mkdir(exist_ok=True)
    for kind in kinds.split(","):
        idx = root / kind / "index.jsonl"
        if not idx.exists():
            continue
        rows = [json.loads(x) for x in idx.read_text().splitlines()]
        tags_path = root / kind / "text_tags.jsonl"
        done = {}
        if tags_path.exists():
            for line in tags_path.read_text().splitlines():
                d = json.loads(line)
                done[d["path"]] = d
        todo = [r for r in rows if r["path"] not in done and r.get("ok") is not False]
        groups = [todo[i:i + 9] for i in range(0, len(todo), 9)]
        print(kind, "rows", len(rows), "groups", len(groups), flush=True)

        def work(gi, grp):
            sp = tmp / f"text_{kind}_{gi}.jpg"
            sheet([r["path"] for r in grp], sp)
            text, _ = llm.call("gpt-6.1-sol", PROMPT, images=[sp], max_tokens=3000, effort="low", timeout=300)
            items = llm.extract_json(text)
            items = items.get("items", items) if isinstance(items, dict) else items
            out = []
            for it in items:
                n = int(it.get("n", 0)) - 1
                if 0 <= n < len(grp):
                    out.append({"path": grp[n]["path"], "text": it.get("text", "none"),
                                "text_script": it.get("script", "none"), "overlay": bool(it.get("overlay", False))})
            with _lock:
                with open(tags_path, "a") as f:
                    for o in out:
                        f.write(json.dumps(o) + "\n")
            return len(out)

        with ThreadPoolExecutor(workers) as ex:
            futs = [ex.submit(work, gi, g) for gi, g in enumerate(groups)]
            for k, f in enumerate(as_completed(futs)):
                try:
                    f.result()
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
                    r.update(text=t["text"], text_script=t["text_script"], overlay=t["overlay"])
                f.write(json.dumps(r) + "\n")
        n_bad = sum(1 for t in tags.values() if t["text"] == "much" or t["overlay"])
        print(kind, "tagged", len(tags), "with prominent text / overlays", n_bad, flush=True)
    print("TEXT_TAG_DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 16)

"""Real-document eval set, step 5: PP-DocLayoutV3 region proposals for the sampled pages.

Runs inside the ocr-serve image with its layout venv (paddleocr LayoutDetection, ONNX Runtime, CPU or GPU), using
exactly the PaddleOCR-VL-1.6 pipeline settings (threshold 0.3, NMS, unclip 1.0):

  /opt/venv-layout/bin/python layout_detect.py --pages /data/synthdog-doc/evalset/pages --shard 0/8

Writes <pages>/layout/<page_id>.json = [{"label", "score", "box": [x0, y0, x1, y1]}] (image pixels).
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--model-dir", default="/mnt/wangbin02-jfs/models/PP-DocLayoutV3-onnx")
    ap.add_argument("--shard", default="0/1")
    a = ap.parse_args()
    k, n = (int(x) for x in a.shard.split("/"))
    root = Path(a.pages)
    man = [json.loads(x) for x in (root / "manifest.jsonl").read_text().splitlines() if x.strip()]
    todo = [m for i, m in enumerate(man) if i % n == k and not (root / "layout" / f"{m['page_id']}.json").exists()]
    (root / "layout").mkdir(exist_ok=True)
    from paddleocr import LayoutDetection
    model = LayoutDetection(model_name="PP-DocLayoutV3", model_dir=a.model_dir, engine="onnxruntime",
                            threshold=0.3, layout_nms=True, layout_unclip_ratio=[1.0, 1.0])
    for j, m in enumerate(todo, 1):
        img = root / "images" / m["lang"] / f"{m['page_id']}.jpg"
        boxes = []
        for res in model.predict(str(img), batch_size=1):
            for b in res.get("boxes", []) or []:
                boxes.append({"label": str(b.get("label")), "score": round(float(b.get("score", 0)), 4),
                              "box": [round(float(v), 1) for v in b["coordinate"]]})
        tmp = root / "layout" / f"{m['page_id']}.json.tmp"
        tmp.write_text(json.dumps(boxes))
        tmp.rename(root / "layout" / f"{m['page_id']}.json")
        if j % 20 == 0:
            print(f"shard {k}/{n}: {j}/{len(todo)}", flush=True)
    print(f"LAYOUT_DONE shard {k}/{n} pages={len(todo)}", flush=True)


if __name__ == "__main__":
    main()

"""Real-document eval set, step 1b: candidates from the FinePDFs parquet shards on JFS (for configs the HF dataset
viewer cannot serve, e.g. spa_Latn / eng_Latn, or when its rate limit is hit). Same output schema as candidates.py.

Runs on a worker:  python3 -m synthdog_doc.evalset.candidates_shard --src /mnt/wangbin02-jfs/public_data/finepdfs \
    --out /data/synthdog-doc/evalset/candidates --langs es,fr,bn,en --n 4000
"""
import argparse
import json
import random
import re
import urllib.parse
from pathlib import Path

import pyarrow.parquet as pq

from .candidates import CONFIGS, _num
from .zhscript import zh_variant

COLS = ["id", "url", "dump", "file_path", "offset", "extractor", "is_truncated", "page_ends", "token_count",
        "fw_edu_scores", "ocr_quality_scores", "full_doc_lid", "full_doc_lid_score", "text"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--langs", required=True)
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=20261128)
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    for lang in a.langs.split(","):
        cfg = CONFIGS[lang]
        rnd = random.Random(f"{a.seed}-{lang}")
        pool = []
        for f in sorted((Path(a.src) / cfg).glob("*.parquet")):
            pf = pq.ParquetFile(str(f))
            have = [c for c in COLS if c in pf.schema_arrow.names]
            groups = list(range(pf.num_row_groups))
            rnd.shuffle(groups)
            for g in groups:
                for r in pf.read_row_group(g, columns=have).to_pylist():
                    text = r.get("text") or ""
                    if lang.startswith("zh") and zh_variant(text[:4000]) != ("hans" if lang == "zh-Hans" else "hant"):
                        continue
                    pe = r.get("page_ends")
                    try:
                        pe = json.loads(pe) if isinstance(pe, str) else pe
                    except Exception:  # noqa: BLE001
                        pe = None
                    url = r.get("url") or ""
                    pool.append({
                        "id": r.get("id"), "lang": lang, "config": cfg, "url": url,
                        "domain": urllib.parse.urlparse(url).netloc.lower().removeprefix("www."),
                        "dump": r.get("dump"), "file_path": r.get("file_path"), "offset": _num(r.get("offset"), int),
                        "extractor": r.get("extractor"), "is_truncated": str(r.get("is_truncated")) == "True",
                        "n_pages": len(pe) if isinstance(pe, list) else None,
                        "token_count": _num(r.get("token_count"), int), "fw_edu": _num(r.get("fw_edu_scores")),
                        "ocr_quality": _num(r.get("ocr_quality_scores")), "lid": r.get("full_doc_lid"),
                        "lid_score": _num(r.get("full_doc_lid_score")),
                        "preview": re.sub(r"\s+", " ", text[:1500]).strip()})
                if len(pool) >= a.n * 3:
                    break
            if len(pool) >= a.n * 3:
                break
        rnd.shuffle(pool)
        with open(Path(a.out) / f"{lang}.jsonl", "w", encoding="utf-8") as fh:
            for d in pool[:a.n]:
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        print(f"[{lang}] kept={min(len(pool), a.n)} from_shard", flush=True)
    print("CANDIDATES_SHARD_DONE", flush=True)


if __name__ == "__main__":
    main()

"""Real-document eval set, step 1: candidate PDFs per language from FinePDFs (HF datasets-server /rows sampling).

FinePDFs (HuggingFaceFW/finepdfs, ODC-By) holds text extracted from CommonCrawl PDFs; every row keeps the CommonCrawl
WARC file + offset, so the original PDF bytes can be fetched later (fetch_pdfs.py). Here we only keep metadata and
a text preview for document-type classification.

  python3 -m synthdog_doc.evalset.candidates --out /data/synthdog-doc/evalset/candidates --langs all --calls 40

Output: <out>/<lang>.jsonl, one row per document:
  {"id","lang","config","url","domain","dump","file_path","offset","extractor","is_truncated","n_pages",
   "token_count","fw_edu","ocr_quality","lid","lid_score","preview"}
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .zhscript import zh_variant

API = "https://datasets-server.huggingface.co"
DATASET = "HuggingFaceFW/finepdfs"
# FinePDFs config per SynthDoG-Doc language code
CONFIGS = {"hi": "hin_Deva", "es": "spa_Latn", "ar": "arb_Arab", "fr": "fra_Latn", "bn": "ben_Beng", "pt": "por_Latn",
           "id": "ind_Latn", "ur": "urd_Arab", "ru": "rus_Cyrl", "de": "deu_Latn", "en": "eng_Latn",
           "zh-Hans": "cmn_Hani", "zh-Hant": "cmn_Hani", "ja": "jpn_Jpan", "ko": "kor_Hang", "vi": "vie_Latn",
           "th": "tha_Thai", "tr": "tur_Latn", "fa": "fas_Arab", "it": "ita_Latn", "pl": "pol_Latn", "nl": "nld_Latn"}


def _opener():
    px = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    return urllib.request.build_opener(urllib.request.ProxyHandler({"https": px, "http": px} if px else {}))


OPENER = _opener()


def get_json(url, tries=6):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "synthdog-doc-research/0.2"})
            with OPENER.open(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(min(60, 2 ** i + random.random()))
    raise RuntimeError(f"{url}: {last}")


def num_rows(config):
    """Row count from the datasets-server /size endpoint (the /rows probe returns HTTP 500 for some big configs)."""
    global _SIZES
    if _SIZES is None:
        try:
            d = get_json(f"{API}/size?dataset={urllib.parse.quote(DATASET)}")
            _SIZES = {c["config"]: c["num_rows"] for c in d["size"]["configs"]}
        except Exception:  # noqa: BLE001
            _SIZES = {}
    if config in _SIZES:
        return _SIZES[config]
    q = urllib.parse.urlencode({"dataset": DATASET, "config": config, "split": "train", "offset": 0, "length": 1})
    return get_json(f"{API}/rows?{q}")["num_rows_total"]


_SIZES = None


def rows(config, offset):
    q = urllib.parse.urlencode({"dataset": DATASET, "config": config, "split": "train", "offset": offset,
                                "length": 100})
    return [r["row"] for r in get_json(f"{API}/rows?{q}")["rows"]]


def _num(x, cast=float):
    try:
        if isinstance(x, str) and x.startswith("["):
            x = json.loads(x)[0]
        return cast(x)
    except Exception:  # noqa: BLE001
        return None


def run_lang(lang, out_dir, calls, workers, seed):
    cfg = CONFIGS[lang]
    n = num_rows(cfg)
    rnd = random.Random(f"{seed}-{lang}")
    offsets = sorted({rnd.randrange(0, max(1, n - 100)) for _ in range(calls)})
    # some big configs are not served by the dataset viewer (HTTP 500): fail fast, use the parquet shards instead
    q = urllib.parse.urlencode({"dataset": DATASET, "config": cfg, "split": "train", "offset": offsets[0],
                                "length": 1})
    get_json(f"{API}/rows?{q}", tries=2)
    kept = 0
    path = Path(out_dir) / f"{lang}.jsonl"
    with open(path, "w", encoding="utf-8") as fh, ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(rows, cfg, o): o for o in offsets}
        for f in as_completed(futs):
            try:
                rs = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"[{lang}] offset {futs[f]} failed: {e}", file=sys.stderr, flush=True)
                continue
            for r in rs:
                text = r.get("text") or ""
                if lang.startswith("zh") and zh_variant(text[:4000]) != ("hans" if lang == "zh-Hans" else "hant"):
                    continue
                pe = r.get("page_ends")
                try:
                    pe = json.loads(pe) if isinstance(pe, str) else pe
                except Exception:  # noqa: BLE001
                    pe = None
                url = r.get("url") or ""
                fh.write(json.dumps({
                    "id": r.get("id"), "lang": lang, "config": cfg, "url": url,
                    "domain": urllib.parse.urlparse(url).netloc.lower().removeprefix("www."),
                    "dump": r.get("dump"), "file_path": r.get("file_path"), "offset": _num(r.get("offset"), int),
                    "extractor": r.get("extractor"), "is_truncated": str(r.get("is_truncated")) == "True",
                    "n_pages": len(pe) if isinstance(pe, list) else None,
                    "token_count": _num(r.get("token_count"), int), "fw_edu": _num(r.get("fw_edu_scores")),
                    "ocr_quality": _num(r.get("ocr_quality_scores")), "lid": r.get("full_doc_lid"),
                    "lid_score": _num(r.get("full_doc_lid_score")),
                    "preview": re.sub(r"\s+", " ", text[:1500]).strip()}, ensure_ascii=False) + "\n")
                kept += 1
    print(f"[{lang}] rows_total={n} calls={len(offsets)} kept={kept}", flush=True)
    return kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--langs", default="all")
    ap.add_argument("--calls", type=int, default=40)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20261128)
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    langs = list(CONFIGS) if a.langs == "all" else a.langs.split(",")
    for lang in langs:
        if (Path(a.out) / f"{lang}.jsonl").exists() and not a.redo:
            print(f"[{lang}] exists, skip", flush=True)
            continue
        calls = a.calls * (3 if lang.startswith("zh") else 1)    # cmn_Hani mixes both Chinese scripts
        try:
            run_lang(lang, a.out, calls, a.workers, a.seed)
        except Exception as e:  # noqa: BLE001
            print(f"[{lang}] FAILED {e!r}"[:300], flush=True)
    print("CANDIDATES_DONE", flush=True)


if __name__ == "__main__":
    main()

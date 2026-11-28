"""Fetch per-language text corpora through the HF datasets-server REST API.

The cluster proxy reaches huggingface.co APIs but not the LFS CDN, so we sample rows
via /rows (random offsets, 100 rows per call) instead of downloading parquet shards.

Outputs (JSONL, one record per article/page):
  <out>/<lang>/wiki.jsonl   {"title","sections":[{"heading","paras":[...]}],"url"}
  <out>/<lang>/web.jsonl    {"url","domain","kind":"news|national","title","paras":[...],"date"}

Usage:
  python3 -m synthdog_doc.corpus_fetch --out /data/synthdog-doc/corpus --langs hi,es --wiki-calls 40 --web-calls 150
"""
import argparse
import json
import random
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .langs import LANG_ORDER, LANGS

API = "https://datasets-server.huggingface.co"
SCRIPT_RANGES = {
    "latin": [(0x41, 0x24F)],
    "cyrillic": [(0x400, 0x4FF)],
    "devanagari": [(0x900, 0x97F)],
    "bengali": [(0x980, 0x9FF)],
    "arabic": [(0x600, 0x6FF), (0x750, 0x77F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
}


def http_json(url, timeout=60, tries=6):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "synthdog-doc-research/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(min(60, 2 ** i + random.random()))
    raise RuntimeError(f"failed {url}: {last}")


def num_rows(dataset, config):
    q = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": "train", "offset": 0, "length": 1})
    return http_json(f"{API}/rows?{q}")["num_rows_total"]


def rows(dataset, config, offset, length=100):
    q = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": "train",
                                "offset": offset, "length": length})
    return [r["row"] for r in http_json(f"{API}/rows?{q}")["rows"]]


def script_ratio(text, script):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    rng = SCRIPT_RANGES[script]
    hit = sum(1 for c in letters if any(a <= ord(c) <= b for a, b in rng))
    return hit / len(letters)


def clean_para(p):
    p = unicodedata.normalize("NFC", p).strip()
    p = re.sub(r"\s+", " ", p)
    return p


def wiki_sections(text, script):
    """Split a Wikipedia plaintext article into (heading, paragraphs) sections."""
    lines = [clean_para(x) for x in text.split("\n")]
    sections, cur = [], {"heading": "", "paras": []}
    for ln in lines:
        if not ln:
            continue
        is_heading = len(ln) < 80 and not re.search(r"[.!?।۔؟]$", ln) and len(ln.split()) <= 10
        if is_heading:
            if cur["paras"]:
                sections.append(cur)
            cur = {"heading": ln, "paras": []}
        elif len(ln) >= 40 and script_ratio(ln, script) >= 0.6:
            cur["paras"].append(ln)
    if cur["paras"]:
        sections.append(cur)
    # drop typical tail sections (references, see also...) by keeping sections with real prose only
    return [s for s in sections if sum(len(p) for p in s["paras"]) >= 120]


def domain_of(url):
    try:
        return urllib.parse.urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def classify_web(url, lang):
    d = domain_of(url)
    for nd in lang.news_domains:
        if d == nd or d.endswith("." + nd):
            return d, "news"
    for t in lang.country_tlds:
        if d.endswith(t):
            return d, "national"
    return d, None


def fetch_wiki(lang, out_dir, calls, workers, seed):
    cfg = lang.wiki_config
    try:
        n = num_rows("wikimedia/wikipedia", cfg)
    except Exception as e:  # noqa: BLE001
        print(f"[{lang.code}] wiki num_rows failed: {e}", file=sys.stderr, flush=True)
        return 0
    rnd = random.Random(seed)
    offsets = sorted({rnd.randrange(0, max(1, n - 100)) for _ in range(calls)})
    out = open(out_dir / "wiki.jsonl", "w", encoding="utf-8")
    kept = 0
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(rows, "wikimedia/wikipedia", cfg, o): o for o in offsets}
        for f in as_completed(futs):
            try:
                rs = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"[{lang.code}] wiki offset {futs[f]} failed: {e}", file=sys.stderr)
                continue
            for r in rs:
                secs = wiki_sections(r.get("text", ""), lang.script)
                if sum(len(p) for s in secs for p in s["paras"]) < 600:
                    continue
                out.write(json.dumps({"title": clean_para(r.get("title", "")), "url": r.get("url", ""),
                                      "sections": secs}, ensure_ascii=False) + "\n")
                kept += 1
    out.close()
    print(f"[{lang.code}] wiki rows_total={n} calls={len(offsets)} kept={kept}", flush=True)
    return kept


WEB_DATASET = "HuggingFaceFW/fineweb-2"
WEB_CONFIG = {}   # lang -> config override (e.g. when the fineweb-2 config is unavailable server-side)


def fetch_web(lang, out_dir, calls, workers, seed):
    cfg = WEB_CONFIG.get(lang.code, lang.fineweb_config)
    try:
        n = num_rows(WEB_DATASET, cfg)
    except Exception as e:  # noqa: BLE001
        print(f"[{lang.code}] web num_rows failed: {e}", file=sys.stderr, flush=True)
        return {}
    rnd = random.Random(seed + 1)
    offsets = sorted({rnd.randrange(0, max(1, n - 100)) for _ in range(calls)})
    out = open(out_dir / "web.jsonl", "w", encoding="utf-8")
    stats = {"rows": 0, "news": 0, "national": 0}
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(rows, WEB_DATASET, cfg, o): o for o in offsets}
        for f in as_completed(futs):
            try:
                rs = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"[{lang.code}] web offset {futs[f]} failed: {e}", file=sys.stderr)
                continue
            for r in rs:
                stats["rows"] += 1
                d, kind = classify_web(r.get("url", ""), lang)
                if not kind or (r.get("language_score") if "language_score" in r else 1.0) < 0.75:
                    continue
                lines = [clean_para(x) for x in (r.get("text") or "").split("\n")]
                lines = [x for x in lines if x]
                if not lines:
                    continue
                title = lines[0] if len(lines[0]) <= 160 else ""
                paras = [x for x in lines[1 if title else 0:]
                         if len(x) >= 60 and script_ratio(x, lang.script) >= 0.6]
                if sum(len(p) for p in paras) < 400:
                    continue
                stats[kind] += 1
                out.write(json.dumps({"url": r.get("url"), "domain": d, "kind": kind, "title": title,
                                      "paras": paras, "date": r.get("date")}, ensure_ascii=False) + "\n")
    out.close()
    print(f"[{lang.code}] web rows_total={n} calls={len(offsets)} {stats}", flush=True)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--langs", default=",".join(LANG_ORDER))
    ap.add_argument("--wiki-calls", type=int, default=40)
    ap.add_argument("--web-calls", type=int, default=150)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20261127)
    ap.add_argument("--skip-wiki", action="store_true")
    ap.add_argument("--skip-web", action="store_true")
    ap.add_argument("--web-dataset", default=None, help="override, e.g. allenai/c4")
    ap.add_argument("--web-config", default=None, help="override config for all langs, e.g. es")
    a = ap.parse_args()
    global WEB_DATASET
    if a.web_dataset:
        WEB_DATASET = a.web_dataset
    if a.web_config:
        for code in a.langs.split(","):
            WEB_CONFIG[code] = a.web_config
    for code in a.langs.split(","):
        lang = LANGS[code]
        od = Path(a.out) / code
        od.mkdir(parents=True, exist_ok=True)
        if not a.skip_wiki:
            fetch_wiki(lang, od, a.wiki_calls, a.workers, a.seed)
        if not a.skip_web:
            fetch_web(lang, od, a.web_calls, a.workers, a.seed)


if __name__ == "__main__":
    main()

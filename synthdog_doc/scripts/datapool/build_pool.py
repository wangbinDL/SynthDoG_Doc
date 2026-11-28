"""Build the SynthDoG-Doc real-text pool (task 2) from FinePDFs / FineWeb-2 parquet shards on JFS.

Per language: quality filters -> page-level text chunks -> parquet + statistics. Runs on a worker:

  python3 build_pool.py --src /mnt/wangbin02-jfs/public_data --out /mnt/wangbin02-jfs/processed/synthdog_doc/datapool/v1 \
      --stats /data/synthdog-doc/datapool/pool_stats_v1.json --workers 24

FinePDFs filters (each counted in the statistics):
  lid       full-document language id matches the config (zh: Simplified / Traditional split by character sets)
  dup       duplicate_count <= 1
  trunc     is_truncated == False (text cut by CommonCrawl's record limit)
  ocr       rolmOCR (scanned) documents need ocr_quality >= 0.5 when the score exists
  script    >= 80 % of letters in the language's script (catches legacy non-Unicode font "mojibake" PDFs)
  short     >= 500 characters of text
  pii       documents dominated by e-mail addresses / phone numbers (forms, directories) are dropped
Pages: text split at page_ends; a page is kept with >= 300 characters (>= 150 for CJK / Thai).
FineWeb-2 (web text for news / magazine layouts): language_score >= 0.75, script purity, >= 400 characters.
Documents whose id is listed in --exclude (the real eval set) are removed (leakage isolation).
"""
import argparse
import json
import re
import sys
import time
import unicodedata
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from synthdog_doc.corpus_fetch import SCRIPT_RANGES, zh_variant  # noqa: E402
from synthdog_doc.langs import LANGS  # noqa: E402

FINEPDFS = {"hi": "hin_Deva", "es": "spa_Latn", "ar": "arb_Arab", "fr": "fra_Latn", "bn": "ben_Beng", "pt": "por_Latn",
            "id": "ind_Latn", "ur": "urd_Arab", "ru": "rus_Cyrl", "de": "deu_Latn", "en": "eng_Latn",
            "zh-Hans": "cmn_Hani", "zh-Hant": "cmn_Hani", "ja": "jpn_Jpan", "ko": "kor_Hang", "vi": "vie_Latn",
            "th": "tha_Thai", "tr": "tur_Latn", "fa": "fas_Arab", "it": "ita_Latn", "pl": "pol_Latn", "nl": "nld_Latn"}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def purity(text, script):
    rng = SCRIPT_RANGES.get(script) or SCRIPT_RANGES["latin"]
    letters = [c for c in text[:20000] if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if any(a <= ord(c) <= b for a, b in rng)) / len(letters)


def as_list(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:  # noqa: BLE001
            return None
    return x


def first_num(x):
    x = as_list(x) if isinstance(x, str) else x
    if isinstance(x, list):
        x = x[0] if x else None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def build_finepdfs(lang, src, out, exclude):
    cfg = FINEPDFS[lang]
    L = LANGS[lang]
    script = {"urdu": "arabic"}.get(L.script, L.script)
    cjk = L.segment in ("cjk", "thai")
    min_page = 150 if cjk else 300
    files = sorted((Path(src) / "finepdfs" / cfg).glob("*.parquet"))
    st = {"docs_in": 0, "lid": 0, "dup": 0, "trunc": 0, "ocr": 0, "script": 0, "short": 0, "pii": 0, "excluded": 0,
          "docs_kept": 0, "pages_kept": 0, "chars_kept": 0, "extractor": {}, "domains": 0}
    cols = ["id", "url", "text", "full_doc_lid", "full_doc_lid_score", "duplicate_count", "is_truncated",
            "extractor", "ocr_quality_scores", "page_ends", "fw_edu_scores", "dump"]
    rows, domains = [], set()
    want_lid = cfg
    for f in files:
        pf = pq.ParquetFile(str(f))
        have = [c for c in cols if c in pf.schema_arrow.names]
        for batch in pf.iter_batches(batch_size=2000, columns=have):
            for r in batch.to_pylist():
                st["docs_in"] += 1
                text = r.get("text") or ""
                if r.get("id") in exclude:
                    st["excluded"] += 1
                    continue
                lid = r.get("full_doc_lid") or ""
                if lid != want_lid and not (lid.split("_")[-1] == want_lid.split("_")[-1] and (first_num(r.get("full_doc_lid_score")) or 0) < 0.5):
                    st["lid"] += 1
                    continue
                if L.zh_script and zh_variant(text[:6000]) != L.zh_script:
                    st["lid"] += 1
                    continue
                if (first_num(r.get("duplicate_count")) or 0) > 1:
                    st["dup"] += 1
                    continue
                if str(r.get("is_truncated")) == "True":
                    st["trunc"] += 1
                    continue
                q = first_num(r.get("ocr_quality_scores"))
                if r.get("extractor") == "rolmOCR" and q is not None and q < 0.5:
                    st["ocr"] += 1
                    continue
                if len(text) < 500:
                    st["short"] += 1
                    continue
                if purity(text, script) < 0.8:
                    st["script"] += 1
                    continue
                n_mail = len(_EMAIL.findall(text[:20000]))
                n_tel = len(_PHONE.findall(text[:20000]))
                if (n_mail + n_tel) * 80 > len(text[:20000]):
                    st["pii"] += 1
                    continue
                ends = as_list(r.get("page_ends")) or [len(text)]
                prev, kept_pages = 0, 0
                for pi, e in enumerate(ends):
                    pt = unicodedata.normalize("NFC", text[prev:e]).strip()
                    prev = e
                    if len(pt) >= min_page:
                        rows.append({"doc_id": r.get("id"), "page": pi, "text": pt, "n_chars": len(pt),
                                     "url": r.get("url") or "", "extractor": r.get("extractor") or "",
                                     "fw_edu": first_num(r.get("fw_edu_scores")), "dump": r.get("dump") or ""})
                        kept_pages += 1
                if kept_pages:
                    st["docs_kept"] += 1
                    st["pages_kept"] += kept_pages
                    st["extractor"][r.get("extractor") or "?"] = st["extractor"].get(r.get("extractor") or "?", 0) + 1
                    domains.add((r.get("url") or "").split("/")[2] if (r.get("url") or "").count("/") >= 2 else "")
    st["chars_kept"] = sum(x["n_chars"] for x in rows)
    st["domains"] = len(domains)
    od = Path(out) / lang
    od.mkdir(parents=True, exist_ok=True)
    if rows:
        pq.write_table(pa.Table.from_pylist(rows), str(od / "finepdfs_pages.parquet"), compression="zstd",
                       row_group_size=20000)
    return st


def build_fineweb(lang, src, out):
    L = LANGS[lang]
    cfg = L.fineweb_config
    ds = "fineweb-2" if L.web_dataset.endswith("fineweb-2") else "fineweb"
    files = sorted((Path(src) / ds / cfg).glob("*.parquet"))
    script = {"urdu": "arabic"}.get(L.script, L.script)
    st = {"docs_in": 0, "lang_score": 0, "script": 0, "short": 0, "lid": 0, "docs_kept": 0, "chars_kept": 0}
    rows = []
    for f in files:
        pf = pq.ParquetFile(str(f))
        have = [c for c in ("id", "url", "text", "language_score", "date") if c in pf.schema_arrow.names]
        for batch in pf.iter_batches(batch_size=4000, columns=have):
            for r in batch.to_pylist():
                st["docs_in"] += 1
                text = r.get("text") or ""
                if (r.get("language_score") or 1.0) < 0.75:
                    st["lang_score"] += 1
                    continue
                if len(text) < 400:
                    st["short"] += 1
                    continue
                if L.zh_script and zh_variant(text[:4000]) != L.zh_script:
                    st["lid"] += 1
                    continue
                if purity(text, script) < 0.8:
                    st["script"] += 1
                    continue
                rows.append({"id": r.get("id"), "url": r.get("url") or "", "text": unicodedata.normalize("NFC", text),
                             "n_chars": len(text), "date": str(r.get("date") or "")})
                st["docs_kept"] += 1
    st["chars_kept"] = sum(x["n_chars"] for x in rows)
    if rows:
        od = Path(out) / lang
        od.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows), str(od / "fineweb_docs.parquet"), compression="zstd",
                       row_group_size=20000)
    return st


def one(lang, src, out, exclude):
    t0 = time.time()
    res = {"lang": lang, "finepdfs": build_finepdfs(lang, src, out, exclude)}
    try:
        res["fineweb"] = build_fineweb(lang, src, out)
    except Exception as e:  # noqa: BLE001
        res["fineweb"] = {"error": repr(e)[:200]}
    res["sec"] = round(time.time() - t0, 1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--langs", default="all")
    ap.add_argument("--exclude", default="", help="file with one FinePDFs document id per line (eval set)")
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    langs = list(FINEPDFS) if a.langs == "all" else a.langs.split(",")
    exclude = set(Path(a.exclude).read_text().split()) if a.exclude and Path(a.exclude).exists() else set()
    stats = {}
    with ProcessPoolExecutor(a.workers) as ex:
        futs = {ex.submit(one, lg, a.src, a.out, exclude): lg for lg in langs}
        for f in as_completed(futs):
            lg = futs[f]
            try:
                stats[lg] = f.result()
            except Exception as e:  # noqa: BLE001
                stats[lg] = {"error": repr(e)[:300]}
            print(lg, json.dumps(stats[lg], ensure_ascii=False)[:400], flush=True)
            Path(a.stats).write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    print("POOL_DONE", flush=True)


if __name__ == "__main__":
    main()

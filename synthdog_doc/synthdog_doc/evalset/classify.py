"""Real-document eval set, step 2: document-type triage of FinePDFs candidates from their text preview.

A cheap LLM labels batches of previews with one of the SynthDoG-Doc layout families (plus "other"); only the
shortlist moves on to PDF fetching and visual verification (verify.py), so precision matters more than recall.

  python3 -m synthdog_doc.evalset.classify --cand /data/synthdog-doc/evalset/candidates \
      --out /data/synthdog-doc/evalset/triage --model deepseek-v4.1-flash-pretrain --max-per-lang 1500

Output <out>/<lang>.jsonl rows: candidate id + {"type", "conf", "lang_ok"}.
"""
import argparse
import json
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from synthdog_doc import llm  # noqa: E402

TYPES = ["slides", "exam", "academic_paper", "newspaper", "magazine", "book", "textbook", "report", "other"]
PROMPT = """You triage PDF documents for a document-layout benchmark. Expected language: {lname}.
For each numbered document you get its URL, page count and the first characters of its extracted text.
Label the document type:
- slides: presentation slide deck exported to PDF
- exam: exam / test / quiz / question paper (school, university, entrance or certification exam)
- academic_paper: scholarly article, conference paper, thesis chapter with abstract / references
- newspaper: newspaper issue or page (news articles, mastheads, columns)
- magazine: magazine issue, feature articles, glossy periodical
- book: book (fiction or non-fiction) or long monograph, not a school textbook
- textbook: school / university textbook, lesson material, workbook
- report: research report, annual / financial / equity research report, government or NGO report, white paper
- other: anything else (forms, manuals, catalogs, brochures, laws, letters, menus, certificates, spreadsheets)
Also say whether the text is mainly in {lname} ("lang_ok") and your confidence 0-1 ("conf").
Return ONLY JSON: {{"items": [{{"n": 1, "type": "...", "conf": 0.9, "lang_ok": true}}, ...]}}

{docs}"""
LNAME = {"hi": "Hindi", "es": "Spanish", "ar": "Arabic", "fr": "French", "bn": "Bengali", "pt": "Portuguese",
         "id": "Indonesian", "ur": "Urdu", "ru": "Russian", "de": "German", "en": "English",
         "zh-Hans": "Simplified Chinese", "zh-Hant": "Traditional Chinese", "ja": "Japanese", "ko": "Korean",
         "vi": "Vietnamese", "th": "Thai", "tr": "Turkish", "fa": "Persian", "it": "Italian", "pl": "Polish",
         "nl": "Dutch"}
_lock = threading.Lock()


def batch_prompt(lang, docs):
    lines = []
    for i, d in enumerate(docs, 1):
        lines.append(f"[{i}] url={d['url'][:120]} pages={d.get('n_pages')}\n{d['preview'][:600]}")
    return PROMPT.format(lname=LNAME[lang], docs="\n\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="deepseek-v4.1-flash-pretrain")
    ap.add_argument("--effort", default=None)
    ap.add_argument("--langs", default="all")
    ap.add_argument("--max-per-lang", type=int, default=1500)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    langs = sorted(LNAME) if a.langs == "all" else a.langs.split(",")
    jobs = []
    for lang in langs:
        p = Path(a.cand) / f"{lang}.jsonl"
        if not p.exists():
            continue
        docs = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        # prefer documents we can fetch intact from CommonCrawl and that have >= 2 pages
        docs = [d for d in docs if d.get("file_path") and d.get("offset") is not None and not d.get("is_truncated")
                and (d.get("n_pages") or 0) >= 2 and len(d.get("preview") or "") >= 200]
        random.Random(f"triage-{lang}").shuffle(docs)
        docs = docs[:a.max_per_lang]
        done = set()
        op = out / f"{lang}.jsonl"
        if op.exists():
            done = {json.loads(x)["id"] for x in op.read_text().splitlines() if x.strip()}
        docs = [d for d in docs if d["id"] not in done]
        for i in range(0, len(docs), a.batch):
            jobs.append((lang, docs[i:i + a.batch]))
    print(f"{len(jobs)} batches", flush=True)

    def work(job):
        lang, docs = job
        text, meta = llm.call(a.model, batch_prompt(lang, docs), max_tokens=3000, effort=a.effort, timeout=300)
        items = llm.extract_json(text)
        items = items.get("items", items) if isinstance(items, dict) else items
        res = []
        for it in items:
            n = int(it.get("n", 0)) - 1
            if 0 <= n < len(docs):
                t = it.get("type") if it.get("type") in TYPES else "other"
                res.append({**docs[n], "type": t, "conf": it.get("conf"), "lang_ok": bool(it.get("lang_ok", True))})
        with _lock, open(out / f"{lang}.jsonl", "a", encoding="utf-8") as fh:
            for r in res:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        return lang, len(res), meta.get("usage", {})

    ok = fail = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(work, j) for j in jobs]
        for k, f in enumerate(as_completed(futs), 1):
            try:
                f.result()
                ok += 1
            except Exception as e:  # noqa: BLE001
                fail += 1
                print("FAIL", repr(e)[:200], flush=True)
            if k % 50 == 0:
                print(f"  {k}/{len(jobs)} ok={ok} fail={fail}", flush=True)
    print(f"TRIAGE_DONE ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()

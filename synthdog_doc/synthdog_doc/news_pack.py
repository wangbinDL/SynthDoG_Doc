"""LLM packaging of real national-web news articles into coherent article packages.

The body text stays verbatim from the national website (only boilerplate paragraphs are dropped);
the LLM edits the headline and writes deck / kicker / caption / brief so every element of a newspaper or
magazine article module belongs to the same story.

  python3 -m synthdog_doc.news_pack --langs hi,ar --n 150 --workers 16
Output: /data/synthdog-doc/content/<lang>/news.jsonl
"""
import argparse
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import llm
from .corpus import _read_jsonl, good_para, clean_headline
from .langs import LANG_ORDER, LANGS
from .textkit import normalize

PROMPT = """You are a copy editor at a {lname}-language newspaper in {countries}. Below is a raw article scraped from
the website {domain}. Paragraphs are numbered. Some paragraphs may be boilerplate (ads, navigation, "read more",
cookie notices, related links, social buttons, duplicated lines, search-result pages).

TITLE: {title}
{paras}

Return ONLY one JSON object (all text in {lname}, written as a professional {lname} newspaper would print it):
{{"is_news": true/false (false if this is not a genuine news/feature article, e.g. a product page, ad, forum,
   listing or search page),
 "section": one of ["National","International","Economy","Sports","Culture","Politics","Science","Health",
   "Technology","Education","Local","Opinion","Entertainment","Business","World"],
 "kicker": "short section/topic label (1-3 words)",
 "headline": "edited headline, 5-14 words, no site name, no trailing period",
 "subhead": "optional second headline line (or empty)",
 "deck": "one-sentence standfirst summarizing THIS article",
 "dateline": "city of the story if stated, else empty",
 "keep": [indices of paragraphs that are genuine article body, in order; drop boilerplate/duplicates],
 "caption": "one-sentence photo caption describing a plausible news photo for THIS story",
 "photo_topic": one of ["people","crowd","politics","sports","business","industry","health","science",
   "technology","nature","city","building","transport","food","education","culture","agriculture","weather",
   "military","religion"],
 "pull_quote": "a short striking sentence copied verbatim from the kept paragraphs (or empty)",
 "brief": "1-2 sentence summary for a news-in-brief column"}}"""

_lock = threading.Lock()


def candidates(lang, n, seed=11):
    rows = _read_jsonl(Path("/data/synthdog-doc/corpus") / lang / "web.jsonl")
    rng = random.Random(seed)
    news = [r for r in rows if r.get("kind") == "news"]
    nat = [r for r in rows if r.get("kind") == "national"]
    rng.shuffle(news)
    rng.shuffle(nat)
    out = []
    for r in news + nat:
        paras = []
        seen = set()
        for p in r.get("paras", []):
            p = normalize(p)
            if p in seen or not good_para(p, 50):
                continue
            seen.add(p)
            paras.append(p)
        if sum(len(p) for p in paras) < 700 or len(paras) < 3:
            continue
        r = dict(r, paras=paras[:18], title=clean_headline(r.get("title") or ""))
        out.append(r)
        if len(out) >= n:
            break
    return out


def work(lang, i, art, model, effort, out_path, key="main"):
    L = LANGS[lang]
    paras = "\n".join(f"[{k}] {p[:900]}" for k, p in enumerate(art["paras"]))
    prompt = PROMPT.format(lname=L.name, countries=", ".join(L.countries), domain=art.get("domain", ""),
                           title=art.get("title", ""), paras=paras)
    text, meta = llm.call(model, prompt, max_tokens=6000, effort=effort, timeout=600, key=key)
    obj = llm.extract_json(text)
    if isinstance(obj, list):
        obj = next((x for x in obj if isinstance(x, dict)), {})
    keep = [k for k in obj.get("keep", []) if isinstance(k, int) and 0 <= k < len(art["paras"])]
    obj["body"] = [art["paras"][k] for k in keep] if keep else art["paras"]
    obj.pop("keep", None)
    obj.update({"_usage": meta.get("usage"), "_model": meta.get("model")})
    obj.update({"_idx": i, "_lang": lang, "url": art.get("url"), "domain": art.get("domain"), "date": art.get("date"),
                "source_kind": art.get("kind"), "orig_title": art.get("title")})
    with _lock:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return lang, i, len(obj["body"]), obj.get("is_news")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default=",".join(LANG_ORDER))
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--model", default="gpt-6.1-sol")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--key", default="main")
    ap.add_argument("--out", default="/data/synthdog-doc/content", help="content root (bake-off runs use their own)")
    a = ap.parse_args()
    jobs = []
    for lang in a.langs.split(","):
        out = Path(a.out) / lang / "news.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        done = {json.loads(x)["_idx"] for x in out.read_text().splitlines()} if out.exists() else set()
        for i, art in enumerate(candidates(lang, a.n)):
            if i not in done:
                jobs.append((lang, i, art, out))
    # interleave languages
    jobs.sort(key=lambda j: (j[1], j[0]))
    print("jobs", len(jobs), flush=True)
    ok = fail = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(work, l, i, art, a.model, a.effort, out, a.key): (l, i) for l, i, art, out in jobs}
        for f in as_completed(futs):
            try:
                r = f.result()
                ok += 1
                if ok % 25 == 0:
                    print("OK", ok, r, flush=True)
            except Exception as e:  # noqa: BLE001
                fail += 1
                print("FAIL", futs[f], repr(e)[:200], flush=True)
    print(f"NEWS_DONE ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()

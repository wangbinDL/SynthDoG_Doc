"""v5: country-specific print ads (each ad belongs to one country: currency, phone format, address, web domain)."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))
from synthdog_doc import llm
from synthdog_doc.langs import LANGS, LANG_ORDER
SEL = [x for x in os.environ.get('SDD_LANGS', ','.join(LANG_ORDER)).split(',') if x]  # languages to run
MODEL = os.environ.get('SDD_LLM', 'gpt-6.1-sol')

PROMPT = """Create 30 realistic print advertisements for {lname}-language newspapers and magazines published in
{country}. Every ad must be from {country}: its currency, phone number format, city / address, and web domain.
Mix: retail sale, bank/loan, mobile phone plan, real estate, private school/coaching, clinic/hospital, car dealer,
travel agency, furniture, electronics, restaurant, job vacancy, government notice/tender, classified, event/concert.
Return ONLY JSON: {{"ads": [{{"kind": "...", "brand": "fictional but natural brand", "headline": "2-6 words",
  "tagline": "short slogan", "offer": "price/discount/offer line with numbers and local currency",
  "details": ["2-4 short lines: address/area, opening hours, conditions"], "phone": "local-format phone number",
  "web": "plausible web address or empty"}}]}}
All text in {lname} except web addresses."""

def one(job):
    lang, country, k = job
    out = f"/data/synthdog-doc/content/{lang}/ads2.jsonl"
    L = LANGS[lang]
    text, _ = llm.call(MODEL, PROMPT.format(lname=L.name, country=country), max_tokens=12000, effort="low",
                       timeout=600)
    try:
        obj = llm.extract_json(text)
    except ValueError:
        return lang, country, "FAIL"
    ads = obj.get("ads") if isinstance(obj, dict) else obj
    rec = {"country": country, "ads": [dict(a, country=country) for a in (ads or []) if isinstance(a, dict)],
           "_idx": f"{country}-{k}"}
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return lang, country, len(rec["ads"])

jobs = [(l, c, k) for l in SEL for c in LANGS[l].countries[:3] for k in range(2 if c == LANGS[l].countries[0] else 1)]
with ThreadPoolExecutor(16) as ex:
    for r in ex.map(one, jobs):
        print(*r, flush=True)
print("ADS2_DONE")

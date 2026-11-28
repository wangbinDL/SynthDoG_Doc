"""One-off: localized equity-research disclosure boilerplate per language -> content/<lang>/disclosures.jsonl"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))
from synthdog_doc import llm
from synthdog_doc.langs import LANGS, LANG_ORDER
SEL = [x for x in os.environ.get('SDD_LANGS', ','.join(LANG_ORDER)).split(',') if x]  # languages to run
MODEL = os.environ.get('SDD_LLM', 'gpt-6.1-sol')

PROMPT = """Write the standard boilerplate of the final DISCLOSURES pages of a sell-side equity research report
published by a brokerage in {countries}, written natively in {lname} as local brokers do (follow the regulator
conventions of these countries, e.g. SEBI / CNMV / CVM / OJK / SECP / AMF / BaFin / CMA / Bank of Russia where
relevant). Use the placeholder {{broker}} for the brokerage name and {{analyst}} for an analyst name.
Return ONLY JSON, all text in {lname}:
{{"title": "heading for the disclosures section",
 "rating_header": ["column header 'Rating'", "column header 'Definition'"],
 "ratings": [["Buy", "expected total return definition with a percentage threshold over 12 months"],
             ["Accumulate or Overweight", "..."], ["Hold or Neutral", "..."], ["Reduce or Underweight", "..."],
             ["Sell", "..."]],
 "certification_title": "heading 'Analyst certification'",
 "certification": "the analyst certification paragraph (2-3 sentences, uses {{analyst}})",
 "sections": [{{"heading": "short heading", "text": "paragraph of 3-5 sentences"}} x 5 covering: important
     disclosures / conflicts of interest, general disclaimer (not an offer, information believed reliable),
     risk warning (past performance, currency), distribution restrictions (who may receive it), copyright],
 "distribution_title": "heading for a 'Rating distribution' table",
 "distribution_header": ["'Rating'", "'% of coverage'", "'% investment banking clients'"],
 "contact_title": "heading 'Research contacts'", "registered_office": "label 'Registered office'"}}"""

def one(lang):
    import os
    if os.path.exists(f"/data/synthdog-doc/content/{lang}/disclosures.jsonl"):
        return lang, "exists", ""
    L = LANGS[lang]
    text, _ = llm.call(MODEL, PROMPT.format(lname=L.name, countries=", ".join(L.countries)),
                       max_tokens=6000, effort="low", timeout=400)
    try:
        obj = llm.extract_json(text)
    except ValueError:
        return lang, "FAIL", ""
    obj["_lang"] = lang
    with open(f"/data/synthdog-doc/content/{lang}/disclosures.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return lang, len(obj.get("sections") or []), (obj.get("ratings") or [[""]])[0][0]

with ThreadPoolExecutor(10) as ex:
    for r in ex.map(one, SEL):
        print(*r, flush=True)

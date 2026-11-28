"""One-off: localized book imprint (copyright page) strings per language -> content/<lang>/imprint.jsonl"""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))
from synthdog_doc import llm
from synthdog_doc.langs import LANGS, LANG_ORDER
SEL = [x for x in os.environ.get('SDD_LANGS', ','.join(LANG_ORDER)).split(',') if x]  # languages to run
MODEL = os.environ.get('SDD_LLM', 'gpt-6.1-sol')

PROMPT = """Write the standard boilerplate found on the copyright (imprint) page of a book published in {lname}
({countries}). Return ONLY JSON with these keys, all values written natively in {lname} (no English):
{{"rights": "the full 'All rights reserved. No part of this publication may be reproduced ... without the prior
   written permission of the publisher.' paragraph as it is typically printed in {lname} books (1-2 sentences)",
 "first_edition": "phrase for 'First edition' (as printed, e.g. with the year placeholder {{year}})",
 "nth_edition": "phrase for 'N-th edition' with placeholders {{n}} and {{year}}",
 "printed_in": "phrase 'Printed in {{country}}' with placeholder {{country}}",
 "countries": ["the country names (in {lname}) of {countries}"],
 "cover_design": "label for 'Cover design'", "typesetting": "label for 'Typesetting'",
 "editor": "label for 'Editor'", "printing": "label for 'Printing'",
 "cip": "heading for the library cataloguing-in-publication data block",
 "translated_from": "phrase 'Translated from {{language}}' with placeholder {{language}}"}}"""

def one(lang):
    L = LANGS[lang]
    text, _ = llm.call(MODEL, PROMPT.format(lname=L.name, countries=", ".join(L.countries)),
                       max_tokens=3000, effort="low", timeout=300)
    obj = llm.extract_json(text)
    obj["_lang"] = lang
    with open(f"/data/synthdog-doc/content/{lang}/imprint.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return lang, obj.get("rights", "")[:80]

with ThreadPoolExecutor(10) as ex:
    for lang, r in ex.map(one, SEL):
        print(lang, r)

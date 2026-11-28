"""One-off: extra localized UI strings for v3 templates -> content/<lang>/locale_x.jsonl (merged by corpus.locale)."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))
from synthdog_doc import llm
from synthdog_doc.langs import LANGS, LANG_ORDER
SEL = [x for x in os.environ.get('SDD_LANGS', ','.join(LANG_ORDER)).split(',') if x]  # languages to run
MODEL = os.environ.get('SDD_LLM', 'gpt-6.1-sol')

KEYS = ["[report] Key charts", "[report] Company", "[report] Median", "[report] Peer comparison",
        "[report] Terminal growth", "[report] Rating distribution",
        "[magazine] Interview by", "[magazine] Photos", "[magazine] Text", "[magazine] Photo essay",
        "[magazine] Reading time", "[magazine] min (minutes, abbreviation)", "[magazine] Advertisement",
        "[textbook] Chapter review", "[textbook] Fill in the blanks", "[textbook] True or false",
        "[textbook] Match the columns", "[textbook] Page", "[textbook] Concept map", "[textbook] Key points",
        "[exam] Answer", "[exam] Marks", "[exam] Time allowed", "[book] Contents", "[book] Page",
        "[general] Continued"]
PROMPT = """Translate these short UI labels for printed documents into {lname} as they are actually printed in
{countries} (school textbooks, magazines, equity research reports, exam papers, books). Keep each label short,
natural and idiomatic (not a literal translation), in the local script. Return ONLY a JSON object mapping each
key exactly as given to its label: {keys}"""

def one(lang):
    out = f"/data/synthdog-doc/content/{lang}/locale_x.jsonl"
    if os.path.exists(out):
        return lang, "exists"
    L = LANGS[lang]
    text, _ = llm.call(MODEL, PROMPT.format(lname=L.name, countries=", ".join(L.countries),
                                                    keys=json.dumps(KEYS, ensure_ascii=False)),
                       max_tokens=3000, effort="low", timeout=300)
    try:
        obj = llm.extract_json(text)
    except ValueError:
        return lang, "FAIL"
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({"strings": obj, "_lang": lang}, ensure_ascii=False) + "\n")
    return lang, obj.get("[report] Peer comparison")

for _ in range(2):
    with ThreadPoolExecutor(10) as ex:
        for r in ex.map(one, SEL):
            print(*r, flush=True)

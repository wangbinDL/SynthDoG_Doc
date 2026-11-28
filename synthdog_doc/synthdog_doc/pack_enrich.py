"""Second-pass LLM enrichment of content packs for internal consistency (judge round-1 feedback).

paper  -> journal name matching the discipline, publication year after the latest cited year, received/accepted
          dates, acknowledgments, author emails, equation placement with lead-in sentences, numeric data for every
          figure consistent with the text, table units.
report -> coherent financial table (unit, currency, years, values consistent with the prose), price history,
          52-week range bracketing the current price, market cap consistent with shares x price, chart data.
  python3 -m synthdog_doc.pack_enrich --kind paper --workers 12
Writes <content>/<lang>/<kind>_x.jsonl (same _idx as the source pack).
"""
import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import llm
from .langs import LANG_ORDER, LANGS

CONTENT = Path("/data/synthdog-doc/content")

PAPER_X = """Below is a {lname} academic paper draft (JSON). Make its publication metadata and quantitative details
internally consistent. Return ONLY a JSON object (all prose in {lname}):
{{"journal": "a plausible {lname}-language journal title that matches the paper's discipline (not a different field)",
 "publisher_line": "short publisher / university press line",
 "year": publication year (integer, >= the latest year cited in the text/references, <= 2026),
 "volume": integer, "issue": integer, "first_page": integer,
 "received": "date string in {lname} conventions, before accepted", "accepted": "date string",
 "doi": "10.xxxx/xxxxx style DOI",
 "emails": [one plausible institutional e-mail per author, using realistic university domains of {countries}],
 "acknowledgments": "1-2 sentences of genuine acknowledgments/funding for THIS study",
 "equation_placement": [{{"eq": index into equations, "section": section index, "after_paragraph": paragraph index
     within that section, "lead_in": "short sentence fragment introducing the equation, ending with ':' or ','",
     "follow_up": "short sentence starting with the local equivalent of 'where' that defines the symbols"}}],
 "figure_data": [{{"fig": index into figures, "kind": "bar"|"line"|"scatter"|"pie", "x_label": "...",
     "y_label": "... with unit", "categories": [...], "series": [{{"name": "...", "values": [numbers]}}],
     "section": section index where it is first referenced, "mention": "short sentence referencing the figure
     by number (e.g. 'Figure 1 shows ...'), consistent with the plotted values"}}],
 "table_units": [{{"table": index into tables, "unit_note": "note with units/abbreviations"}}]}}
Rules: figure values must match numbers stated in the text; never plot quantities with different units on one axis;
keep values physically plausible.

PAPER JSON:
{pack}"""

REPORT_X = """Below is a {lname} equity research report draft (JSON). Produce coherent numbers for its exhibits.
Return ONLY a JSON object (labels in {lname}):
{{"currency": "currency code/symbol used in {countries}", "unit_label": "e.g. 'million' in {lname}",
 "current_price": number, "target_price": number, "upside_pct": number,
 "week52_low": number, "week52_high": number (must bracket current_price),
 "shares_outstanding_mn": number, "market_cap_mn": number (= shares x price), "free_float_pct": number,
 "years": ["2022A","2023A","2024A","2025E","2026E"] (A=actual, E=estimate; consistent with the prose),
 "fin_rows": [{{"name": "{lname} line item", "values": [numbers per year], "kind": "abs"|"pct"|"ratio"|"per_share"}}]
   (8-10 rows: revenue, growth %, gross profit, EBITDA, margin %, net profit, EPS, P/E, ROE %, dividend yield %;
    absolute rows in the stated unit, percentages only in 'pct' rows; values must agree with the prose),
 "price_history": {{"labels": 12 month labels in {lname}, "values": 12 prices ending near current_price}},
 "charts": [{{"title": "{lname} chart title", "kind": "bar"|"line", "categories": [...],
   "series": [{{"name": "...", "values": [numbers]}}], "y_label": "... with unit"}}] (2-3, consistent with fin_rows),
 "source_line": "Source: ... (in {lname})"}}

REPORT JSON:
{pack}"""

_lock = threading.Lock()


def job(kind, lang, pack, model, effort):
    L = LANGS[lang]
    slim = {k: v for k, v in pack.items() if not k.startswith("_")}
    tpl = PAPER_X if kind == "paper" else REPORT_X
    prompt = tpl.format(lname=L.name, countries=", ".join(L.countries),
                        pack=json.dumps(slim, ensure_ascii=False)[:24000])
    text, meta = llm.call(model, prompt, max_tokens=12000, effort=effort, timeout=900)
    obj = llm.extract_json(text)
    if isinstance(obj, list):
        obj = next((x for x in obj if isinstance(x, dict)), {})
    obj["_idx"] = pack["_idx"]
    obj["_lang"] = lang
    with _lock:
        with open(CONTENT / lang / f"{kind}_x.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return lang, pack["_idx"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["paper", "report"], required=True)
    ap.add_argument("--langs", default=",".join(LANG_ORDER))
    ap.add_argument("--model", default="gpt-6.1-sol")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    jobs = []
    for lang in a.langs.split(","):
        src = CONTENT / lang / f"{a.kind}.jsonl"
        if not src.exists():
            continue
        dst = CONTENT / lang / f"{a.kind}_x.jsonl"
        done = {json.loads(x)["_idx"] for x in dst.read_text().splitlines()} if dst.exists() else set()
        for line in src.read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            if p["_idx"] not in done:
                jobs.append((lang, p))
                done.add(p["_idx"])
    print("jobs", len(jobs), flush=True)
    ok = fail = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(job, a.kind, l, p, a.model, a.effort): (l, p["_idx"]) for l, p in jobs}
        for f in as_completed(futs):
            try:
                f.result()
                ok += 1
                if ok % 20 == 0:
                    print("OK", ok, flush=True)
            except Exception as e:  # noqa: BLE001
                fail += 1
                print("FAIL", futs[f], repr(e)[:200], flush=True)
    print(f"ENRICH_DONE ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()

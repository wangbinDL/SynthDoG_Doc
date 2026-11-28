"""LLM-generated content pools (run once per language, cached as JSONL under <out>/<lang>/).

Kinds:
  locale : localized UI strings / names for templates (one JSON object)
  paper  : academic paper packs (title, authors, abstract, sections with inline math + citations, equations,
           figure/table captions, small result tables, references)
  exam   : exam packs (header + 10-14 questions of mixed types, with LaTeX where natural)
  ppt    : slide decks (8-10 slides of typed layouts)
  report : equity/industry research report packs
  lesson : textbook lesson packs
Grounding: each pack prompt includes a short excerpt of national-web / Wikipedia text in the same language
as topical seed, so packs inherit real topics from the language's own web.
"""
import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import llm
from .langs import LANG_ORDER, LANGS

LOCALE_KEYS = {
    "paper": ["Abstract", "Keywords", "Introduction", "Related Work", "Methods", "Materials and Methods",
              "Experiments", "Results", "Discussion", "Conclusion", "References", "Acknowledgments",
              "Figure (abbrev. used in captions, e.g. 'Fig.')", "Table", "Equation", "Appendix",
              "et al.", "Received", "Accepted", "Published online", "Corresponding author", "E-mail",
              "Department of", "University", "Faculty of", "Vol.", "No.", "pp.", "Page", "Preprint",
              "Journal", "Proceedings of the", "Conference", "doi", "Copyright notice short", "Article"],
    "exam": ["School", "Exam (generic word)", "Final Examination", "Mid-term Examination", "Mock Examination",
             "Unit Test", "Board Examination (national/state exam)", "Subject", "Mathematics", "Physics",
             "Chemistry", "Biology", "History", "Geography", "Language and Literature (native language)",
             "Economics", "Computer Science", "Social Studies", "Time allowed", "hours", "minutes",
             "Maximum marks", "Marks", "Name", "Class/Grade", "Section (class section)", "Roll number",
             "Date", "Signature of invigilator", "General instructions", "Answer all questions",
             "Choose the correct answer", "Fill in the blanks", "True or False", "Match the following",
             "Short answer questions", "Long answer questions", "Section A", "Section B", "Section C",
             "Part I", "Part II", "Question", "Answer", "Page {x} of {y}", "Turn over", "Do not write in this margin",
             "Rough work", "Total", "Score", "Grader", "Examiner", "Code", "Set", "Reading comprehension",
             "Read the passage and answer the questions", "Show your work", "Use of calculator is (not) allowed",
             "End of question paper"],
    "news": ["National", "International", "World", "Economy", "Business", "Sports", "Culture", "Opinion",
             "Editorial", "Politics", "Science", "Health", "Technology", "Education", "Weather", "Classifieds",
             "Local", "Entertainment", "Front page", "Continued on page", "Price", "Edition", "Year", "Issue",
             "Founded", "Reporter (byline word)", "By (byline prefix)", "Photo", "Correspondent",
             "Editor-in-chief", "Pages", "Today", "Inside", "Read more", "Advertisement", "Subscribe",
             "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January", "February",
             "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "magazine": ["Cover story", "Interview", "Feature", "Analysis", "Portrait", "Travel", "Lifestyle", "Review",
                 "Column", "Special report", "In this issue", "Monthly", "Weekly", "Subscribe now"],
    "book": ["Chapter", "Part", "Preface", "Contents", "Introduction", "Epilogue", "Notes", "Bibliography",
             "Index", "Translated by", "Edition"],
    "textbook": ["Unit", "Lesson", "Chapter", "Learning objectives", "Activity", "Exercise", "Exercises",
                 "Did you know?", "Key words", "Let's practice", "Remember", "Summary", "Think and answer",
                 "Project work", "Example", "Solution", "Note", "Group work", "Homework", "Review questions",
                 "Glossary", "Let's learn", "Observe and discuss", "Experiment"],
    "report": ["Equity Research", "Company Report", "Industry Report", "Macro Strategy", "Rating", "Buy",
               "Accumulate", "Hold", "Reduce", "Sell", "Overweight", "Neutral", "Target price", "Current price",
               "Market capitalization", "52-week range", "Shares outstanding", "Free float", "Analyst",
               "Investment highlights", "Key risks", "Valuation", "Financial summary", "Revenue", "Net profit",
               "Gross margin", "EBITDA", "EPS", "P/E", "P/B", "ROE", "Dividend yield", "Source", "Note",
               "Disclaimer", "Important disclosures at the end of this report", "Please read the disclaimer",
               "Fiscal year", "estimate (abbrev. like 2025E)", "million", "billion", "Year-on-year", "Quarter",
               "Price performance", "Index", "Sector", "Company data", "Forecast"],
    "ppt": ["Agenda", "Overview", "Background", "Objectives", "Methodology", "Results", "Key findings",
            "Next steps", "Conclusion", "Thank you", "Questions?", "Q&A", "Contents", "Case study", "Timeline",
            "Recommendations", "Summary", "Appendix", "Confidential"],
    "common": ["Source", "Note", "Total", "Average", "Other", "Yes", "No", "and", "or", "page", "see", "Fig.",
               "Tab.", "continued", "Continued", "Contact", "Address", "Phone", "Website"],
}

LOCALE_PROMPT = """You are a native {lname} ({native}) typesetter and editor from {countries}.
Produce a JSON object that localizes UI strings used on printed documents (papers, exams, newspapers,
magazines, books, textbooks, equity research reports, slides) for {lname}.

Rules:
- Use the conventions actually printed in {countries} (not word-for-word translation). Keep them short.
- Output digits as Western 0-9 (the renderer converts digits when needed).
- Keep placeholders like {{x}} and {{y}} unchanged.
- Additionally provide name lists that look natural in {countries}:
  "person_first": 40 common first names (mixed gender), "person_last": 40 common surnames,
  "cities": 25 cities/towns, "universities": 15 plausible university names (real-style, may be real),
  "institutes": 10 research institute names, "schools": 15 secondary school names,
  "newspapers": 12 plausible newspaper titles (fictional but natural), "magazines": 10 magazine titles,
  "journals": 12 academic journal titles in {lname}, "publishers": 8 publisher names,
  "brokers": 8 brokerage / securities firm names (fictional), "companies": 20 company names (fictional, with sector),
  "orgs": 10 organization/department names for slide decks,
  "exam_boards": 6 names of exam-setting bodies typical in {countries} (may be real),
  "option_labels": the 4 labels used for multiple-choice options in exams in {countries} (e.g. ["A","B","C","D"]
    or native letters), "option_labels_alt": an alternative set,
  "list_markers": common enumerators for sub-questions (e.g. ["a)","b)","c)","d)"]),
  "quote_open"/"quote_close": primary quotation marks, "decimal_sep", "thousands_sep",
  "date_format_example": today's date written as on a newspaper masthead (use 27 November 2026, Friday).
Return JSON with top-level keys: "strings" (object mapping each English key below to its localization),
and the list/scalar keys above. English keys:
{keys}
Return only JSON."""

PAPER_PROMPT = """Write realistic academic-paper content in {lname} ({native}) as typically published by journals and
universities in {countries}. Discipline: {disc}. Topic seed (real {lname} text, use only for inspiration):
<<<{seed}>>>

Return ONE JSON object:
{{"title": str, "authors": [5 names natural for {countries}], "affiliations": [2-3 strings],
 "abstract": str (120-200 words), "keywords": [4-6],
 "sections": [ {{"heading": str (no number), "paragraphs": [str,...], "subsections": [{{"heading": str, "paragraphs": [str,...]}}]}} ] (4-6 sections),
 "equations": [{{"latex": str (KaTeX-compatible display math, no $), "after_paragraph_hint": str}}] (3-6, {eqnote}),
 "figures": [{{"caption": str, "kind": one of ["bar","line","scatter","pie","photo","diagram"],
              "series_names": [1-3 short], "x_label": str, "y_label": str, "categories": [3-7 short labels]}}] (2-3),
 "tables": [{{"caption": str, "header": [3-6 short], "rows": [[...],...] (4-8 rows; numbers as strings, may use ±)}}] (1-2),
 "references": [10-16 reference entries formatted in a common citation style used in {countries}]}}
Requirements: paragraphs 60-160 words each, total body 1400-2200 words; use citation markers like [3] or (Author, 2021)
consistently; include some inline math as $...$ where natural; real terminology of the discipline in {lname};
no markdown, no English unless it is a standard term. Return only JSON.
Never state or imply that the company, study, data or results are fictional, hypothetical, simulated or illustrative; write as the real publication would.
"""

EXAM_PROMPT = """Create a realistic school/university exam paper content in {lname} ({native}) as used in {countries}.
Level: {level}. Subject: {subject}. Exam style should follow local conventions (headers, numbering, marks).
Topic seed (real {lname} text for inspiration of names/places, optional): <<<{seed}>>>

Return ONE JSON object:
{{"exam_title": str, "institution": str, "subject": str, "level": str, "duration_minutes": int, "max_marks": int,
 "instructions": [3-6 short instructions],
 "sections": [ {{"title": str, "instruction": str, "marks_each": int,
   "questions": [ {{"type": one of ["mcq","fill","truefalse","short","long","calc","match","passage"],
                  "stem": str (may contain inline LaTeX $...$ for math/science),
                  "options": [4 strings] (mcq only, similar lengths),
                  "pairs": [[left,right],...] (match only, 4-5 pairs),
                  "passage": str (passage only, 120-220 words) , "subquestions": [str,...] (passage/long/calc, 2-4),
                  "marks": int, "has_figure": bool, "figure_kind": one of ["geometry","graph","circuit","table","map","none"]}} ] }} ]
 }}
Total 12-18 questions across 2-4 sections with a natural mix for the subject. {mathnote}
Write everything in {lname}; numbers as Western digits. Return only JSON."""

PPT_PROMPT = """Create the text content of a real-looking slide deck in {lname} ({native}) from {countries}.
Context: {context}. Topic seed (real {lname} text, inspiration only): <<<{seed}>>>

Return ONE JSON object:
{{"deck_title": str, "subtitle": str, "presenter": str, "organization": str, "date": str,
 "slides": [ 9-11 slides, each one of:
   {{"layout":"title"}},
   {{"layout":"agenda","title":str,"items":[4-6 short]}},
   {{"layout":"bullets","title":str,"bullets":[{{"text":str (5-16 words),"sub":[0-2 short]}}] (3-6)}},
   {{"layout":"two_column","title":str,"left_title":str,"left":[3-4 short],"right_title":str,"right":[3-4 short]}},
   {{"layout":"chart","title":str,"chart":"bar|line|pie|column","categories":[3-6],"series":[{{"name":str,"values":[numbers]}}] (1-3),"takeaway":str}},
   {{"layout":"table","title":str,"header":[3-5],"rows":[[...]] (3-6 rows),"note":str}},
   {{"layout":"process","title":str,"steps":[{{"label":str (1-3 words),"desc":str (4-10 words)}}] (3-5)}},
   {{"layout":"kpi","title":str,"kpis":[{{"value":str,"label":str}}] (3-4)}},
   {{"layout":"quote","quote":str,"author":str}},
   {{"layout":"image_text","title":str,"text":str (25-50 words),"caption":str}},
   {{"layout":"section","title":str,"subtitle":str}},
   {{"layout":"formula","title":str,"latex":[1-3 KaTeX formulas],"bullets":[1-3 short]}} (only if topic is technical),
   {{"layout":"closing","title":str,"contact":str}} ]}}
Use short presentation phrases (not paragraphs). Everything in {lname}. Return only JSON."""

REPORT_PROMPT = """Write the content of a sell-side equity/industry research report in {lname} ({native}) as published
by brokers in {countries}. Company/industry: invent a plausible listed company in sector "{sector}".
Topic seed (real {lname} business news, inspiration only): <<<{seed}>>>

Return ONE JSON object:
{{"broker": str (fictional), "report_type": str, "title": str (headline-like, 6-14 words), "company": str,
 "ticker": str, "exchange": str, "sector": str, "rating": str, "target_price": str, "current_price": str,
 "currency": str, "analysts": [2 names with email-like handles],
 "highlights": [4-6 bullet sentences 15-35 words],
 "sections": [{{"heading": str, "paragraphs": [2-3 paragraphs 60-120 words]}}] (3-4),
 "risks": [3-4 short],
 "fin_rows": [6-10 financial line item names in {lname}],
 "chart_titles": [3-4 short chart titles],
 "disclaimer": str (100-160 words)}}
Everything in {lname}. Return only JSON.
Never state or imply that the company, study, data or results are fictional, hypothetical, simulated or illustrative; write as the real publication would.
"""

LESSON_PROMPT = """Write one textbook lesson in {lname} ({native}) for {level} students in {countries}. Subject: {subject}.
Topic seed (real {lname} text, inspiration only): <<<{seed}>>>
Return ONE JSON object:
{{"unit_title": str, "lesson_title": str, "objectives": [3-5], "intro": str (50-90 words),
 "sections": [{{"heading": str, "paragraphs": [1-3 paragraphs 40-110 words], "key_terms": [0-3]}}] (2-4),
 "did_you_know": str (25-50 words), "activity": {{"title": str, "steps": [3-5 short]}},
 "example": {{"problem": str, "solution": str}} (math/science may use $...$ LaTeX),
 "exercises": [5-8 short questions], "image_captions": [2-3 short]}}
Everything in {lname}. Return only JSON."""

FEATURE_PROMPT = """Write a long magazine feature article in {lname} ({native}) for a {lname}-language {mag_kind}
magazine published in {countries}. Topic seed (real {lname} text, inspiration only): <<<{seed}>>>
Style: {style}. Write natively in {lname} (not translated), with concrete local details.
Return ONE JSON object:
{{"section": short section name, "kicker": "1-3 words", "title": "6-12 words", "deck": "1-2 sentence standfirst",
 "author": "name natural for {countries}", "author_role": "e.g. staff writer / correspondent",
 "format": "{fmt}",
 "sections": [{{"heading": "short subheading", "paragraphs": [2-4 paragraphs of 60-140 words]}}] (4-6 sections;
     for an interview, headings may be empty and paragraphs alternate "Q:" questions and answers using the local
     labels for interviewer/interviewee),
 "pull_quotes": [2 short striking sentences copied verbatim from the paragraphs],
 "sidebar": {{"title": "fact box title", "items": [4-6 short facts with numbers]}},
 "photo_topic": one of ["people","crowd","politics","sports","business","industry","health","science","technology",
   "nature","city","building","transport","food","education","culture","agriculture","weather","religion"],
 "photo_brief": "what the main photo should show (generic)"}}
Total 1500-2400 words. Return only JSON."""

ADS_PROMPT = """Create 30 realistic print advertisements for {lname}-language newspapers and magazines in {countries}.
Mix: retail sale, bank/loan, mobile phone plan, real estate, private school/coaching, clinic/hospital, car dealer,
travel agency, furniture, electronics, restaurant, job vacancy, government notice/tender, matrimonial/classified
(where culturally normal), event/concert.
Return ONLY JSON: {{"ads": [{{"kind": "...", "brand": "fictional but natural brand", "headline": "2-6 words",
  "tagline": "short slogan", "offer": "price/discount/offer line with numbers and local currency",
  "details": ["2-4 short lines: address/area, opening hours, conditions"], "phone": "local-format phone number",
  "web": "plausible web address or empty"}}]}}
All text in {lname} except web addresses."""

FEATURE_STYLES = [("news/current affairs weekly", "long-form reportage with quotes from people on the ground", "feature"),
                  ("business monthly", "analysis with numbers and expert quotes", "feature"),
                  ("lifestyle and culture magazine", "colourful, personal, descriptive", "feature"),
                  ("science and technology magazine", "explanatory journalism", "feature"),
                  ("sports magazine", "portrait of an athlete or team", "portrait"),
                  ("news weekly", "question-and-answer interview with a public figure", "interview"),
                  ("travel magazine", "destination report", "feature"),
                  ("health magazine", "service journalism with practical tips", "feature")]

DISCIPLINES = ["physics", "computer science", "economics", "medicine", "biology", "chemistry", "civil engineering",
               "linguistics", "sociology", "mathematics", "environmental science", "education", "agriculture",
               "electrical engineering", "psychology", "history"]
EXAM_SUBJECTS = [("Mathematics", "secondary school final year"), ("Physics", "secondary school"),
                 ("Chemistry", "secondary school"), ("Biology", "secondary school"),
                 ("native language and literature", "secondary school"), ("History", "secondary school"),
                 ("Geography", "secondary school"), ("Mathematics", "university first year"),
                 ("Economics", "high school"), ("Mathematics", "middle school"), ("Science", "middle school"),
                 ("Computer Science", "high school"), ("Social Studies", "primary school grade 5"),
                 ("English as a foreign language", "secondary school")]
PPT_CONTEXTS = ["university lecture", "company quarterly business review", "government policy briefing",
                "school class presentation", "research group meeting", "startup pitch", "NGO project report",
                "hospital training session", "marketing plan", "engineering design review", "conference talk",
                "teacher training workshop"]
SECTORS = ["banking", "telecommunications", "consumer goods", "energy", "pharmaceuticals", "automobiles",
           "information technology", "real estate", "retail", "agriculture", "steel and mining", "aviation",
           "insurance", "renewable energy", "food and beverages", "logistics"]
LESSON_SUBJECTS = [("Science", "grade 6"), ("Geography", "grade 7"), ("Mathematics", "grade 8"),
                   ("History", "grade 6"), ("Biology", "grade 9"), ("Civics", "grade 8"),
                   ("Environmental studies", "grade 4"), ("Physics", "grade 10"), ("Chemistry", "grade 9"),
                   ("Language", "grade 5")]


def load_seeds(corpus_dir, lang, kind, n, rng):
    """Short real-text excerpts from the language's corpus as topical seeds."""
    seeds = []
    for fn in (["web.jsonl"] if kind == "news" else ["wiki.jsonl", "web.jsonl"]):
        p = Path(corpus_dir) / lang / fn
        if not p.exists():
            continue
        rows = p.read_text(encoding="utf-8").splitlines()
        rng.shuffle(rows)
        for line in rows[: n * 3]:
            d = json.loads(line)
            if "sections" in d:
                paras = [x for s in d["sections"] for x in s["paras"]]
                head = d.get("title", "")
            else:
                paras = d.get("paras", [])
                head = d.get("title", "")
            if paras:
                txt = (head + ". " + " ".join(paras))[:900]
                seeds.append(txt)
    rng.shuffle(seeds)
    return seeds[:n] if seeds else [""] * n


def job_list(lang, counts, corpus_dir, seed=7):
    rng = random.Random(f"{seed}-{lang}")
    L = LANGS[lang]
    ctx = dict(lname=L.name, native=L.native, countries=", ".join(L.countries))
    jobs = []
    if counts.get("locale"):
        keys = "\n".join(f"- [{grp}] {k}" for grp, ks in LOCALE_KEYS.items() for k in ks)
        jobs.append(("locale", 0, LOCALE_PROMPT.format(keys=keys, **ctx)))
    seeds = load_seeds(corpus_dir, lang, "any", 400, rng)
    news = load_seeds(corpus_dir, lang, "news", 200, rng)
    si = 0

    def nxt(pool):
        nonlocal si
        si += 1
        return pool[si % len(pool)] if pool else ""
    for i in range(counts.get("paper", 0)):
        disc = DISCIPLINES[i % len(DISCIPLINES)]
        eqnote = ("formulas central to the method" if disc in ("physics", "mathematics", "computer science",
                  "electrical engineering", "economics", "chemistry", "civil engineering") else
                  "statistical formulas such as regression or test statistics")
        jobs.append(("paper", i, PAPER_PROMPT.format(disc=disc, eqnote=eqnote, seed=nxt(seeds), **ctx)))
    for i in range(counts.get("exam", 0)):
        subj, level = EXAM_SUBJECTS[i % len(EXAM_SUBJECTS)]
        mathnote = ("Use LaTeX $...$ for all formulas; include calculation and geometry questions."
                    if subj in ("Mathematics", "Physics", "Chemistry", "Science", "Economics") else "")
        jobs.append(("exam", i, EXAM_PROMPT.format(level=level, subject=subj, mathnote=mathnote,
                                                   seed=nxt(news), **ctx)))
    for i in range(counts.get("ppt", 0)):
        jobs.append(("ppt", i, PPT_PROMPT.format(context=PPT_CONTEXTS[i % len(PPT_CONTEXTS)], seed=nxt(seeds),
                                                 **ctx)))
    for i in range(counts.get("report", 0)):
        jobs.append(("report", i, REPORT_PROMPT.format(sector=SECTORS[i % len(SECTORS)], seed=nxt(news), **ctx)))
    for i in range(counts.get("feature", 0)):
        mk, st, fmt = FEATURE_STYLES[i % len(FEATURE_STYLES)]
        jobs.append(("feature", i, FEATURE_PROMPT.format(mag_kind=mk, style=st, fmt=fmt, seed=nxt(news), **ctx)))
    for i in range(counts.get("ads", 0)):
        jobs.append(("ads", i, ADS_PROMPT.format(**ctx)))
    for i in range(counts.get("lesson", 0)):
        subj, level = LESSON_SUBJECTS[i % len(LESSON_SUBJECTS)]
        jobs.append(("lesson", i, LESSON_PROMPT.format(subject=subj, level=level, seed=nxt(seeds), **ctx)))
    return jobs


_lock = threading.Lock()


def run(out_dir, langs, counts, model, effort, workers, corpus_dir, key="main"):
    out_dir = Path(out_dir)
    all_jobs = []
    for lang in langs:
        (out_dir / lang).mkdir(parents=True, exist_ok=True)
        done = set()
        for kind in ("locale", "paper", "exam", "ppt", "report", "lesson", "feature", "ads"):
            p = out_dir / lang / f"{kind}.jsonl"
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    try:
                        d = json.loads(line)
                        done.add((kind, d["_idx"]))
                    except Exception:  # noqa: BLE001
                        pass
        for kind, idx, prompt in job_list(lang, counts, corpus_dir):
            if (kind, idx) not in done:
                all_jobs.append((lang, kind, idx, prompt))
    korder = {"locale": 0, "paper": 1, "exam": 2, "ppt": 3, "report": 4, "lesson": 5, "feature": 6, "ads": 7}
    lorder = {lg: i for i, lg in enumerate(langs)}
    # round-robin: every language/kind gets early items first, so partial pools are usable quickly
    all_jobs.sort(key=lambda j: (j[2] if j[1] != "locale" else -1, korder[j[1]], lorder[j[0]]))
    print(f"jobs pending: {len(all_jobs)}", flush=True)

    def work(job):
        lang, kind, idx, prompt = job
        t = time.time()
        text, meta = llm.call(model, prompt, max_tokens=20000, effort=effort, key=key, timeout=1200)
        try:
            obj = llm.extract_json(text)
        except ValueError:
            (out_dir / lang / f"_fail_{kind}_{idx}.txt").write_text(
                json.dumps(meta, ensure_ascii=False) + "\n" + text, encoding="utf-8")
            raise
        if isinstance(obj, list):
            obj = {"items": obj}
        obj["_idx"] = idx
        obj["_model"] = meta.get("model")
        obj["_usage"] = meta.get("usage")          # token accounting for the cost model
        obj["_lang"] = lang
        with _lock:
            with open(out_dir / lang / f"{kind}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        return lang, kind, idx, round(time.time() - t, 1), meta.get("usage", {}).get("completion_tokens")

    ok = fail = 0
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(work, j): j for j in all_jobs}
        for f in as_completed(futs):
            j = futs[f]
            try:
                r = f.result()
                ok += 1
                print("OK", *r, flush=True)
            except Exception as e:  # noqa: BLE001
                fail += 1
                print("FAIL", j[0], j[1], j[2], repr(e)[:300], flush=True)
    print(f"DONE ok={ok} fail={fail}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/data/synthdog-doc/content")
    ap.add_argument("--corpus", default="/data/synthdog-doc/corpus")
    ap.add_argument("--langs", default=",".join(LANG_ORDER))
    ap.add_argument("--model", default="gpt-6.1-sol")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--key", default="main")
    ap.add_argument("--locale", type=int, default=1)
    ap.add_argument("--paper", type=int, default=30)
    ap.add_argument("--exam", type=int, default=36)
    ap.add_argument("--ppt", type=int, default=30)
    ap.add_argument("--report", type=int, default=20)
    ap.add_argument("--lesson", type=int, default=24)
    ap.add_argument("--feature", type=int, default=0)
    ap.add_argument("--ads", type=int, default=0)
    a = ap.parse_args()
    counts = dict(locale=a.locale, paper=a.paper, exam=a.exam, ppt=a.ppt, report=a.report, lesson=a.lesson,
                  feature=a.feature, ads=a.ads)
    run(a.out, a.langs.split(","), counts, a.model, a.effort, a.workers, a.corpus, a.key)


if __name__ == "__main__":
    sys.exit(main())

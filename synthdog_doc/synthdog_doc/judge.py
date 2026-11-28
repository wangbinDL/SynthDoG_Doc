"""VLM judging protocol (Opus 5.5 + GPT-6.1-Sol).

Three task types, all blind (file names hidden, real/synthetic mixed):
  single : one page (downscaled full view + one native-resolution text crop). Judge says real vs synthetic,
           confidence, scores (layout realism / typography / locale conventions / overall 1-5) and a structured
           flaw list (region, issue_type, severity, evidence, fix).
  grid   : 4x4 contact sheet of 16 pages of one document type -> diversity score 1-5, #distinct templates,
           repeated motifs, missing structures.
  pair   : two pages of the same type/language side by side (versions A/B, order randomized) -> which one looks
           more like a real document, with reasons.
Outputs JSONL with raw responses for auditability.
"""
import argparse
import hashlib
import io
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

from . import llm

JUDGES = {"opus": ("claude-opus-5-5-pretrain", "medium"), "sol": ("gpt-6.1-sol", "medium")}
TMP = Path("/data/synthdog-doc/judge_tmp")

SINGLE_PROMPT = """You are a forensic document examiner and an expert typographer for {lname} ({script}) printed documents.
You will see ONE document page image (first image: whole page, downscaled; second image: a crop at native
resolution from the same page). The page is either a REAL scanned/exported document page or a SYNTHETIC page
rendered by a document generator. The expected document genre is: {genre}.

Judge it critically and independently. Look for: layout logic and grid, typographic hierarchy, fonts and
shaping of {script}, line breaking/hyphenation/justification, reading flow, page furniture (headers, folios,
captions), content coherence (do headings, captions, figures and text belong together), local conventions of
{lname}-speaking countries (numerals, punctuation, quotation marks, labels), image/figure plausibility, and
imaging artifacts.

Return ONLY a JSON object:
{{"verdict": "real" | "synthetic", "confidence": 0-100,
  "scores": {{"layout_realism": 1-5, "typography": 1-5, "locale_conventions": 1-5, "content_coherence": 1-5,
             "overall_realism": 1-5}},
  "flaws": [{{"region": "e.g. top header / left column middle / figure 2 caption", "issue_type": one of
             ["layout","typography","shaping","line_breaking","locale","content","figure","table","math",
              "furniture","imaging","other"], "severity": "minor" | "major" | "blocker",
             "evidence": "what exactly you see", "fix": "concrete change to make it look real"}}],
  "strengths": ["..."],
  "summary": "one or two sentences"}}
Scoring anchors: 1 = unusable / clearly broken; 2 = several obvious violations of genre or local conventions;
3 = recognizable genre but recurring noticeable problems; 4 = normal real-world quality with minor issues;
5 = indistinguishable from a professionally produced real document.
List at most 8 flaws, most important first. If you think the page is real, still list any flaws you see."""

GRID_PROMPT = """You are reviewing the DIVERSITY of a set of document page images of genre "{genre}". The image is a
4x4 contact sheet of 16 pages (they may be in different languages). Real collections of this genre show many
different publishers/templates, page roles, grids, color schemes and content.

Return ONLY a JSON object:
{{"diversity_score": 1-5, "estimated_distinct_templates": integer,
  "largest_repeated_cluster": {{"size": integer, "shared_features": "..."}},
  "repeated_motifs": ["..."], "missing_structures": ["layouts/components real {genre} pages have that are absent"],
  "realism_of_set": 1-5, "top_recommendations": ["concrete changes to increase realistic diversity"]}}
Anchors: 1 = >50% look like the same template; 3 = 3-4 template families clearly recurring; 5 = looks like 16
pages collected from 16 different real sources."""

PAIR_PROMPT = """Two document page images of genre "{genre}" in {lname} are shown: image 1 = page A, image 2 = page B.
Which page looks more like a REAL professionally produced document (not synthetic)? Consider layout, typography,
{script} shaping, local conventions, content coherence and imaging. Return ONLY JSON:
{{"winner": "A" | "B" | "tie", "confidence": 0-100, "reasons": ["..."], "A_main_problem": "...", "B_main_problem": "..."}}"""

SIGNOFF_PROMPT = """You are one of two senior reviewers deciding whether a synthetic document generator is good enough
to produce TRAINING DATA for multilingual document parsing / OCR models in 10 languages (Hindi, Spanish, Arabic,
French, Bengali, Portuguese, Indonesian, Urdu, Russian, German). The goal is NOT to fool forensic experts; it is
that the pages are (a) DIVERSE like a real collection of this genre and (b) RELATIVELY REALISTIC: correct scripts and
local conventions, plausible layouts and coherent content, so a model trained on them transfers to real documents.

Genre under review: {genre}.
Image 1: a 4x4 contact sheet of 16 random pages of this genre from the current template version (mixed languages).
Images 2-3: two of those pages at readable resolution.

Your own blind single-page judgments of this genre in the current round (you did not know they were synthetic):
{own}
Automatic lint of the current version (objective defects such as bare LaTeX, wrong digits, empty regions,
English leaking into non-English pages): {lint}
Main changes since the previous round: {changes}

Decide, separately for diversity and realism: "accept" (good enough as training data), "accept_with_minor" (good
enough, minor issues worth fixing later) or "reject" (must be fixed before generating the dataset). Reject only for
problems that would teach a parsing/OCR model something wrong or leave an important real-world variety uncovered.
Return ONLY JSON:
{{"diversity": "accept" | "accept_with_minor" | "reject", "realism": "accept" | "accept_with_minor" | "reject",
  "blocking_issues": ["only if reject: concrete, fixable issues"], "minor_issues": ["..."],
  "diversity_score": 1-5, "realism_score": 1-5, "rationale": "2-3 sentences"}}"""

SCRIPT_NAME = {"hi": "Devanagari", "bn": "Bengali", "ar": "Arabic (Naskh/Kufi)", "ur": "Urdu Perso-Arabic (Nastaliq/Naskh)",
               "ru": "Cyrillic", "es": "Latin", "fr": "Latin", "pt": "Latin", "id": "Latin", "de": "Latin"}
LNAME = {"hi": "Hindi", "bn": "Bengali", "ar": "Arabic", "ur": "Urdu", "ru": "Russian", "es": "Spanish", "fr": "French",
         "pt": "Portuguese", "id": "Indonesian", "de": "German", "en": "English", "zh": "Chinese", "mixed": "various",
         "zh-Hans": "Simplified Chinese", "zh-Hant": "Traditional Chinese (Taiwan / Hong Kong)", "ja": "Japanese",
         "ko": "Korean", "vi": "Vietnamese", "th": "Thai", "tr": "Turkish", "fa": "Persian", "it": "Italian",
         "pl": "Polish", "nl": "Dutch"}
SCRIPT_NAME.update({"en": "Latin", "zh-Hans": "Simplified Han", "zh-Hant": "Traditional Han", "ja": "Kanji + Kana",
                    "ko": "Hangul", "vi": "Latin with Vietnamese diacritics", "th": "Thai", "tr": "Latin",
                    "fa": "Perso-Arabic (Naskh)", "it": "Latin", "pl": "Latin", "nl": "Latin"})
GENRE = {"ppt": "presentation slide", "exam": "exam / test paper", "paper_single": "single-column academic paper page",
         "paper_double": "double-column academic paper page", "newspaper": "newspaper page", "magazine": "magazine page",
         "book": "book page", "textbook": "colorful school textbook page", "report": "financial / equity research report page"}

_lock = threading.Lock()


def _prep_single(path, max_side=1600, crop=1000):
    """Return (full_jpg_path, crop_jpg_path) with a crop centred on the densest dark-pixel region."""
    TMP.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(str(path).encode()).hexdigest()[:16]
    fp, cp = TMP / f"{h}_full.jpg", TMP / f"{h}_crop.jpg"
    if fp.exists() and cp.exists():
        return fp, cp
    im = Image.open(path).convert("RGB")
    full = im.copy()
    s = max_side / max(full.size)
    if s < 1:
        full = full.resize((int(full.width * s), int(full.height * s)), Image.LANCZOS)
    full.save(fp, quality=88)
    g = im.convert("L").resize((max(1, im.width // 16), max(1, im.height // 16)))
    import numpy as np
    a = (255 - np.asarray(g, dtype=np.float32))
    cw = max(1, crop // 16)
    best, bx, by = -1, 0, 0
    for y in range(0, max(1, a.shape[0] - cw), max(1, cw // 3)):
        for x in range(0, max(1, a.shape[1] - cw), max(1, cw // 3)):
            v = a[y:y + cw, x:x + cw].sum()
            if v > best:
                best, bx, by = v, x, y
    x0, y0 = bx * 16, by * 16
    im.crop((x0, y0, min(im.width, x0 + crop), min(im.height, y0 + crop))).save(cp, quality=90)
    return fp, cp


def make_grid(paths, out, cell=(420, 560), cols=4):
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell[0], rows * cell[1]), "white")
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell[0] - 10, cell[1] - 10))
        sheet.paste(im, ((i % cols) * cell[0] + 5, (i // cols) * cell[1] + 5))
    sheet.save(out, quality=88)
    return out


def make_pair(pa, pb, out, h=1500):
    ims = []
    for p in (pa, pb):
        im = Image.open(p).convert("RGB")
        s = h / im.height
        ims.append(im.resize((int(im.width * s), h), Image.LANCZOS))
    return ims


def judge_one(task, judge, out_f, key="main"):
    model, effort = JUDGES[judge]
    t0 = time.time()
    if task["kind"] == "single":
        fp, cp = _prep_single(task["path"])
        prompt = SINGLE_PROMPT.format(lname=LNAME.get(task["lang"], task["lang"]), script=SCRIPT_NAME.get(task["lang"], ""),
                                      genre=GENRE[task["doc_type"]])
        images = [fp, cp]
    elif task["kind"] == "grid":
        prompt = GRID_PROMPT.format(genre=GENRE[task["doc_type"]])
        images = [task["path"]]
    elif task["kind"] == "signoff":
        own = task.get("own", {}).get(judge, "n/a")
        prompt = SIGNOFF_PROMPT.format(genre=GENRE[task["doc_type"]], own=own, lint=task.get("lint", "n/a"),
                                       changes=task.get("changes", "n/a"))
        images = [task["path"]] + [_prep_single(p, max_side=1500)[0] for p in task.get("samples", [])[:2]]
    else:
        prompt = PAIR_PROMPT.format(genre=GENRE[task["doc_type"]], lname=LNAME.get(task["lang"], ""),
                                    script=SCRIPT_NAME.get(task["lang"], ""))
        images = [task["path_a"], task["path_b"]]
    try:
        text, meta = llm.call(model, prompt, images=images, max_tokens=6000, effort=effort, key=key, timeout=600)
        try:
            res = llm.extract_json(text)
        except Exception:  # noqa: BLE001
            res = {"parse_error": True}
        rec = {**task, "judge": judge, "model": meta.get("model"), "result": res, "raw": text,
               "sec": round(time.time() - t0, 1), "usage": meta.get("usage")}
    except Exception as e:  # noqa: BLE001
        rec = {**task, "judge": judge, "error": repr(e)[:400], "sec": round(time.time() - t0, 1)}
    with _lock:
        out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out_f.flush()
    return rec


def run_tasks(tasks, out_path, judges=("opus", "sol"), workers=10, key="main"):
    done = set()
    p = Path(out_path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                if "error" not in d:
                    done.add((d["task_id"], d["judge"]))
            except Exception:  # noqa: BLE001
                pass
    todo = [(t, j) for t in tasks for j in judges if (t["task_id"], j) not in done]
    print(f"judge tasks: {len(todo)} (done {len(done)})", flush=True)
    with open(p, "a", encoding="utf-8") as f, ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(judge_one, t, j, f, key) for t, j in todo]
        n = 0
        for fu in as_completed(futs):
            n += 1
            r = fu.result()
            if n % 10 == 0 or "error" in r:
                print(n, r.get("task_id"), r.get("judge"), "ERR " + r["error"][:120] if "error" in r else "ok",
                      flush=True)
    print("JUDGE_DONE", flush=True)

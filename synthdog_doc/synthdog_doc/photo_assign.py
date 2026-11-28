"""Photo assignment pass: pick a fitting photo for each story / lesson / deck and caption it truthfully.

For every item we sample ~16 candidate photos from compatible topics (each with a VLM English description) and
ask an LLM to choose the best matches and write captions in the document language that describe what is
actually visible, phrased so they fit the item's context (no invented names for unknown people).

  python3 -m synthdog_doc.photo_assign --kind news --workers 16
Output: /data/synthdog-doc/content/<lang>/<kind>_photos.jsonl  {"_idx", "photos": [{"path","caption","w","h"}]}
"""
import argparse
import json
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import llm
from .imagepool import TOPIC_COMPAT, SECTION_TOPIC, pool
from .langs import LANG_ORDER, LANGS

CONTENT = Path("/data/synthdog-doc/content")
NONPHOTO = re.compile(r"chart|diagram|graph|screenshot|logo|sign\b|signage|poster|table|label|page|document|"
                      r"cover|text|banner|infographic|map\b|slide|scan|certificate|form\b", re.I)
SUBJ_TOPIC = [("scien|wissen|ciên|cienc|naturw|विज्ञान|বিজ্ঞান|سائنس|علوم|наук|ipa|sains", "science"),
              ("geo|भूगोल|ভূগোল|جغراف|географ", "nature"), ("bio|जीव|জীব|حیات|احياء|биолог", "nature"),
              ("hist|इतिहास|ইতিহাস|تاریخ|تاريخ|истор|sejarah", "culture"),
              ("civ|नागरिक|পৌর|مدنی|وطن|обществ|pkn|citoy|cidad", "politics"),
              ("env|पर्यावरण|পরিবেশ|ماحول|بيئ|окруж|lingkungan|umwelt|ambient|environ", "nature")]

PROMPT = """You are a photo editor for a {lname}-language {genre} from {countries}.
CONTEXT ({what}):
{context}

CANDIDATE PHOTOS (id: description, orientation):
{cands}

Choose up to {k} photos that could plausibly illustrate this {what} in a real publication (generic/file photos
are fine). If none is acceptable, return an empty list. For each chosen photo write a caption in {lname} that
(1) accurately describes what is visible in the photo, (2) relates it to the context naturally (e.g. "File photo:
...", "A ... in ..."), (3) does NOT name specific people or places that the description does not support,
(4) is {caplen}.
{lenient}Return ONLY JSON: {{"photos": [{{"id": <id>, "caption": "..."}}]}}"""
STRICT = ("Strict rule for school textbooks: choose a photo ONLY if it clearly depicts the lesson's subject "
          "matter (the organ, organism, phenomenon, place, historical period or object being taught). Modern street "
          "or café scenes for historical or biological topics are NOT acceptable. When in doubt return an empty "
          "list.\n")
STRICT_STORY = ("Strict rule: choose a photo ONLY if it plausibly shows this story's own subject -- the kind of event, "
                "place, activity, people or objects the text is about (a generic file photo is fine only when it "
                "matches that specific subject, e.g. a hospital ward for a hospital story). Never a different sport, "
                "a different country's landmark, or an unrelated activity. When in doubt return an empty list.\n")
_SCRIPT_OK = {"latin": ("latin",), "cyrillic": ("cyrillic", "latin"), "devanagari": ("devanagari", "latin"),
              "bengali": ("bengali", "latin"), "arabic": ("arabic", "latin")}
LENIENT = ("Note: newspapers routinely illustrate stories with generic FILE photos (a building, a street, a crowd, "
           "an office, a classroom, a vehicle, a landscape, hands, a document on a desk) when no specific picture "
           "exists. Prefer choosing one such photo over none, as long as the caption is truthful and not misleading "
           "(e.g. 'File photo: ...', 'Symbolic image: ...').\n")

_lock = threading.Lock()


def candidates(topic, rng, n=16, script=None):
    rows = [r for r in pool("photo") + pool("photo_gray") if r.get("ok") is not False and r.get("subject")
            and not NONPHOTO.search(r["subject"])]
    if script:
        # no camera stamps / overlays, no prominent text, and any small text must be in a script of the page
        ok = _SCRIPT_OK.get(script, ("latin",))
        rows = [r for r in rows if not r.get("overlay") and r.get("text") != "much"
                and (r.get("text") in (None, "none") or r.get("text_script") in ok + ("none",))]
    compat = TOPIC_COMPAT.get(topic, [topic]) if topic else []
    pri = [r for r in rows if r.get("topic") in compat]
    rng.shuffle(pri)
    rest = [r for r in rows if r.get("topic") not in compat and r.get("topic") not in ("object", "other")]
    rng.shuffle(rest)
    out = pri[: int(n * 0.75)]
    out += rest[: n - len(out)]
    rng.shuffle(out)
    return out


def items(kind, lang):
    if kind == "news":
        for d in (json.loads(x) for x in (CONTENT / lang / "news.jsonl").read_text().splitlines()):
            if not d.get("is_news", True):
                continue
            ctx = f"HEADLINE: {d.get('headline','')}\nDECK: {d.get('deck','')}\nSTART: {' '.join(d.get('body', [])[:2])[:700]}"
            topic = d.get("photo_topic") or SECTION_TOPIC.get(d.get("section", ""), None)
            yield d["_idx"], ctx, topic, 2, "news story", "newspaper", "one sentence, 8-22 words"
    elif kind == "feature":
        for d in (json.loads(x) for x in (CONTENT / lang / "feature.jsonl").read_text().splitlines()):
            ctx = f"TITLE: {d.get('title','')}\nDECK: {d.get('deck','')}\nSECTIONS: " + \
                  "; ".join(s.get("heading", "") for s in d.get("sections", []))
            yield d["_idx"], ctx, d.get("photo_topic"), 3, "magazine feature", "magazine", "one or two sentences, 10-30 words"
    elif kind == "lesson":
        for d in (json.loads(x) for x in (CONTENT / lang / "lesson.jsonl").read_text().splitlines()):
            subj = f"{d.get('unit_title','')} {d.get('lesson_title','')}".lower()
            topic = next((t for pat, t in SUBJ_TOPIC if re.search(pat, subj)), "education")
            ctx = (f"UNIT: {d.get('unit_title','')}\nLESSON: {d.get('lesson_title','')}\nSECTIONS: "
                   + "; ".join(s.get("heading", "") for s in d.get("sections", [])))
            yield d["_idx"], ctx, topic, 3, "school textbook lesson", "school textbook", "short, 5-14 words"
    elif kind == "ppt":
        for d in (json.loads(x) for x in (CONTENT / lang / "ppt.jsonl").read_text().splitlines()):
            ctx = f"DECK: {d.get('deck_title','')}\nORG: {d.get('organization','')}\nSLIDES: " + \
                  "; ".join(s.get("title", "") for s in d.get("slides", []) if s.get("title"))
            yield d["_idx"], ctx, None, 3, "slide deck", "presentation", "short, 4-12 words"


def work(kind, lang, idx, ctx, topic, k, what, genre, caplen, seed=5, lenient=False, strict=False):
    rng = random.Random(f"{seed}-{kind}-{lang}-{idx}" + ("-l" if lenient else ""))
    cands = candidates(topic, rng, n=28 if lenient else 16, script=LANGS[lang].script if strict else None)
    L = LANGS[lang]
    lines = "\n".join(f"{i}: {c['subject']} ({'portrait' if c['h'] > c['w'] * 1.1 else 'landscape'})"
                      for i, c in enumerate(cands))
    prompt = PROMPT.format(lname=L.name, genre=genre, countries=", ".join(L.countries), what=what, context=ctx,
                           cands=lines, k=k, caplen=caplen,
                           lenient=LENIENT if lenient else ((STRICT if kind == "lesson" else STRICT_STORY) if strict else ""))
    text, _ = llm.call("gpt-6.1-sol", prompt, max_tokens=4000, effort="low", timeout=300)
    obj = llm.extract_json(text)
    if isinstance(obj, list):
        obj = {"photos": obj}
    out = []
    for p in (obj.get("photos") or [])[:k]:
        try:
            c = cands[int(p["id"])]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        out.append({"path": c["path"], "caption": p.get("caption", ""), "w": c["w"], "h": c["h"],
                    "subject": c["subject"], "topic": c.get("topic")})
    with _lock:
        with open(CONTENT / lang / f"{kind}_photos.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"_idx": idx, "photos": out, **({"retried": True} if lenient else {}),
                                **({"strict": True} if strict else {})}, ensure_ascii=False) + "\n")
    return len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=["news", "lesson", "ppt", "feature"])
    ap.add_argument("--langs", default=",".join(LANG_ORDER))
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--strict", action="store_true", help="re-assign every item with the strict relevance rule")
    ap.add_argument("--retry-empty", action="store_true",
                    help="second, more lenient pass (more candidates, file photos allowed) for items without a photo")
    a = ap.parse_args()
    jobs = []
    for lang in a.langs.split(","):
        src = CONTENT / lang / f"{a.kind}.jsonl"
        if not src.exists():
            continue
        dst = CONTENT / lang / f"{a.kind}_photos.jsonl"
        recs = {}
        if dst.exists():
            for x in dst.read_text().splitlines():
                d = json.loads(x)
                recs[d["_idx"]] = d          # later lines override earlier ones (same rule as corpus.packs)
        for it in items(a.kind, lang):
            if a.strict:
                if not (it[0] in recs and recs[it[0]].get("strict")):
                    jobs.append((lang,) + it)
            elif a.retry_empty:
                if it[0] in recs and not recs[it[0]].get("photos") and not recs[it[0]].get("retried"):
                    jobs.append((lang,) + it)
            elif it[0] not in recs:
                jobs.append((lang,) + it)
    print("jobs", len(jobs), flush=True)
    ok = fail = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(work, a.kind, *j, lenient=a.retry_empty, strict=a.strict): j[:2] for j in jobs}
        for f in as_completed(futs):
            try:
                f.result()
                ok += 1
                if ok % 50 == 0:
                    print("OK", ok, flush=True)
            except Exception as e:  # noqa: BLE001
                fail += 1
                print("FAIL", futs[f], repr(e)[:160], flush=True)
    print(f"ASSIGN_DONE kind={a.kind} ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()

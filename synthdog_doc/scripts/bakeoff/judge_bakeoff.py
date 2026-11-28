"""Score the LLM content bake-off: blind pairwise preference against the baseline + automatic checks + token cost.

  python3 scripts/bakeoff/judge_bakeoff.py --root /data/synthdog-doc/bakeoff/r1 --baseline sol-low \
      --candidates deepseek-flash,sonnet-low,gemini-low,step5 --out /data/synthdog-doc/bakeoff/r1/judge.json

Pairwise: for every (language, kind, idx) both runs produced, a judge from a different model family than both sides
(Claude Opus judges GPT / DeepSeek / Gemini / Step candidates against GPT-6.1-Sol; Gemini judges the Claude Sonnet
candidate) sees the two packs as A / B in random order. Automatic checks per pack: JSON failure rate, script purity,
Latin-word leakage in non-Latin languages, Simplified-character leakage in Traditional Chinese, placeholders.
Cost: token usage recorded in the packs times the price table below (USD per 1M tokens, public-list magnitudes --
replace with the gateway's settlement prices when known).
"""
import argparse
import collections
import json
import random
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from synthdog_doc import llm  # noqa: E402
from synthdog_doc.corpus_fetch import SCRIPT_RANGES, _SIMP, _TRAD  # noqa: E402
from synthdog_doc.langs import LANGS  # noqa: E402

PRICE = {  # (input, output) USD / 1M tokens -- assumptions (CCG round 2), reasoning tokens billed as output
    "sol-low": (1.25, 10.0), "deepseek-flash": (0.3, 1.2), "sonnet-low": (3.0, 15.0), "gemini-low": (2.0, 12.0),
    "step5": (0.5, 2.0), "qwen27-local": (0.0, 0.0)}   # self-hosted: priced by GPU time instead (see production.json)
FAMILY = {"sol-low": "gpt", "deepseek-flash": "deepseek", "sonnet-low": "claude", "gemini-low": "gemini", "step5": "step",
          "qwen27-local": "qwen", "qwen27-think": "qwen"}
JUDGE_PROMPT = """You are a senior native {lname} editor in {countries}. Two candidate content packs (A and B) were
written for a realistic printed {kind_desc}. Judge which one is better as authentic {lname} document content:
- native fluency (reads like original {lname} writing, not translation), correct orthography and script
- correctness (facts, mathematics, units, answer options) and internal consistency
- realism for documents actually printed in {countries} (structure, register, names, local conventions)
- no English / foreign leakage, no placeholders, no meta comments
<A>
{a}
</A>
<B>
{b}
</B>
Return ONLY JSON: {{"winner": "A" | "B" | "tie", "score_a": 1-5, "score_b": 1-5, "issues_a": ["..."], "issues_b": ["..."]}}"""
KIND_DESC = {"paper": "academic journal article", "exam": "school / university exam paper",
             "news": "newspaper article package (headline, deck, kicker, photo caption and brief around a real article)"}
_lock = threading.Lock()


def load(root, cand, lang, kind):
    p = Path(root) / cand / "content" / lang / f"{kind}.jsonl"
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                out[d["_idx"]] = d
            except Exception:  # noqa: BLE001
                pass
    return out


def fails(root, cand, lang, kind):
    return len(list((Path(root) / cand / "content" / lang).glob(f"_fail_{kind}_*.txt")))


def strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            if not str(k).startswith("_") and k not in ("url", "domain", "date", "body"):
                yield from strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from strings(v)


def render(pack, kind, limit=2600):
    """Compact, model-neutral text view of a pack for the judge."""
    p = {k: v for k, v in pack.items() if not k.startswith("_") and k not in ("url", "domain", "date")}
    if kind == "news":
        p["body"] = (pack.get("body") or [""])[:1]          # real text: only context, identical on both sides
    s = json.dumps(p, ensure_ascii=False, indent=0)
    return s[:limit] + (" …" if len(s) > limit else "")


def auto_checks(pack, lang):
    L = LANGS[lang]
    script = {"urdu": "arabic", "persian": "arabic", "vietnamese": "latin"}.get(L.script, L.script)
    rng = SCRIPT_RANGES.get(script, SCRIPT_RANGES["latin"])
    txt = " ".join(s for s in strings(pack) if "\\" not in s)            # skip LaTeX strings
    letters = [c for c in txt if c.isalpha()]
    pur = sum(1 for c in letters if any(a <= ord(c) <= b for a, b in rng)) / len(letters) if letters else 1.0
    latin_words = len(re.findall(r"\b[A-Za-z]{4,}\b", txt)) if script != "latin" else 0
    words = max(1, len(txt.split()) if script not in ("hans", "hant", "japanese", "thai") else len(txt) // 2)
    simp = sum(1 for c in txt if c in _SIMP and c not in _TRAD) if lang == "zh-Hant" else 0
    ph = len(re.findall(r"\[(?:\.\.\.|…|X+|TBD|placeholder)\]|Lorem ipsum|XXX|\{\{|\}\}", txt, re.I))
    return {"purity": round(pur, 4), "latin_word_rate": round(latin_words / words, 4), "simp_chars": simp,
            "placeholders": ph}


def usage_tokens(pack):
    u = pack.get("_usage") or {}
    inp = u.get("prompt_tokens") or u.get("input_tokens") or u.get("promptTokenCount") or 0
    out = u.get("completion_tokens") or u.get("output_tokens") or 0
    if not out and u.get("candidatesTokenCount") is not None:
        out = (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)
    cached = ((u.get("prompt_tokens_details") or {}).get("cached_tokens") or u.get("cache_read_input_tokens") or 0)
    return inp, out, cached


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--baseline", default="sol-low")
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--langs", default="ar,hi,bn,ja,th,zh-Hant,de")
    ap.add_argument("--kinds", default="paper,exam,news")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    langs, kinds = a.langs.split(","), a.kinds.split(",")
    rnd = random.Random(a.seed)
    rows, jobs = collections.defaultdict(list), []
    stats = {}
    for cand in [a.baseline] + a.candidates.split(","):
        st = collections.defaultdict(lambda: collections.Counter())
        for lang in langs:
            for kind in kinds:
                packs = load(a.root, cand, lang, kind)
                st[kind]["packs"] += len(packs)
                st[kind]["fails"] += fails(a.root, cand, lang, kind)
                for d in packs.values():
                    ac = auto_checks(d, lang)
                    st[kind]["purity_sum"] += ac["purity"]
                    st[kind]["latin_rate_sum"] += ac["latin_word_rate"]
                    st[kind]["simp_chars"] += ac["simp_chars"]
                    st[kind]["placeholders"] += ac["placeholders"]
                    i, o, c = usage_tokens(d)
                    st[kind]["in_tok"] += i
                    st[kind]["out_tok"] += o
                    st[kind]["cached_tok"] += c
        stats[cand] = {k: dict(v) for k, v in st.items()}
    judge_for = lambda cand: ("gemini" if FAMILY.get(cand) == "claude" else "opus")  # noqa: E731
    for cand in a.candidates.split(","):
        for lang in langs:
            for kind in kinds:
                base, mine = load(a.root, a.baseline, lang, kind), load(a.root, cand, lang, kind)
                for idx in sorted(set(base) & set(mine)):
                    flip = rnd.random() < 0.5
                    jobs.append((cand, lang, kind, idx, base[idx], mine[idx], flip))
    print(f"{len(jobs)} pairwise judgements", flush=True)
    done = {}
    outp = Path(a.out).with_suffix(".pairs.jsonl")
    if outp.exists():
        for line in outp.read_text().splitlines():
            r = json.loads(line)
            done[(r["cand"], r["lang"], r["kind"], r["idx"])] = r

    def work(job):
        cand, lang, kind, idx, b, m, flip = job
        L = LANGS[lang]
        A, B = (m, b) if flip else (b, m)
        prompt = JUDGE_PROMPT.format(lname=L.name, countries=", ".join(L.countries), kind_desc=KIND_DESC[kind],
                                     a=render(A, kind), b=render(B, kind))
        if judge_for(cand) == "gemini":
            text, _ = llm.call(llm.gemini_model_for_key("mid"), prompt, max_tokens=8000, effort="high", key="mid",
                               timeout=600)
        else:
            text, _ = llm.call("claude-opus-5-5-pretrain", prompt, max_tokens=8000, effort="medium", timeout=600)
        v = llm.extract_json(text)
        w = v.get("winner")
        cand_side = "A" if flip else "B"
        res = {"cand": cand, "lang": lang, "kind": kind, "idx": idx, "judge": judge_for(cand),
               "result": "win" if w == cand_side else ("tie" if w == "tie" else "loss"),
               "score_cand": v.get("score_a") if flip else v.get("score_b"),
               "score_base": v.get("score_b") if flip else v.get("score_a"),
               "issues_cand": v.get("issues_a") if flip else v.get("issues_b"),
               "issues_base": v.get("issues_b") if flip else v.get("issues_a")}
        with _lock, open(outp, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
        return res

    todo = [j for j in jobs if (j[0], j[1], j[2], j[3]) not in done]
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(work, j) for j in todo]
        for k, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
                done[(r["cand"], r["lang"], r["kind"], r["idx"])] = r
            except Exception as e:  # noqa: BLE001
                print("FAIL", repr(e)[:200], flush=True)
            if k % 50 == 0:
                print(f"  judged {k}/{len(todo)}", flush=True)
    summary = {"baseline": a.baseline, "price_assumption": PRICE, "auto": stats, "pairwise": {}}
    for cand in a.candidates.split(","):
        rs = [r for r in done.values() if r["cand"] == cand]
        by = collections.defaultdict(lambda: collections.Counter())
        for r in rs:
            by["all"][r["result"]] += 1
            by[r["kind"]][r["result"]] += 1
            by[r["lang"]][r["result"]] += 1
        summary["pairwise"][cand] = {k: {**dict(v), "non_inferior": round((v["win"] + 0.5 * v["tie"]) / max(1, sum(v.values())), 3)}
                                     for k, v in by.items()}
    Path(a.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    for cand, d in summary["pairwise"].items():
        print(cand, d.get("all"))


if __name__ == "__main__":
    main()

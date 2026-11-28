"""Page -> Markdown predictions from gateway VLMs (GPT-6-Astra, GPT-6.1-Sol, Claude Opus 5.5, ...).

One request per page with the multilingual OmniDocBench-style prompt below; resumable (rows already ok in --out are
skipped); every row keeps status, stop reason, token usage and latency so refusal / truncation rates and cost can
be reported next to the scores.

  python3 scripts/bench_api.py --images /data/synthdog-doc/bench/bench900/images \
      --manifest /data/synthdog-doc/bench/bench900/manifest.jsonl --model gpt-6.1-sol --effort medium \
      --out /data/synthdog-doc/bench/runs/bench900/raw/gpt-6.1-sol.jsonl --concurrency 8

Output rows: {"record_id": "<image file>", "model", "status": ok|empty|truncated|refused|error, "response", "stop",
"usage", "sec", "error"}; feed them to docparse.evaluate.to_markdown and odb-eval's jsonl_to_md.py.
"""
import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synthdog_doc import llm  # noqa: E402

PROMPT = """Convert this document image to Markdown. Follow these rules exactly and output nothing else:

1. Transcribe all text exactly as printed, in its original language and script. Do NOT translate, summarize or \
correct it; keep the digits as printed (e.g. Arabic-Indic or Devanagari digits stay as they are).
2. Headings: prefix with `# `.
3. Body text: plain paragraphs, separated by a blank line.
4. Tables: output as HTML, `<table><tr><td>…</td></tr></table>`. Do NOT use Markdown pipe tables. Do NOT flatten a \
table into running text.
5. Display formulas: wrap in `$$` on their own lines. Inline formulas: `$…$`.
6. Figures, charts, photos, seals: output NOTHING for them. Do NOT describe the image content. (Captions and \
footnotes ARE text — transcribe them normally.)
7. Headers, footers, page numbers: omit.
8. Follow human reading order. For multi-column layouts finish one column before starting the next: left column \
first for left-to-right scripts, right column first for right-to-left scripts (Arabic, Urdu, Persian, Hebrew).

Output only the Markdown."""

_lock = threading.Lock()


def classify_error(msg):
    m = msg.lower()
    if "refus" in m or "stop=refusal" in m or "content_filter" in m or "safety" in m:
        return "refused"
    if "max_tokens" in m or "length" in m:
        return "truncated"
    if "empty response" in m:
        return "empty"
    return "error"


def run_one(img, model, effort, max_tokens, timeout):
    t0 = time.time()
    try:
        text, meta = llm.call(model, PROMPT, images=[img], max_tokens=max_tokens, effort=effort,
                              timeout=timeout, retries=3)
        stop = meta.get("stop")
        status = "truncated" if stop in ("max_tokens", "length") else "ok"
        return {"status": status, "response": text, "stop": stop, "usage": meta.get("usage"),
                "reported_model": meta.get("model"), "sec": round(time.time() - t0, 1)}
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        return {"status": classify_error(msg), "response": "", "error": msg[:500], "sec": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--manifest", required=True, help="manifest.jsonl with a 'name' per page (image = <name>.jpg)")
    ap.add_argument("--model", required=True)
    ap.add_argument("--effort", default=None)
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    names = [json.loads(x)["name"] for x in Path(a.manifest).read_text().splitlines() if x.strip()]
    if a.limit:
        names = names[:a.limit]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            if r.get("status") == "ok":
                done.add(r["record_id"])
    todo = [n for n in names if f"{n}.jpg" not in done]
    print(f"{a.model}: {len(names)} pages, {len(done)} already ok, {len(todo)} to run", flush=True)

    t0 = time.time()
    stats = {}
    with ThreadPoolExecutor(a.concurrency) as ex:
        futs = {ex.submit(run_one, str(Path(a.images) / f"{n}.jpg"), a.model, a.effort, a.max_tokens, a.timeout): n
                for n in todo}
        for k, f in enumerate(as_completed(futs), 1):
            n = futs[f]
            r = {"record_id": f"{n}.jpg", "model": a.model, "effort": a.effort, **f.result()}
            stats[r["status"]] = stats.get(r["status"], 0) + 1
            with _lock, open(out, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            if k % 25 == 0 or k == len(todo):
                print(f"  {k}/{len(todo)} {stats} {time.time() - t0:.0f}s", flush=True)
    print("BENCH_API_DONE", a.model, stats, flush=True)


if __name__ == "__main__":
    main()

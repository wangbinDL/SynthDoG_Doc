"""LLM content-model bake-off (task 5): which model writes SynthDoG-Doc content packs best per unit cost?

Same prompts, same real-text seeds (content_gen / news_pack job lists are deterministic), several candidate models:
  paper  -- full academic-paper pack (the hardest generation task)
  exam   -- exam paper pack (questions, options, formulas)
  news   -- structured edit of a real national-web article (headline, deck, kicker, caption around verbatim text)

  python3 scripts/bakeoff/run_bakeoff.py --out /data/synthdog-doc/bakeoff/r1 --langs ar,hi,bn,ja,th,zh-Hant,de --n 10

Each candidate's packs land in <out>/<candidate>/content/<lang>/{paper,exam,news}.jsonl (with token usage);
judge_bakeoff.py then scores them.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from synthdog_doc import content_gen, llm  # noqa: E402

CANDIDATES = {   # name -> (model id, key, effort)
    "sol-low": ("gpt-6.1-sol", "main", "low"),
    "deepseek-flash": ("deepseek-v4.1-flash-pretrain", "main", None),
    "sonnet-low": ("claude-sonnet-5-5-coding", "main", "low"),
    "gemini-low": ("@gemini", "mid", "low"),
    "step5": ("Step-5-preview-pretrain", "main", None),
    "qwen27-local": ("Qwen3.8-27B", "@local", "nothink"),   # self-hosted vLLM on 1 GPU, thinking off
    "qwen27-think": ("Qwen3.8-27B", "@local", "think"),     # same server, thinking on
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--langs", default="ar,hi,bn,ja,th,zh-Hant,de")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--candidates", default=",".join(CANDIDATES))
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--local-base", default="", help="URL of the self-hosted server for '@local' candidates")
    a = ap.parse_args()
    langs = a.langs.split(",")
    for name in a.candidates.split(","):
        model, key, effort = CANDIDATES[name]
        if model == "@gemini":
            model = llm.gemini_model_for_key(key)
        if key == "@local":
            key = a.local_base
        out = Path(a.out) / name / "content"
        print(f"== {name}: {model} effort={effort}", flush=True)
        content_gen.run(out, langs, {"paper": a.n, "exam": a.n}, model, effort, a.workers,
                        "/data/synthdog-doc/corpus", key=key)
        cmd = [sys.executable, "-u", "-m", "synthdog_doc.news_pack", "--langs", ",".join(langs), "--n", str(a.n),
               "--model", model, "--workers", str(a.workers), "--key", key, "--out", str(out)]
        if effort:
            cmd += ["--effort", effort]
        else:
            cmd += ["--effort", ""]
        subprocess.run(cmd, cwd=ROOT, check=False)
    print("BAKEOFF_GEN_DONE", flush=True)


if __name__ == "__main__":
    main()

"""Build and run one judging round for a rendered version.

  python3 scripts/judge_round.py --version 0 --renders /data/synthdog-doc/renders/v0 --out /data/synthdog-doc/judge/r1
  python3 scripts/judge_round.py --version 1 --renders .../v1 --prev .../v0 --out .../r2      (adds A/B pairs)
"""
import argparse
import glob
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synthdog_doc import judge as J  # noqa: E402

TYPES = ["ppt", "exam", "paper_single", "paper_double", "newspaper", "magazine", "book", "textbook", "report"]
LANGS = ["hi", "es", "ar", "fr", "bn", "pt", "ru", "id", "ur", "de"]
REAL_MAP = {"ppt": ["Slides_Presentation"], "exam": ["Exam_Test_Paper", "Worksheet_Practice_Set"],
            "paper_single": ["Scientific_Paper", "Scientific_Abstract"], "paper_double": ["Scientific_Paper"],
            "newspaper": ["News_Article"], "magazine": ["Opinion_Review"],
            "book": ["Narrative_Fiction", "Narrative_Nonfiction", "Poetry"], "textbook": ["Textbook", "Lecture_Notes"],
            "report": ["Report_(General)", "Technical_Report"]}
ODB_SRC = {"ppt": "PPT2PDF", "exam": "exam_paper", "paper_single": "academic_literature",
           "paper_double": "academic_literature", "newspaper": "newspaper", "magazine": "magazine", "book": "book",
           "textbook": "colorful_textbook", "report": "research_report"}


def real_controls(rng, per_type=3):
    out = []
    odb = None
    for t in TYPES:
        cands = []
        for lang in LANGS:
            for fmt in REAL_MAP[t]:
                idx = Path(f"/data/synthdog-doc/realref/{lang}/{fmt}/index.jsonl")
                if idx.exists():
                    rows = [json.loads(x) for x in idx.read_text().splitlines()]
                    cands += [(lang, r["path"], "l1") for r in rows]
        rng.shuffle(cands)
        chosen, langs_seen = [], set()
        for lang, p, src in cands:
            if lang in langs_seen:
                continue
            chosen.append((lang, p, src))
            langs_seen.add(lang)
            if len(chosen) >= per_type:
                break
        if len(chosen) < 2:
            if odb is None:
                odb = json.load(open("/data/omnidocbench-full/OmniDocBench.json"))
            pool = [x for x in odb if x["page_info"]["page_attribute"]["data_source"] == ODB_SRC[t]
                    and x["page_info"]["page_attribute"]["language"] == "english"]
            for x in rng.sample(pool, min(len(pool), per_type - len(chosen))):
                chosen.append(("en", "/data/omnidocbench-full/images/" + x["page_info"]["image_path"], "odb"))
        for lang, p, src in chosen:
            out.append({"kind": "single", "doc_type": t, "lang": lang, "path": p, "truth": "real", "real_src": src})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int, required=True)
    ap.add_argument("--renders", required=True)
    ap.add_argument("--prev", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-cell", type=int, default=1)
    ap.add_argument("--judges", default="opus,sol")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--no-real", action="store_true")
    ap.add_argument("--types", default=",".join(TYPES), help="restrict the round to some document types")
    a = ap.parse_args()
    TYPES[:] = [t for t in TYPES if t in a.types.split(",")]
    rng = random.Random(1234)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tasks = []
    for t in TYPES:
        for lang in LANGS:
            for i in range(a.per_cell):
                p = Path(a.renders) / f"{t}__{lang}__v{a.version}__{i:04d}.jpg"
                if p.exists():
                    tasks.append({"kind": "single", "doc_type": t, "lang": lang, "path": str(p), "truth": "synthetic",
                                  "version": a.version})
    if not a.no_real:
        tasks += real_controls(rng)
    # diversity grids: 16 random pages of each type
    for t in TYPES:
        fs = sorted(glob.glob(f"{a.renders}/{t}__*__v{a.version}__*.jpg"))
        fs = [f for f in fs if "overlay" not in f]
        if len(fs) >= 8:
            sel = rng.sample(fs, min(16, len(fs)))
            gp = out / f"grid_{t}.jpg"
            J.make_grid(sel, gp)
            tasks.append({"kind": "grid", "doc_type": t, "lang": "mixed", "path": str(gp), "version": a.version,
                          "members": sel})
    if a.prev:
        pv = a.version - 1
        for t in TYPES:
            for lang in LANGS:
                pa = Path(a.prev) / f"{t}__{lang}__v{pv}__0000.jpg"
                pb = Path(a.renders) / f"{t}__{lang}__v{a.version}__0000.jpg"
                if pa.exists() and pb.exists():
                    flip = rng.random() < 0.5
                    A_, B_ = (pb, pa) if flip else (pa, pb)
                    tasks.append({"kind": "pair", "doc_type": t, "lang": lang, "path_a": str(A_), "path_b": str(B_),
                                  "new_is": "A" if flip else "B", "versions": [pv, a.version]})
    for k, t in enumerate(tasks):
        t["task_id"] = f"{t['kind']}_{t['doc_type']}_{t['lang']}_{k:04d}"
    (out / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"tasks: {len(tasks)} single_syn={sum(1 for t in tasks if t.get('truth') == 'synthetic')} "
          f"single_real={sum(1 for t in tasks if t.get('truth') == 'real')} "
          f"grid={sum(1 for t in tasks if t['kind'] == 'grid')} pair={sum(1 for t in tasks if t['kind'] == 'pair')}",
          flush=True)
    J.run_tasks(tasks, out / "results.jsonl", judges=tuple(a.judges.split(",")), workers=a.workers)


if __name__ == "__main__":
    main()

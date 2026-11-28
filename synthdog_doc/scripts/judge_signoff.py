"""Sign-off round: for every document type ask both judges whether the current templates are diverse and realistic
enough to generate the training set (accept / accept_with_minor / reject), given the 4x4 contact sheet, two pages at
readable resolution, their own blind scores from the latest round and the lint summary.

  python3 scripts/judge_signoff.py --version 3 --renders /data/synthdog-doc/renders/v3 --round /data/synthdog-doc/judge/r4 \
      --lint /data/synthdog-doc/metrics/lint_all.json --out /data/synthdog-doc/judge/signoff_v3
"""
import argparse
import collections
import glob
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synthdog_doc import judge as J  # noqa: E402

TYPES = ["ppt", "exam", "paper_single", "paper_double", "newspaper", "magazine", "book", "textbook", "report"]
CHANGES = {
    "newspaper": "issue date never older than the years mentioned in its stories; photos limited in upscaling and "
                 "cropping, assigned to 96% of stories; headline blocks cannot run into the module below",
    "paper_single": "submitted-manuscript style (double spacing, line numbers); affiliation superscripts; equations "
                    "sized to fit; ~150 additional papers so text repeats less; self-described hypothetical packs removed",
    "paper_double": "affiliation superscripts; full-width figure = first figure of the page; equations fitted clear of "
                    "the equation number; math isolated from right-to-left text; ~150 additional papers",
    "exam": "question labels no longer doubled in Urdu; script-appropriate sub-question markers; plausible marks for "
            "objective items; instruction before the reading passage; sections never restart from another paper; "
            "student fields on most first pages; footer items spaced",
    "report": "structured disclosures page with realistic rating distribution and one certifying analyst; chart "
              "gallery and peer-valuation pages; ~90 additional reports",
    "magazine": "each story uses its own captioned photo (never a random one), photos need enough pixels; genuine Q&A "
                "interviews; photo essays; ~110 additional features",
    "book": "contents page from one coherent subject without a foreign running head; footnotes removed when their "
            "reference mark is not on the page",
    "textbook": "photos only when they clearly show the lesson subject (otherwise none); whole-word blanks; "
                "self-contained true/false items; one margin key-words box; full-bleed openers, margin layout, "
                "chapter review pages; ~160 additional lessons",
    "ppt": "KPI tiles and process steps equal height and centred as a block; larger text on sparse slides; abstract "
           "logo marks instead of broken initials for Indic / Arabic-script names; only real photographs on covers",
}


def own_summary(results, doc_type):
    by = collections.defaultdict(list)
    for r in results:
        if r.get("kind") == "single" and r.get("truth") == "synthetic" and r.get("doc_type") == doc_type \
                and "result" in r:
            by[r["judge"]].append(r["result"])
    out = {}
    for j, rs in by.items():
        sc = [x.get("scores", {}).get("overall_realism") for x in rs if x.get("scores")]
        sc = [s for s in sc if isinstance(s, (int, float))]
        real = sum(1 for x in rs if x.get("verdict") == "real")
        flaws = collections.Counter(f.get("issue_type") for x in rs for f in (x.get("flaws") or [])
                                    if f.get("severity") in ("major", "blocker"))
        out[j] = (f"{len(rs)} pages; mean overall realism {sum(sc) / max(1, len(sc)):.2f}/5; judged real on "
                  f"{real}/{len(rs)}; most frequent major issues: "
                  + (", ".join(f"{k} ({v})" for k, v in flaws.most_common(4)) or "none"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int, required=True)
    ap.add_argument("--renders", required=True)
    ap.add_argument("--round", required=True, help="judge round dir with results.jsonl of this version")
    ap.add_argument("--lint", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--types", default=",".join(TYPES))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=4321, help="page sample for the contact sheets")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    results = [json.loads(x) for x in (Path(a.round) / "results.jsonl").read_text().splitlines()]
    lint = json.loads(Path(a.lint).read_text())
    lk = next((k for k in lint if k.rstrip("/").endswith(Path(a.renders).name)), None)
    rng = random.Random(a.seed)
    tasks = []
    prev = {}
    if (out / "results.jsonl").exists():      # keep verdicts already obtained for other types
        for x in (out / "results.jsonl").read_text().splitlines():
            d = json.loads(x)
            prev[(d.get("doc_type"), d.get("judge"))] = "result" in d
    for t in a.types.split(","):
        fs = sorted(f for f in glob.glob(f"{a.renders}/{t}__*__v{a.version}__*.jpg") if "overlay" not in f)
        sel = rng.sample(fs, min(16, len(fs)))
        gp = out / f"grid_{t}.jpg"
        J.make_grid(sel, gp)
        ltr = [f for f in sel if any(f"__{l}__" in f for l in ("es", "fr", "de", "pt", "id", "ru"))]
        oth = [f for f in sel if f not in ltr]
        samples = (ltr[:1] + oth[:1]) or sel[:2]
        lsum = "n/a"
        if lk:
            bt = lint[lk]["summary"]["by_type"].get(t, {})
            lsum = (f"{bt.get('clean_rate', 0):.0%} of pages without medium/high-severity defects; check rates: "
                    + ", ".join(f"{k} {v:.0%}" for k, v in list(bt.get("checks", {}).items())[:4]))
        tasks.append({"kind": "signoff", "doc_type": t, "lang": "mixed", "path": str(gp), "samples": samples,
                      "own": own_summary(results, t), "lint": lsum, "changes": CHANGES.get(t, "n/a"),
                      "version": a.version, "task_id": f"signoff_{t}" + (f"_s{a.seed}" if a.seed != 4321 else ""),
                      "seed": a.seed})
    (out / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
    J.run_tasks(tasks, out / "results.jsonl", judges=("opus", "sol"), workers=a.workers)
    # verdict table
    res = [json.loads(x) for x in (out / "results.jsonl").read_text().splitlines()]
    table = collections.defaultdict(dict)
    for r in res:
        if isinstance(r.get("result"), list):
            r["result"] = next((x for x in r["result"] if isinstance(x, dict)), None)
        if isinstance(r.get("result"), dict):
            table[r["doc_type"]][r["judge"]] = {k: r["result"].get(k) for k in
                                                ("diversity", "realism", "diversity_score", "realism_score",
                                                 "blocking_issues", "minor_issues", "rationale")}
    (out / "summary.json").write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = all(v.get(j, {}).get("diversity") in ("accept", "accept_with_minor") and
             v.get(j, {}).get("realism") in ("accept", "accept_with_minor")
             for v in table.values() for j in ("opus", "sol"))
    for t in TYPES:
        if t in table:
            print(t, {j: (table[t].get(j, {}).get("diversity"), table[t].get(j, {}).get("realism"))
                      for j in ("opus", "sol")})
    print("SIGNOFF_ALL_ACCEPT" if ok else "SIGNOFF_HAS_REJECT", flush=True)


if __name__ == "__main__":
    main()

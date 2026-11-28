"""Quantitative comparison of synthetic sets against OmniDocBench statistics (frozen reference, not tuned on pages).

Per doc type: page geometry, element densities, text/figure area fractions, a normalized distribution distance,
and a layout-diversity score (mean nearest-neighbour layout-mask similarity; lower = more diverse).
  python3 -m synthdog_doc.metrics --sets v0=/data/synthdog-doc/renders/v0 v1=... --out metrics.json
"""
import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ODB_JSON = "/data/omnidocbench-full/OmniDocBench.json"
ODB_SRC = {"ppt": "PPT2PDF", "exam": "exam_paper", "paper_single": "academic_literature",
           "paper_double": "academic_literature", "newspaper": "newspaper", "magazine": "magazine", "book": "book",
           "textbook": "colorful_textbook", "report": "research_report"}
TEXT = {"text_block", "title", "header", "footer", "page_number", "figure_caption", "table_caption", "reference",
        "page_footnote", "table_footnote", "figure_footnote", "equation_caption", "code_txt", "list_group"}
LABEL = {"text_block": 1, "reference": 1, "list_group": 1, "code_txt": 1, "title": 2, "figure": 3, "table": 4,
         "equation_isolated": 5, "figure_caption": 6, "table_caption": 6, "equation_caption": 6, "header": 7,
         "footer": 7, "page_number": 7, "page_footnote": 7}
GRID = (24, 32)  # cols x rows


def page_features(dets, w, h):
    cnt = defaultdict(int)
    text_area = fig_area = tab_area = 0.0
    for d in dets:
        c = d["category_type"]
        cnt[c] += 1
        p = np.asarray(d["poly"], dtype=float).reshape(-1, 2)
        a = (p[:, 0].max() - p[:, 0].min()) * (p[:, 1].max() - p[:, 1].min()) / (w * h)
        if c in TEXT:
            text_area += a
        elif c == "figure":
            fig_area += a
        elif c == "table":
            tab_area += a
    return {"aspect": h / w, "width": w, "n_blocks": len(dets), "n_title": cnt["title"], "n_text": cnt["text_block"],
            "n_figure": cnt["figure"], "n_table": cnt["table"], "n_equation": cnt["equation_isolated"],
            "text_area": min(1.0, text_area), "figure_area": min(1.0, fig_area), "table_area": min(1.0, tab_area)}


def layout_mask(dets, w, h):
    gx, gy = GRID
    m = np.zeros((gy, gx), dtype=np.int8)
    order = sorted(dets, key=lambda d: -(LABEL.get(d["category_type"], 0) in (3, 4)))
    for d in order:
        lab = LABEL.get(d["category_type"])
        if not lab:
            continue
        p = np.asarray(d["poly"], dtype=float).reshape(-1, 2)
        x0, x1 = int(p[:, 0].min() / w * gx), int(np.ceil(p[:, 0].max() / w * gx))
        y0, y1 = int(p[:, 1].min() / h * gy), int(np.ceil(p[:, 1].max() / h * gy))
        m[max(0, y0):min(gy, y1), max(0, x0):min(gx, x1)] = lab
    return m


def mask_sim(a, b):
    nz = (a > 0) | (b > 0)
    if not nz.any():
        return 1.0
    return float(((a == b) & nz).sum() / nz.sum())


def nn_similarity(masks):
    if len(masks) < 2:
        return None
    M = np.stack(masks)
    sims = []
    for i in range(len(M)):
        best = 0.0
        for j in range(len(M)):
            if i != j:
                best = max(best, mask_sim(M[i], M[j]))
        sims.append(best)
    return float(np.mean(sims))


FLOOR = {"aspect": 0.05, "text_area": 0.05, "figure_area": 0.05, "table_area": 0.05}


def w1_norm(x, ref, feat=None):
    """Quantile-matched W1 distance normalised by the reference IQR (with a per-feature floor)."""
    x, ref = np.sort(np.asarray(x, float)), np.sort(np.asarray(ref, float))
    if len(x) == 0 or len(ref) == 0:
        return None
    qs = np.linspace(0, 1, 101)
    d = np.abs(np.quantile(x, qs) - np.quantile(ref, qs)).mean()
    iqr = np.quantile(ref, 0.75) - np.quantile(ref, 0.25)
    scale = max(iqr, FLOOR.get(feat, 1.0))
    return float(d / scale)


FEATS = ["aspect", "n_blocks", "n_title", "n_text", "n_figure", "n_table", "n_equation", "text_area", "figure_area"]


def odb_reference(rng_seed=0, max_per_src=200):
    d = json.load(open(ODB_JSON))
    by = defaultdict(list)
    for x in d:
        by[x["page_info"]["page_attribute"]["data_source"]].append(x)
    ref = {}
    for src, xs in by.items():
        feats = [page_features(x["layout_dets"], x["page_info"]["width"], x["page_info"]["height"]) for x in xs]
        masks = [layout_mask(x["layout_dets"], x["page_info"]["width"], x["page_info"]["height"]) for x in xs]
        ref[src] = {"feats": feats, "masks": masks, "n": len(xs)}
    return ref


def load_set(root):
    by = defaultdict(list)
    for f in glob.glob(f"{root}/*.json"):
        if f.endswith(".meta.json") or "/_" in f:
            continue
        name = Path(f).stem
        dt = name.split("__")[0]
        lang = name.split("__")[1] if "__" in name else "?"
        o = json.load(open(f))
        pi = o["page_info"]
        by[dt].append((lang, o["layout_dets"], pi["width"], pi["height"]))
    return by


def summarize(sets, out):
    ref = odb_reference()
    res = {"odb": {}, "sets": {}}
    rng = np.random.default_rng(0)

    def odb_nn(src, n, reps=5):
        ms = ref[src]["masks"]
        vals = [nn_similarity([ms[i] for i in rng.choice(len(ms), size=min(n, len(ms)), replace=False)])
                for _ in range(reps)]
        return float(np.mean(vals))
    for dt, src in ODB_SRC.items():
        r = ref[src]
        res["odb"][dt] = {"n": r["n"], "nn_sim@40": odb_nn(src, 40),
                          "median": {k: float(np.median([f[k] for f in r["feats"]])) for k in FEATS}}
    for name, root in sets.items():
        by = load_set(root)
        res["sets"][name] = {}
        for dt, pages in by.items():
            feats = [page_features(d, w, h) for _, d, w, h in pages]
            masks = [layout_mask(d, w, h) for _, d, w, h in pages]
            reff = ref[ODB_SRC[dt]]["feats"]
            dists = {k: w1_norm([f[k] for f in feats], [f[k] for f in reff], k) for k in FEATS}
            vals = [v for v in dists.values() if v is not None]
            sub = [masks[i] for i in rng.choice(len(masks), size=min(40, len(masks)), replace=False)]
            res["sets"][name][dt] = {"n": len(pages), "nn_sim": nn_similarity(sub), "odb_nn_sim_same_n": odb_nn(ODB_SRC[dt], len(sub)),
                                     "median": {k: float(np.median([f[k] for f in feats])) for k in FEATS},
                                     "dist": dists, "dist_mean": float(np.mean(vals)) if vals else None}
    Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", required=True, help="name=dir")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sets = dict(s.split("=", 1) for s in a.sets)
    res = summarize(sets, a.out)
    for name in sets:
        print("==", name)
        for dt, r in sorted(res["sets"][name].items()):
            o = res["odb"][dt]
            print(f"  {dt:13s} n={r['n']:4d} dist={r['dist_mean']:.2f} nn_sim={r['nn_sim']:.3f} (odb {r['odb_nn_sim_same_n']:.3f}) "
                  f"blocks={r['median']['n_blocks']:.0f}/{o['median']['n_blocks']:.0f} "
                  f"text_area={r['median']['text_area']:.2f}/{o['median']['text_area']:.2f} "
                  f"fig_area={r['median']['figure_area']:.2f}/{o['median']['figure_area']:.2f}")


if __name__ == "__main__":
    main()

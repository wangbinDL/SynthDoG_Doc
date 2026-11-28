"""Collect project statistics and page images into the portal folder (data.js + thumbnails).

  python3 scripts/build_portal.py --versions v0,v1,v2 --final-version v2 --out /data/synthdog-doc/portal
The page itself is portal/index.html (static, renders everything from data.js).
"""
import argparse
import collections
import glob
import json
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synthdog_doc.langs import LANG_ORDER, LANGS  # noqa: E402
from synthdog_doc.geometry import PAPER_MIX, PPT_MIX  # noqa: E402

ROOT = Path("/data/synthdog-doc")
TYPES = ["ppt", "exam", "paper_single", "paper_double", "newspaper", "magazine", "book", "textbook", "report"]
TYPE_ZH = {"ppt": "PPT 幻灯片", "exam": "试卷", "paper_single": "论文单栏", "paper_double": "论文双栏",
           "newspaper": "报纸", "magazine": "杂志", "book": "书籍", "textbook": "教材", "report": "研报"}
ROUNDS = {"v0": "r1", "v1": "r2", "v2": "r3", "v3": "r4", "v4": "r5"}
# version -> judge round that evaluated it (r1 judged v0, ...)


def _thumb(job):
    src, dst, size, q = job
    dst = Path(dst)
    if dst.exists():
        return str(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    im.thumbnail((size, size), Image.LANCZOS)
    im.save(dst, quality=q, optimize=True)
    return str(dst)


def norm_res(res):
    """Judge outputs are JSON objects; a few came back wrapped in a list."""
    if isinstance(res, list):
        res = next((x for x in res if isinstance(x, dict)), {})
    return res if isinstance(res, dict) else {}


def jl(p):
    p = Path(p)
    if not p.exists():
        return []
    out = []
    for x in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(x))
        except Exception:  # noqa: BLE001
            pass
    return out


def lang_table():
    d = json.loads((ROOT / "analysis/lang_ranking.json").read_text())
    rows = []
    sel = set(LANG_ORDER)
    code = {"Hindi": "hi", "Spanish": "es", "Arabic": "ar", "French": "fr", "Bengali": "bn", "Portuguese": "pt",
            "Indonesian": "id", "Urdu": "ur", "Russian": "ru", "German": "de", "English": "en", "Mandarin": "zh",
            "Japanese": "ja"}
    for i, r in enumerate(d["rows"][:16], 1):
        c = next((v for k, v in code.items() if k in r["language"]), None)
        note = ""
        if c in ("en", "zh"):
            note = "排除（中英文）"
        elif c in sel:
            note = "入选"
        elif c == "ja":
            note = "第 11 位（Top-10 之外）"
        rows.append({"rank": i, "language": r["language"], "family": r["family"], "l1": r["l1_m"], "l2": r["l2_m"],
                     "total": r["total_m"], "code": c, "selected": c in sel, "note": note})
    return {"source": d["source"], "url": d["url"], "rows": rows}


def corpus_stats():
    out = {}
    for lang in LANG_ORDER:
        L = LANGS[lang]
        web = jl(ROOT / f"corpus/{lang}/web.jsonl")
        kinds = collections.Counter(r.get("kind") for r in web)
        doms = collections.Counter(r.get("domain") for r in web if r.get("kind") == "national")
        packs = {}
        for k in ("paper", "exam", "ppt", "report", "lesson", "news", "feature"):
            packs[k] = len(jl(ROOT / f"content/{lang}/{k}.jsonl"))
        ads = 0
        for r in jl(ROOT / f"content/{lang}/ads.jsonl"):
            ads += len(r.get("ads") or r.get("items") or [])
        packs["ads"] = ads
        photos = {}
        for k in ("news", "lesson", "ppt", "feature"):
            rows = jl(ROOT / f"content/{lang}/{k}_photos.jsonl")
            photos[k] = sum(len(r.get("photos") or []) for r in rows)
        out[lang] = {"name": L.name, "native": L.native, "script": L.script, "rtl": L.rtl,
                     "countries": list(L.countries), "wiki": len(jl(ROOT / f"corpus/{lang}/wiki.jsonl")),
                     "web": len(web), "national": kinds.get("national", 0), "news": kinds.get("news", 0),
                     "top_domains": doms.most_common(6), "packs": packs, "photos": photos,
                     "news_domains_cfg": len(L.news_domains), "tlds": list(L.country_tlds)[:8]}
    return out


def font_stats():
    m = json.loads((ROOT / "fonts/font_manifest.json").read_text())
    by = collections.Counter()
    fams = collections.defaultdict(set)
    for f in m:
        for s, v in (f.get("coverage") or {}).items():
            if v >= 0.9:
                by[s] += 1
                fams[s].add(f["family"])
    from synthdog_doc import fonts as F
    pools = {}
    for script, roles in F.POOLS.items():
        pools[script] = {role: sorted({x if isinstance(x, str) else x[0] for x in fams_})[:12]
                         for role, fams_ in roles.items()}
    return {"files": len(m), "families": len({f["family"] for f in m}), "by_script_files": dict(by),
            "by_script_families": {k: len(v) for k, v in fams.items()}, "pools": pools}


def asset_stats():
    raw = len(list((ROOT / "assets_raw").glob("*.jpg")))
    out = {"raw_crops": raw}
    topics = collections.Counter()
    for k in ("photo", "photo_gray", "diagram"):
        rows = jl(ROOT / f"assets/{k}/index.jsonl")
        out[k] = len(rows)
        if k != "diagram":
            ok = [r for r in rows if r.get("ok") is not False and r.get("subject")]
            out[k + "_usable"] = len(ok)
            topics.update(r.get("topic") for r in ok)
    out["topics"] = topics.most_common()
    return out


def odb_stats():
    d = json.loads((ROOT / "analysis/odb_stats.json").read_text())
    keep = {}
    for src, v in d.items():
        keep[src] = {"n": v.get("n"), "width": v.get("width"), "height": v.get("height"),
                     "aspect": v.get("aspect_h_over_w"), "paper": v.get("nearest_paper"),
                     "layout": v.get("layout"), "language": v.get("language")}
    geo = {t: [{"w": w, "paper": p, "orient": o} for w, p, o in PAPER_MIX[t]] for t in PAPER_MIX}
    geo["ppt"] = [{"w": w, "paper": r, "orient": "l"} for w, r in PPT_MIX]
    return {"odb": keep, "geometry": geo}


def judge_rounds():
    out = {}
    for rd in sorted((ROOT / "judge").glob("r*")):
        s = rd / "summary.json"
        if s.exists():
            out[rd.name] = json.loads(s.read_text())
    return out


def single_index():
    """(doc_type, lang, version) -> {judge: compact result} from all rounds."""
    idx = {}
    for rd in sorted((ROOT / "judge").glob("r*")):
        for r in jl(rd / "results.jsonl"):
            if r.get("kind") != "single" or r.get("truth") != "synthetic" or "result" not in r:
                continue
            m = re.search(r"__v(\d+)__", r["path"])
            if not m:
                continue
            v = "v" + m.group(1)
            res = norm_res(r["result"])
            flaws = [{"sev": f.get("severity"), "type": f.get("issue_type"), "where": f.get("region"),
                      "what": f.get("evidence")} for f in (res.get("flaws") or [])[:4]]
            idx.setdefault(f"{r['doc_type']}|{r['lang']}|{v}", {})[r["judge"]] = {
                "verdict": res.get("verdict"), "conf": res.get("confidence"), "scores": res.get("scores"),
                "summary": res.get("summary"), "flaws": flaws, "round": rd.name}
    return idx


def pair_index():
    idx = {}
    for rd in sorted((ROOT / "judge").glob("r*")):
        for r in jl(rd / "results.jsonl"):
            if r.get("kind") != "pair" or "result" not in r:
                continue
            res = norm_res(r["result"])
            new_won = res.get("winner") == r.get("new_is")
            key = f"{r['doc_type']}|{r['lang']}|v{r['versions'][1]}"
            idx.setdefault(key, {})[r["judge"]] = {"new_won": new_won, "tie": res.get("winner") == "tie",
                                                   "conf": res.get("confidence"),
                                                   "reasons": (res.get("reasons") or [])[:2]}
    return idx


def grid_index():
    out = {}
    for rd in sorted((ROOT / "judge").glob("r*")):
        for r in jl(rd / "results.jsonl"):
            if r.get("kind") != "grid" or "result" not in r:
                continue
            res = norm_res(r["result"])
            out.setdefault(rd.name, {}).setdefault(r["doc_type"], {})[r["judge"]] = {
                "diversity": res.get("diversity_score"), "templates": res.get("estimated_distinct_templates"),
                "realism": res.get("realism_of_set"), "missing": (res.get("missing_structures") or [])[:4],
                "recs": (res.get("top_recommendations") or [])[:3]}
    return out


def signoff_index():
    out = {}
    for rd in sorted((ROOT / "judge").glob("signoff*")):
        for r in jl(rd / "results.jsonl"):
            if "result" not in r:
                continue
            out.setdefault(rd.name, {}).setdefault(r["doc_type"], {})[r["judge"]] = norm_res(r["result"])
    return out


def signoff_final():
    """Latest sign-off status per (doc type, judge) across batches: a verdict, or 'refused' when the most recent
    request for that type was declined by the model's safety filter (earlier verdict kept for reference)."""
    out = {}
    for sd in sorted((ROOT / "judge").glob("signoff_v*"), key=lambda p: int(p.name.split("_v")[1])):
        for r in jl(sd / "results.jsonl"):
            key = (r.get("doc_type"), r.get("judge"))
            cur = out.setdefault(key, {"status": None, "batch": None, "prev": None})
            res = norm_res(r.get("result")) if "result" in r else None
            if res:
                cur.update(status="verdict", batch=sd.name, diversity=res.get("diversity"),
                           realism=res.get("realism"), rationale=res.get("rationale"))
                cur["prev"] = {"batch": sd.name, "diversity": res.get("diversity"), "realism": res.get("realism")}
            elif "refusal" in str(r.get("error", "")):
                cur.update(status="refused", batch=sd.name)
    table = {}
    for (t, j), v in out.items():
        table.setdefault(t, {})[j] = v
    return table


def page_meta(p):
    mf = Path(str(p).replace(".jpg", ".meta.json"))
    if not mf.exists():
        return {}
    m = json.loads(mf.read_text())
    pg = m.get("page") or {}
    fonts = m.get("fonts") or {}
    return {"paper": pg.get("paper"), "dpi": round(pg.get("dpi") or 0), "size": m.get("size"),
            "role": m.get("page_role"), "branch": (m.get("degrade") or {}).get("branch"),
            "layout": m.get("layout"), "profile": m.get("profile"), "font": fonts.get("serif") or fonts.get("sans"),
            "blocks": m.get("n_blocks")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", default="v0,v1,v2")
    ap.add_argument("--final-version", default="v2")
    ap.add_argument("--final-samples", default=str(ROOT / "portal_final_src"),
                    help="dir with sampled pages of the full generation (copied there by the worker)")
    ap.add_argument("--out", default=str(ROOT / "portal"))
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    out = Path(a.out)
    vers = a.versions.split(",")
    jobs = []
    data = {"generated": time.strftime("%Y-%m-%d %H:%M"), "types": TYPES, "type_zh": TYPE_ZH, "langs": LANG_ORDER,
            "versions": vers, "final_version": a.final_version}
    # ---------------------------------------------------------------- pages of each version
    cases, gallery = {}, {}
    for v in vers:
        rdir = ROOT / "renders" / v
        for t in TYPES:
            for lang in LANG_ORDER:
                for i in range(4):
                    name = f"{t}__{lang}__{v}__{i:04d}"
                    src = rdir / f"{name}.jpg"
                    if not src.exists():
                        continue
                    th = f"thumbs/{v}/{name}.jpg"
                    jobs.append((str(src), str(out / th), 460, 80))
                    rec = {"name": name, "lang": lang, "idx": i, "thumb": th, **page_meta(src)}
                    if i == 0 or (v == a.final_version and i == 1):
                        md = f"med/{v}/{name}.jpg"
                        jobs.append((str(src), str(out / md), 1500, 82))
                        rec["med"] = md
                    ov = rdir / f"{name}.overlay.jpg"
                    if v == a.final_version and i <= 1 and ov.exists():
                        ovp = f"ov/{v}/{name}.jpg"
                        jobs.append((str(ov), str(out / ovp), 1500, 78))
                        rec["ov"] = ovp
                    if i == 0:
                        cases.setdefault(t, {}).setdefault(lang, {})[v] = rec
                    if v == a.final_version:
                        gallery.setdefault(t, []).append(rec)
    data["cases"], data["gallery"] = cases, gallery
    # ---------------------------------------------------------------- final full-generation samples
    fs = Path(a.final_samples)
    final = []
    if fs.exists():
        for src in sorted(fs.glob("*.jpg")):
            if src.name.endswith(".overlay.jpg"):
                continue
            name = src.stem
            t, lang = name.split("__")[:2]
            th, md = f"final/thumbs/{name}.jpg", f"final/med/{name}.jpg"
            jobs += [(str(src), str(out / th), 460, 80), (str(src), str(out / md), 1500, 82)]
            rec = {"name": name, "type": t, "lang": lang, "thumb": th, "med": md, **page_meta(src)}
            ov = src.with_name(name + ".overlay.jpg")
            if ov.exists():
                jobs.append((str(ov), str(out / f"final/ov/{name}.jpg"), 1500, 78))
                rec["ov"] = f"final/ov/{name}.jpg"
            final.append(rec)
    data["final_samples"] = final
    stats_f = fs / "final_stats.json"
    data["final_stats"] = json.loads(stats_f.read_text()) if stats_f.exists() else None
    if data["final_stats"] and data["final_stats"].get("json_example"):
        # compact number arrays (polygons) so the example reads like the real file
        ex = data["final_stats"]["json_example"]
        ex = re.sub(r"\[\s*((?:-?[\d.]+,\s*)*-?[\d.]+)\s*\]",
                    lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",")) + "]", ex)
        data["final_stats"]["json_example"] = ex
    # ---------------------------------------------------------------- real reference pages (layout reference)
    real = []
    tasks = jl(ROOT / "judge/r3/results.jsonl") or jl(ROOT / "judge/r2/results.jsonl")
    seen = set()
    for r in tasks:
        if r.get("kind") == "single" and r.get("truth") == "real" and r["path"] not in seen:
            seen.add(r["path"])
            nm = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(r["path"]).stem)[:60]
            md = f"real/{r['doc_type']}__{r['lang']}__{nm}.jpg"
            jobs.append((r["path"], str(out / md), 1300, 80))
            real.append({"type": r["doc_type"], "lang": r["lang"], "med": md, "src": r.get("real_src")})
    data["real"] = real
    # ---------------------------------------------------------------- judge grids per round
    grids = {}
    for rd in sorted((ROOT / "judge").glob("r*")):
        for t in TYPES:
            g = rd / f"grid_{t}.jpg"
            if g.exists():
                gp = f"grids/{rd.name}/{t}.jpg"
                jobs.append((str(g), str(out / gp), 1700, 80))
                grids.setdefault(rd.name, {})[t] = gp
    data["grids"] = grids
    # ---------------------------------------------------------------- stats
    data["ranking"] = lang_table()
    data["corpus"] = corpus_stats()
    data["fonts"] = font_stats()
    data["assets"] = asset_stats()
    data.update(odb_stats())
    data["judge"] = judge_rounds()
    data["single"] = single_index()
    data["pairs"] = pair_index()
    data["grid_scores"] = grid_index()
    data["signoff"] = signoff_index()
    data["signoff_final"] = signoff_final()
    lint = ROOT / "metrics/lint_all.json"
    if lint.exists():
        L = json.loads(lint.read_text())
        data["lint"] = {Path(k).name: v["summary"] for k, v in L.items()}
        data["lint_examples"] = {Path(k).name: v["examples"] for k, v in L.items()}
    met = ROOT / "metrics/metrics_all.json"
    if met.exists():
        data["metrics"] = json.loads(met.read_text())
    for key in ("changelog", "conclusions"):
        f = ROOT / f"portal_src/{key}.json"
        if f.exists():
            data[key] = json.loads(f.read_text())
    # ---------------------------------------------------------------- images
    with ProcessPoolExecutor(a.procs) as ex:
        list(ex.map(_thumb, jobs, chunksize=8))
    (out / "data.js").write_text("window.SDD = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    print("images", len(jobs), "data.js", (out / "data.js").stat().st_size)


if __name__ == "__main__":
    main()

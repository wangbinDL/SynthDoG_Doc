"""Batch generation: (doc_type, lang, index) jobs -> image + ODB json + markdown + meta (+ overlay).

  python3 -m synthdog_doc.generate --types paper_double --langs hi,ar --n 4 --out /data/synthdog-doc/renders/dev
"""
import argparse
import asyncio
import io
import json
import multiprocessing as mp
import os
import random
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from PIL import Image

from . import export as X
from .degrade import degrade, pick_branch, remember_page
from .langs import LANG_ORDER, LANGS
from .render import Renderer

ODB_SOURCE = {"ppt": "PPT2PDF", "paper_single": "academic_literature", "paper_double": "academic_literature",
              "book": "book", "exam": "exam_paper", "magazine": "magazine", "newspaper": "newspaper",
              "textbook": "colorful_textbook", "report": "research_report"}
DOC_TYPES = ["ppt", "exam", "paper_single", "paper_double", "newspaper", "magazine", "book", "textbook", "report"]


def build_spec(doc_type, lang, rng, version):
    from .doctypes import registry
    return registry.make(doc_type, lang, rng, version)


def job_name(doc_type, lang, idx, version):
    return f"{doc_type}__{lang}__v{version}__{idx:04d}"


def finalize(name, spec, png, gt, out_dir, rng, do_degrade=True, overlay=False, branch=None):
    img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
    scale = img.shape[1] / gt["page"]["w"]
    blocks = X.build(gt, scale)
    polys, index = X.collect_polys(blocks)
    branch = branch or (pick_branch(spec.doc_type, rng) if do_degrade else "digital")
    if do_degrade:
        from . import degrade as _D
        _D._CUR.update(lang=spec.lang, doc_type=spec.doc_type)
        img2, polys2, dparams = degrade(img, polys, branch, rng)
        remember_page(img, lang=spec.lang)
        X.scatter_polys(blocks, polys2, index)
    else:
        img2, dparams = img, {"branch": "none"}
    h, w = img2.shape[:2]
    meta = spec.meta
    issues = list(meta.get("special_issue", []))
    if dparams.get("branch") == "photo":
        issues.append("geometric_deformation")
    if dparams.get("branch") == "scan" and dparams.get("blur", 0) > 0.6:
        issues.append("fuzzy_scan")
    page_info = {"page_no": 0, "height": h, "width": w, "image_path": f"{name}.jpg",
                 "page_attribute": {"data_source": ODB_SOURCE.get(spec.doc_type, spec.doc_type),
                                    "language": LANGS[spec.lang].name.lower(),
                                    "layout": meta.get("layout", "other_layout"),
                                    "special_issue": issues or ["None"]}}
    odb = X.to_odb(blocks, page_info)
    md = X.to_markdown(blocks)
    out_dir = Path(out_dir)
    Image.fromarray(img2).save(out_dir / f"{name}.jpg", quality=93)
    X.save_json(out_dir / f"{name}.json", odb)
    (out_dir / f"{name}.md").write_text(md, encoding="utf-8")
    m = {"name": name, **meta, "degrade": dparams, "render": {k: gt.get(k) for k in ("layout", "font_errors",
                                                                                         "render_sec", "stats")},
         "n_blocks": len(blocks), "size": [w, h]}
    X.save_json(out_dir / f"{name}.meta.json", m)
    if overlay:
        X.overlay(img2, blocks, lines=True).save(out_dir / f"{name}.overlay.jpg", quality=80)
    return m


async def _run_chunk(jobs, out_dir, version, do_degrade, overlay, concurrency, keep_html):
    results = []
    async with Renderer(concurrency=concurrency) as R:
        async def one(job):
            doc_type, lang, idx, seed = job
            name = job_name(doc_type, lang, idx, version)
            if (Path(out_dir) / f"{name}.json").exists():
                return {"name": name, "skipped": True}
            rng = random.Random(f"{seed}|{doc_type}|{lang}|{idx}")
            t0 = time.time()
            for attempt in range(3):
                try:
                    spec = build_spec(doc_type, lang, rng, version)
                    png, gt = await R.render(spec, name, keep_html=keep_html)
                    m = finalize(name, spec, png, gt, out_dir, rng, do_degrade, overlay)
                    m["sec"] = round(time.time() - t0, 2)
                    return m
                except Exception as e:  # noqa: BLE001
                    err = f"{type(e).__name__}: {e}"
                    tb = traceback.format_exc(limit=4)
            return {"name": name, "error": err, "tb": tb}
        results = await asyncio.gather(*[one(j) for j in jobs])
    return results


def _worker(args):
    jobs, out_dir, version, do_degrade, overlay, concurrency, keep_html = args
    return asyncio.run(_run_chunk(jobs, out_dir, version, do_degrade, overlay, concurrency, keep_html))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", default=",".join(DOC_TYPES))
    ap.add_argument("--langs", default=",".join(LANG_ORDER))
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--version", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--no-degrade", action="store_true")
    ap.add_argument("--overlay", action="store_true")
    ap.add_argument("--keep-html", action="store_true")
    ap.add_argument("--chunk", type=int, default=8)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(t, l, i, a.seed) for t in a.types.split(",") for l in a.langs.split(",")
            for i in range(a.start, a.start + a.n)]
    random.Random(0).shuffle(jobs)
    chunks = [jobs[i:i + a.chunk] for i in range(0, len(jobs), a.chunk)]
    args = [(c, str(out), a.version, not a.no_degrade, a.overlay, a.concurrency, a.keep_html) for c in chunks]
    t0 = time.time()
    n_ok = n_err = 0
    logf = open(out / "_gen_log.jsonl", "a", encoding="utf-8")
    if a.procs <= 1:
        it = map(_worker, args)
    else:
        pool = mp.get_context("spawn").Pool(a.procs, maxtasksperchild=4)
        it = pool.imap_unordered(_worker, args)
    for res in it:
        for m in res:
            logf.write(json.dumps({k: m.get(k) for k in ("name", "error", "sec", "n_blocks", "skipped", "render",
                                                       "tb")}, ensure_ascii=False) + "\n")
            logf.flush()
            if m.get("error"):
                n_err += 1
                print("ERR", m["name"], m["error"], flush=True)
            else:
                n_ok += 1
        print(f"progress ok={n_ok} err={n_err} elapsed={time.time() - t0:.0f}s", flush=True)
    print(f"GEN_DONE ok={n_ok} err={n_err} sec={time.time() - t0:.0f}", flush=True)


if __name__ == "__main__":
    sys.exit(main())

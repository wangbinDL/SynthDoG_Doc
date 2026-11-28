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


NO_BODY = {"header", "footer", "page_number", "abandon"}


class EmptyPage(RuntimeError):
    pass


def build_spec(doc_type, lang, rng, version):
    from .doctypes import registry
    return registry.make(doc_type, lang, rng, version)


def job_name(doc_type, lang, idx, version):
    return f"{doc_type}__{lang}__v{version}__{idx:04d}"


def finalize(name, spec, png, gt, out_dir, rng, do_degrade=True, overlay=False, branch=None, sink=None):
    """sink=None writes <name>.{jpg,json,md,meta.json}; a list collects the page for a parquet shard instead."""
    tf0 = time.time()
    img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
    scale = img.shape[1] / gt["page"]["w"]
    blocks = X.build(gt, scale)
    if spec.meta.get("page_role") != "advertisement" and all(b["cat"] in NO_BODY for b in blocks):
        # content ran out (e.g. a continuation page past the last question): retried with fresh draws by the caller
        raise EmptyPage(f"{name}: only page furniture, no body content")
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
    tf1 = time.time()
    buf = io.BytesIO()
    Image.fromarray(img2).save(buf, format="JPEG", quality=93)
    tf2 = time.time()
    timing = dict(gt.get("timing") or {}, degrade_export=round(tf1 - tf0, 3), jpeg=round(tf2 - tf1, 3))
    m = {"name": name, **meta, "degrade": dparams, "render": {k: gt.get(k) for k in ("layout", "font_errors",
                                                                                         "render_sec", "stats")},
         "n_blocks": len(blocks), "size": [w, h], "timing": timing}
    if sink is not None:
        sink.append({"name": name, "doc_type": spec.doc_type, "lang": spec.lang, "branch": dparams.get("branch"),
                     "width": w, "height": h, "image": buf.getvalue(), "odb": json.dumps(odb, ensure_ascii=False),
                     "markdown": md, "meta": json.dumps(m, ensure_ascii=False)})
    else:
        (out_dir / f"{name}.jpg").write_bytes(buf.getvalue())
        X.save_json(out_dir / f"{name}.json", odb)
        (out_dir / f"{name}.md").write_text(md, encoding="utf-8")
        X.save_json(out_dir / f"{name}.meta.json", m)
    m["timing"]["write"] = round(time.time() - tf2, 3)
    if overlay:
        X.overlay(img2, blocks, lines=True).save(out_dir / f"{name}.overlay.jpg", quality=80)
    return m


async def _run_jobs(R, jobs, out_dir, version, do_degrade, overlay, keep_html, sink=None):
    async def one(job):
        doc_type, lang, idx, seed = job
        name = job_name(doc_type, lang, idx, version)
        if sink is None and (Path(out_dir) / f"{name}.json").exists():
            return {"name": name, "skipped": True}
        rng = random.Random(f"{seed}|{doc_type}|{lang}|{idx}")
        t0 = time.time()
        for attempt in range(3):
            try:
                tb0 = time.time()
                spec = build_spec(doc_type, lang, rng, version)
                build_s = round(time.time() - tb0, 3)
                png, gt = await R.render(spec, name, keep_html=keep_html)
                m = finalize(name, spec, png, gt, out_dir, rng, do_degrade, overlay, sink=sink)
                m["timing"]["build"] = build_s
                m["sec"] = round(time.time() - t0, 2)
                return m
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
                tb = traceback.format_exc(limit=4)
        return {"name": name, "error": err, "tb": tb}
    return await asyncio.gather(*[one(j) for j in jobs])


async def _run_chunk(jobs, out_dir, version, do_degrade, overlay, concurrency, keep_html):
    async with Renderer(concurrency=concurrency) as R:
        return await _run_jobs(R, jobs, out_dir, version, do_degrade, overlay, keep_html)


# Persistent per-process browser (production mode): one Chromium per worker process, reused across chunks and
# recycled every RECYCLE_PAGES pages (bounded memory growth) or after an error.
_P = {"loop": None, "R": None}
RECYCLE_PAGES = int(os.environ.get("SDD_RECYCLE_PAGES", "400"))


def _renderer(concurrency, shot):
    if _P["loop"] is None:
        _P["loop"] = asyncio.new_event_loop()
        asyncio.set_event_loop(_P["loop"])
    R = _P["R"]
    if R is not None and R.pages >= RECYCLE_PAGES:
        _P["loop"].run_until_complete(R.__aexit__(None, None, None))
        R = None
    if R is None:
        R = Renderer(concurrency=concurrency, shot=shot)
        _P["loop"].run_until_complete(R.__aenter__())
        _P["R"] = R
    return R


def _write_shard(rows, out_dir, tag):
    import pyarrow as pa  # noqa: PLC0415
    import pyarrow.parquet as pq  # noqa: PLC0415
    d = Path(out_dir) / "shards"
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{tag}.parquet.tmp"
    pq.write_table(pa.Table.from_pylist(rows), str(tmp), compression="zstd", row_group_size=64)
    tmp.rename(d / f"{tag}.parquet")


def _worker(args):
    jobs, out_dir, version, do_degrade, overlay, concurrency, keep_html = args[:7]
    opts = args[7] if len(args) > 7 else {}
    if not opts.get("persistent"):
        return asyncio.run(_run_chunk(jobs, out_dir, version, do_degrade, overlay, concurrency, keep_html))
    try:                                   # one OpenCV thread per process: dozens of workers share the machine
        import cv2  # noqa: PLC0415
        cv2.setNumThreads(1)
    except Exception:  # noqa: BLE001
        pass
    tag = job_name(*jobs[0][:3], version) + f"__{len(jobs)}"
    if opts.get("format") == "parquet" and (Path(out_dir) / "shards" / f"{tag}.parquet").exists():
        return [{"name": tag, "skipped": True}]
    sink = [] if opts.get("format") == "parquet" else None
    try:
        R = _renderer(concurrency, opts.get("shot", "png"))
        res = _P["loop"].run_until_complete(_run_jobs(R, jobs, out_dir, version, do_degrade, overlay, keep_html,
                                                      sink=sink))
    except Exception:  # noqa: BLE001  -- browser died: recycle and report the chunk as failed
        try:
            _P["loop"].run_until_complete(_P["R"].__aexit__(None, None, None))
        except Exception:  # noqa: BLE001
            pass
        _P["R"] = None
        raise
    if any(m.get("error") for m in res) and _P["R"] is not None:
        _P["R"].pages = RECYCLE_PAGES      # recycle the browser after a failing chunk
    if sink:
        _write_shard(sink, out_dir, tag)
    return res


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
    ap.add_argument("--persistent", action="store_true", help="production mode: browser kept alive per process")
    ap.add_argument("--format", choices=["files", "parquet"], default="files",
                    help="files: 4 files per page; parquet: one zstd shard per chunk under <out>/shards/")
    ap.add_argument("--shot", choices=["png", "jpeg"], default="png")
    ap.add_argument("--max-tasks", type=int, default=4, help="chunks per worker process before it is replaced")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(t, l, i, a.seed) for t in a.types.split(",") for l in a.langs.split(",")
            for i in range(a.start, a.start + a.n)]
    random.Random(0).shuffle(jobs)
    chunks = [jobs[i:i + a.chunk] for i in range(0, len(jobs), a.chunk)]
    opts = {"persistent": a.persistent, "format": a.format, "shot": a.shot}
    args = [(c, str(out), a.version, not a.no_degrade, a.overlay, a.concurrency, a.keep_html, opts) for c in chunks]
    t0 = time.time()
    n_ok = n_err = 0
    logf = open(out / "_gen_log.jsonl", "a", encoding="utf-8")
    if a.procs <= 1:
        it = map(_worker, args)
    else:
        pool = mp.get_context("spawn").Pool(a.procs, maxtasksperchild=a.max_tasks if a.max_tasks > 0 else None)
        it = pool.imap_unordered(_worker, args)
    for res in it:
        for m in res:
            logf.write(json.dumps({k: m.get(k) for k in ("name", "error", "sec", "n_blocks", "skipped", "render",
                                                       "timing", "tb")}, ensure_ascii=False) + "\n")
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

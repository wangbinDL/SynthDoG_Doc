"""Regenerate listed pages of a parquet production run in place (e.g. pages found defective by prod_verify.py).

  python3 scripts/prod_patch.py --root /mnt/wangbin02-jfs/processed/synthdog_doc/prod200k \
      --list /data/synthdog-doc/portal_src/prod200k_empty_md.json --seed 20261128 --version 7

Each listed page is rebuilt with the current generator (same name, same seed; generate.finalize now rejects pages
without body content, so the retry draws a fresh layout), then every shard holding a listed page is rewritten with
the new rows in place of the old ones (written to a temp file, then renamed). A log of replaced pages goes to
<root>/_patches.jsonl.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synthdog_doc import generate as G  # noqa: E402
from synthdog_doc.render import Renderer  # noqa: E402


async def regen(jobs, version):
    sink = []
    async with Renderer(concurrency=2, shot="jpeg") as R:
        res = await G._run_jobs(R, jobs, "/tmp", version, True, False, False, sink=sink)
    return {r["name"]: r for r in sink}, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--list", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--version", type=int, required=True)
    a = ap.parse_args()
    items = json.loads(Path(a.list).read_text())
    want = {}
    for it in items:
        want.setdefault(it["group"], set()).add(it["name"])
    jobs = []
    for names in want.values():
        for n in names:
            t, lg, v, idx = n.split("__")
            jobs.append((t, lg, int(idx), a.seed))
    new, res = asyncio.run(regen(jobs, a.version))
    errs = [r for r in res if r.get("error")]
    print(f"regenerated {len(new)} / {len(jobs)} pages, errors {len(errs)}", flush=True)
    for r in errs:
        print("ERR", r["name"], r["error"], flush=True)
    log = open(Path(a.root) / "_patches.jsonl", "a", encoding="utf-8")
    n_rows = 0
    for g, names in want.items():
        for sp in sorted((Path(a.root) / g / "shards").glob("*.parquet")):
            hit = set(pq.read_table(sp, columns=["name"]).column("name").to_pylist()) & names
            hit &= set(new)
            if not hit:
                continue
            rows = pq.read_table(sp).to_pylist()
            rows = [new[r["name"]] if r["name"] in hit else r for r in rows]
            tmp = sp.with_suffix(".parquet.tmp")
            pq.write_table(pa.Table.from_pylist(rows), str(tmp), compression="zstd", row_group_size=64)
            tmp.rename(sp)
            n_rows += len(hit)
            for n in sorted(hit):
                log.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "group": g, "shard": sp.name,
                                      "name": n, "reason": "empty body (only page furniture)"}) + "\n")
            print("patched", sp.name, sorted(hit), flush=True)
    print(f"PATCH_DONE rows={n_rows}", flush=True)


if __name__ == "__main__":
    main()

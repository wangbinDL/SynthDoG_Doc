"""Move platform-downloaded HF parquet shards from OSS to JFS public_data/, verify them and write READMEs.

Runs on a worker with JFS mounted:  python3 ingest_shards.py <oss_manifest.json> /mnt/wangbin02-jfs/public_data
The platform inserts hashes into file names, so files are identified by size, then renamed to the HF shard name:
  public_data/<dataset short name>/<config>/<shard>.parquet
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

man = json.load(open(sys.argv[1]))
root = Path(sys.argv[2])
fast = "/data/osworld-v2-1029/scripts/fast_oss2jfs.py"
report = []
for m in man:
    ds = m["dataset"].split("/")[1]
    dst = root / ds / m["config"] / m["shard"]
    rec = {"name": m["name"], "dataset": m["dataset"], "config": m["config"], "shard": m["shard"], "size": m["size"],
           "url": m["url"], "dst": str(dst)}
    if dst.exists() and dst.stat().st_size == m["size"]:
        rec["status"] = "exists"
    else:
        inc = root / "_incoming" / m["name"]
        t0 = time.time()
        for pre in m["prefixes"]:
            subprocess.run([sys.executable, fast, pre, str(inc), "32"], check=False)
        cand = [p for p in inc.rglob("*") if p.is_file() and p.stat().st_size == m["size"]]
        if not cand:
            rec["status"] = "size_mismatch"
            rec["found"] = [(str(p), p.stat().st_size) for p in inc.rglob("*") if p.is_file()][:5]
            report.append(rec)
            print(json.dumps(rec, ensure_ascii=False), flush=True)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(cand[0]), str(dst))
        shutil.rmtree(inc, ignore_errors=True)
        rec["sec"] = round(time.time() - t0, 1)
        rec["status"] = "moved"
    try:
        md = pq.ParquetFile(str(dst)).metadata
        rec["rows"] = md.num_rows
        rec["row_groups"] = md.num_row_groups
    except Exception as e:  # noqa: BLE001
        rec["status"] = "bad_parquet"
        rec["error"] = repr(e)[:200]
    report.append(rec)
    print(json.dumps(rec, ensure_ascii=False), flush=True)
(root / "_ingest_report_sdd.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
today = time.strftime("%Y-%m-%d")
for ds, desc in (("finepdfs", "HuggingFaceFW/finepdfs：CommonCrawl 真实 PDF 抽取全文（ODC-By），每语种 1 个分片，含 WARC 指针"),
                 ("fineweb-2", "HuggingFaceFW/fineweb-2：多语种网页正文（ODC-By），每语种 1 个分片")):
    rows = [r for r in report if r["dataset"].endswith(ds) and r.get("rows")]
    if not rows:
        continue
    lines = [f"# {ds}", "", desc, "", f"- 下载：{today}，经数采平台 common_file_downloader（HF commit 固定，见 url）",
             "- 用途：SynthDoG-Doc 第二阶段大规模真实文本池 / 真实评测集候选", "", "| config | shard | rows | GB | url |",
             "|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["config"]):
        lines.append(f"| {r['config']} | {r['shard']} | {r['rows']} | {r['size'] / 1e9:.2f} | {r['url']} |")
    (root / ds / "README.md").write_text("\n".join(lines) + "\n")
idx = root / "README.md"
txt = idx.read_text() if idx.exists() else "# public_data\n"
for ds, line in (("finepdfs", f"- finepdfs/ — HF HuggingFaceFW/finepdfs 每语种 1 分片（30 语种），CommonCrawl 真实 PDF 全文，{today}"),
                 ("fineweb-2", f"- fineweb-2/ — HF HuggingFaceFW/fineweb-2 每语种 1 分片（28 语种），多语种网页正文，{today}")):
    if f"- {ds}/" not in txt:
        txt = txt.rstrip("\n") + "\n" + line + "\n"
idx.write_text(txt)
print("INGEST_DONE", sum(1 for r in report if r.get("rows")), "/", len(report), flush=True)

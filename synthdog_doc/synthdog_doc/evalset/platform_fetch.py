"""Real-document eval set, step 3b: fetch candidate PDFs through the company data platform (data-turing).

CommonCrawl's CDN throttles our shared egress IP (HTTP 503, 6-20 s per range request), so the shortlisted documents'
original URLs are handed to the platform's common_file_downloader (overseas bandwidth). Results land in OSS:
<resource>/success/<name>.meta.json carries the source URL of object <name>; failures are <resource>/failure/*.json.

  python3 -m synthdog_doc.evalset.platform_fetch submit --triage /data/synthdog-doc/evalset/triage --out /data/synthdog-doc/evalset/pdfs
  python3 -m synthdog_doc.evalset.platform_fetch ingest --out /data/synthdog-doc/evalset/pdfs     (OSS creds in env)

ingest writes <out>/<lang>/<id>.pdf (PDF magic checked) and appends to <out>/fetch_log.jsonl like fetch_pdfs.py.
"""
import argparse
import collections
import hashlib
import json
import os
import sys
from pathlib import Path

from .fetch_pdfs import WANT, pdf_stats

PLAT = "/data/synthdog-doc/scripts"


def shortlist(triage, per_cell=15, min_conf=0.6):
    jobs = []
    for f in sorted(Path(triage).glob("*.jsonl")):
        rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        cells = collections.defaultdict(list)
        for r in rows:
            if r.get("type") in WANT and r.get("lang_ok") and (r.get("conf") or 0) >= min_conf:
                cells[r["type"]].append(r)
        for rs in cells.values():
            rs.sort(key=lambda r: -(r.get("conf") or 0))
            per_dom, picked = collections.Counter(), []
            for r in rs:
                if per_dom[r["domain"]] >= 3:
                    continue
                per_dom[r["domain"]] += 1
                picked.append(r)
                if len(picked) >= per_cell:
                    break
            jobs += picked
    return jobs


def submit(a):
    sys.path.insert(0, PLAT)
    import plat  # noqa: PLC0415
    plat.LEDGER = str(Path(a.out) / "plat_tasks.jsonl")
    jobs = shortlist(a.triage, a.per_cell)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    have = {p.stem for p in Path(a.out).glob("*/*.pdf")}
    jobs = [j for j in jobs if j["id"] not in have and j["url"].startswith("http")]
    urls = list(dict.fromkeys(j["url"] for j in jobs))
    (Path(a.out) / "platform_batch.jsonl").write_text("".join(json.dumps(
        {k: j[k] for k in ("id", "lang", "type", "url", "domain")}, ensure_ascii=False) + "\n" for j in jobs))
    r = plat.post('/api/v1/tasks/run', {'task_type': 'common_file_downloader', 'name': f'sdd_evalset_pdfs_{len(urls)}',
                                         'task_input_type': 'array', 'task_input': {'url': urls},
                                         'notify_user_on_result': False})
    tid = (r.get('data') or {}).get('taskId')
    print(json.dumps(r, ensure_ascii=False)[:300], flush=True)
    if tid:
        with open(plat.LEDGER, "a") as fh:
            fh.write(json.dumps({"taskId": tid, "n_urls": len(urls), "batch": "platform_batch.jsonl"}) + "\n")
    print(f"submitted {len(urls)} URLs task={tid}", flush=True)


def ingest(a):
    import boto3  # noqa: PLC0415
    sys.path.insert(0, PLAT)
    import plat  # noqa: PLC0415
    out = Path(a.out)
    tasks = [json.loads(x) for x in (out / "plat_tasks.jsonl").read_text().splitlines() if x.strip()]
    batch = [json.loads(x) for x in (out / "platform_batch.jsonl").read_text().splitlines() if x.strip()]
    by_url = collections.defaultdict(list)
    for b in batch:
        by_url[b["url"]].append(b)
    s3 = boto3.client("s3", endpoint_url=os.environ["SHAI__OSS_ENDPOINT"],
                      aws_access_key_id=os.environ["SHAI__AWS_ACCESS_KEY_ID"],
                      aws_secret_access_key=os.environ["SHAI__AWS_SECRET_ACCESS_KEY"])
    stats = collections.Counter()
    for t in plat.status([x["taskId"] for x in tasks]):
        if t["status"] != "TASK_STATUS_EXPORTED" or not all(s == "SYNC_TASK_STATUS_COMPLETED" for s in t["sync_status"]):
            print("not ready:", t["taskId"], t["status"], t["sync_status"], flush=True)
            continue
        for rp in t["resource_paths"]:
            bucket, prefix = rp[len("shaipower://"):].split("/", 1)
            keys = [o["Key"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix + "/")
                    for o in pg.get("Contents", [])]
            for k in keys:
                if "/failure/" in k and k.endswith(".json"):
                    stats["platform_fail"] += 1
                    continue
                if not (k.endswith(".meta.json") and "/success/" in k):
                    continue
                meta = json.loads(s3.get_object(Bucket=bucket, Key=k)["Body"].read())
                if all((out / b["lang"] / f"{b['id']}.pdf").exists() for b in by_url.get(meta.get("url"), [])):
                    stats["already"] += 1
                    continue
                data = s3.get_object(Bucket=bucket, Key=k[:-len(".meta.json")])["Body"].read()
                pos = data[:1024].find(b"%PDF")
                for b in by_url.get(meta.get("url"), []):
                    dst = out / b["lang"] / f"{b['id']}.pdf"
                    res = {"id": b["id"], "lang": b["lang"], "type": b["type"], "url": b["url"], "domain": b["domain"],
                           "source": "platform_original_url"}
                    if pos < 0:
                        res["status"] = "not_pdf"
                    else:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        dst.write_bytes(data[pos:])
                        try:
                            pages, chars = pdf_stats(str(dst))
                            res.update(status="ok", bytes=len(data) - pos, pages=pages, text_chars=chars,
                                       sha256=hashlib.sha256(data[pos:]).hexdigest())
                        except Exception as e:  # noqa: BLE001
                            res.update(status="unreadable", error=repr(e)[:200])
                    stats[res["status"]] += 1
                    with open(out / "fetch_log.jsonl", "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(res, ensure_ascii=False) + "\n")
    print("INGEST", dict(stats), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["submit", "ingest"])
    ap.add_argument("--triage", default="/data/synthdog-doc/evalset/triage")
    ap.add_argument("--out", default="/data/synthdog-doc/evalset/pdfs")
    ap.add_argument("--per-cell", type=int, default=15)
    a = ap.parse_args()
    submit(a) if a.cmd == "submit" else ingest(a)


if __name__ == "__main__":
    main()

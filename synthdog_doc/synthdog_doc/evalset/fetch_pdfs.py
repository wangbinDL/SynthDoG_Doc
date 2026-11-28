"""Real-document eval set, step 3: fetch the original PDFs of shortlisted candidates from CommonCrawl.

FinePDFs keeps the CommonCrawl WARC file and record offset of every document; the record is one gzip member, so we
range-read from the offset (growing the window until the member ends), unpack the WARC + HTTP envelopes and keep the
PDF body. Public CommonCrawl data (https://data.commoncrawl.org), no crawling of the original sites.

  python3 -m synthdog_doc.evalset.fetch_pdfs --triage /data/synthdog-doc/evalset/triage \
      --out /data/synthdog-doc/evalset/pdfs --per-cell 15 --workers 8

Writes <out>/<lang>/<id>.pdf and appends {"id","lang","type","bytes","sha256","pages","text_chars","status"} to
<out>/fetch_log.jsonl. Idempotent: existing PDFs are skipped.
"""
import argparse
import collections
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

CC = "https://data.commoncrawl.org/"
WANT = ["slides", "exam", "academic_paper", "newspaper", "magazine", "book", "textbook", "report"]
_lock = threading.Lock()


def _opener():
    px = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    return urllib.request.build_opener(urllib.request.ProxyHandler({"https": px, "http": px} if px else {}))


OPENER = _opener()


_gate = threading.Lock()
_next_ok = [0.0]


def _throttle(min_gap):
    """Global request pacing: CommonCrawl's CDN answers 503 Slow Down to bursts from shared egress IPs."""
    with _gate:
        wait = _next_ok[0] - time.time()
        if wait > 0:
            time.sleep(wait)
        _next_ok[0] = time.time() + min_gap


def read_range(path, start, length, tries=6, min_gap=0.6):
    last = None
    for i in range(tries):
        _throttle(min_gap)
        try:
            req = urllib.request.Request(CC + path, headers={"Range": f"bytes={start}-{start + length - 1}",
                                                              "User-Agent": "synthdog-doc-research/0.2"})
            with OPENER.open(req, timeout=180) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503):          # slow down: back off globally
                with _gate:
                    _next_ok[0] = max(_next_ok[0], time.time() + min(120, 10 * 2 ** i))
            else:
                time.sleep(2 ** i)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"range read failed: {last}")


def fetch_original(url, max_bytes=64 << 20):
    """Fallback: the document's original URL (many government / university PDFs are still online)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (synthdog-doc-research)"})
    with OPENER.open(req, timeout=120) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise RuntimeError("original too large")
    return data if data[:1024].find(b"%PDF") >= 0 else None


def fetch_record(path, offset, max_bytes=64 << 20):
    """Return the decompressed WARC record starting at offset (one gzip member)."""
    size, buf = 256 << 10, b""
    while True:
        need = size - len(buf)
        buf += read_range(path, offset + len(buf), need)
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            rec = d.decompress(buf)
        except zlib.error as e:
            raise RuntimeError(f"bad gzip member: {e}") from e
        if d.eof:
            return rec
        if size >= max_bytes:
            raise RuntimeError("record larger than max_bytes")
        size *= 4


def pdf_body(rec):
    _, _, rest = rec.partition(b"\r\n\r\n")          # WARC header
    http, _, body = rest.partition(b"\r\n\r\n")       # HTTP header
    if b"chunked" in http.lower() and not body.startswith(b"%PDF"):
        out, i = b"", 0
        while i < len(body):
            j = body.find(b"\r\n", i)
            if j < 0:
                break
            n = int(body[i:j].split(b";")[0] or b"0", 16)
            if n == 0:
                break
            out += body[j + 2:j + 2 + n]
            i = j + 2 + n + 2
        body = out
    k = body.find(b"%PDF")
    return body[k:] if 0 <= k < 1024 else None


def pdf_stats(path):
    import fitz  # noqa: PLC0415
    doc = fitz.open(path)
    chars = sum(len(p.get_text("text")) for p in doc)
    return doc.page_count, chars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--triage", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-cell", type=int, default=15)
    ap.add_argument("--min-conf", type=float, default=0.6)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--langs", default="all")
    a = ap.parse_args()
    out = Path(a.out)
    jobs = []
    for f in sorted(Path(a.triage).glob("*.jsonl")):
        lang = f.stem
        if a.langs != "all" and lang not in a.langs.split(","):
            continue
        rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        cells = collections.defaultdict(list)
        for r in rows:
            if r.get("type") in WANT and r.get("lang_ok") and (r.get("conf") or 0) >= a.min_conf:
                cells[r["type"]].append(r)
        for t, rs in cells.items():
            rs.sort(key=lambda r: -(r.get("conf") or 0))
            per_domain = collections.Counter()
            picked = []
            for r in rs:                       # at most 3 candidates per web domain in a cell
                if per_domain[r["domain"]] >= 3:
                    continue
                per_domain[r["domain"]] += 1
                picked.append(r)
                if len(picked) >= a.per_cell:
                    break
            jobs += picked
    print(f"{len(jobs)} PDFs to fetch", flush=True)

    def work(r):
        d = out / r["lang"]
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{r['id']}.pdf"
        res = {"id": r["id"], "lang": r["lang"], "type": r["type"], "url": r["url"], "domain": r["domain"]}
        if not p.exists():
            try:
                body, src = pdf_body(fetch_record(r["file_path"], int(r["offset"]))), "commoncrawl"
            except Exception as e:  # noqa: BLE001
                body, src = None, f"cc_error:{e!r}"[:120]
            if not body:
                try:
                    raw = fetch_original(r["url"])
                    body, src = (raw[raw.find(b"%PDF"):] if raw else None), "original_url"
                except Exception as e:  # noqa: BLE001
                    return {**res, "status": "not_pdf", "error": f"{src} | orig:{e!r}"[:300]}
            if not body:
                return {**res, "status": "not_pdf", "error": src}
            res["source"] = src
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.rename(p)
        data = p.read_bytes()
        try:
            pages, chars = pdf_stats(str(p))
        except Exception as e:  # noqa: BLE001
            return {**res, "status": "unreadable", "error": repr(e)[:200]}
        return {**res, "status": "ok", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "pages": pages, "text_chars": chars}

    stats = collections.Counter()
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(work, r) for r in jobs]
        for k, f in enumerate(as_completed(futs), 1):
            try:
                res = f.result()
            except Exception as e:  # noqa: BLE001
                res = {"status": "error", "error": repr(e)[:200]}
            stats[res["status"]] += 1
            with _lock, open(out / "fetch_log.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            if k % 50 == 0:
                print(f"  {k}/{len(jobs)} {dict(stats)}", flush=True)
    print("FETCH_DONE", dict(stats), flush=True)


if __name__ == "__main__":
    main()

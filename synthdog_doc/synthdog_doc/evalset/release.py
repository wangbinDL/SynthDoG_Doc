"""Real-document eval set, step 7: package a release (OmniDocBench format, two licence tiers).

  python3 -m synthdog_doc.evalset.release --pages /data/synthdog-doc/evalset/pages \
      --candidates /data/synthdog-doc/evalset/candidates --out /data/synthdog-doc/evalset/release/v1

Tier A (government / education / inter-governmental domains, redistributable as a rule): page images ship with the
annotations. Tier B (everything else): only pointers ship -- original URL, CommonCrawl WARC file + offset, page index,
render DPI and the PDF's SHA-256 -- and render_pages.py rebuilds the identical page images locally. The tier is a
domain heuristic; each tier-A document still needs a licence check before a public release (the dataset card says so).

Writes <out>/omnidocbench_gt.json, manifest.jsonl, images/<page_id>.jpg (tier A), agreement.jsonl,
annotations/<annotator>/<page_id>.json (raw annotator answers, for leave-one-out GT), render_pages.py, README.md.
"""
import argparse
import collections
import json
import re
import shutil
from pathlib import Path

OPEN_DOMAIN = re.compile(r"(\.gov(\.[a-z]{2})?|\.gob\.[a-z]{2}|\.gouv\.[a-z]{2}|\.go\.(jp|kr|th|id)|\.gov\.[a-z]{2}|"
                         r"\.edu(\.[a-z]{2})?|\.ac\.[a-z]{2}|\.europa\.eu|\.un\.org|\.int|\.nic\.in)$")
LANG_EN = {"hi": "Hindi", "es": "Spanish", "ar": "Arabic", "fr": "French", "bn": "Bengali", "pt": "Portuguese",
           "id": "Indonesian", "ur": "Urdu", "ru": "Russian", "de": "German", "en": "English",
           "zh-Hans": "Chinese (Simplified)", "zh-Hant": "Chinese (Traditional)", "ja": "Japanese", "ko": "Korean",
           "vi": "Vietnamese", "th": "Thai", "tr": "Turkish", "fa": "Persian", "it": "Italian", "pl": "Polish",
           "nl": "Dutch"}
TYPES = ["ppt", "exam", "paper_single", "paper_double", "newspaper", "magazine", "book", "textbook", "report"]


def tier_of(domain):
    return "A" if OPEN_DOMAIN.search(domain or "") else "B"


def card(man, agree, out_dir):
    langs = collections.Counter(m["lang"] for m in man)
    types = collections.Counter(m["doc_type"] for m in man)
    tiers = collections.Counter(m["tier"] for m in man)
    docs = {m["doc_id"] for m in man}
    ca = [x["cat_agree"] for x in agree if x.get("cat_agree") is not None]
    oa = [x["order_agree"] for x in agree if x.get("order_agree") is not None]
    ts = collections.Counter()
    for x in agree:
        ts.update(x.get("text_source") or {})
    rows = "\n".join(f"| {LANG_EN.get(lg, lg)} | `{lg}` | " + " | ".join(
        str(sum(1 for m in man if m["lang"] == lg and m["doc_type"] == t)) for t in TYPES) + f" | {langs[lg]} |"
        for lg in sorted(langs, key=lambda l: list(LANG_EN).index(l) if l in LANG_EN else 99))
    text = f"""# SynthDoG-Doc RealEval v1 — multilingual real-document parsing benchmark

Real PDF pages in {len(langs)} languages and 9 layout families, annotated in the OmniDocBench format so that the
official OmniDocBench end-to-end scorer runs unchanged.

| | |
|---|---|
| Pages | {len(man)} |
| Source documents | {len(docs)} (at most 5 per language × layout cell, at most 2 pages each, at most 2 per web domain) |
| Languages | {len(langs)} |
| Licence tier A (images included) | {tiers.get('A', 0)} pages |
| Licence tier B (pointers + render script) | {tiers.get('B', 0)} pages |

## Pages per language and layout

| Language | Code | {' | '.join(TYPES)} | Total |
|---|---|{'---|' * len(TYPES)}---|
{rows}

## How it was built

1. **Candidates.** Random FinePDFs (ODC-By) documents per language; a text-only classifier (GPT-6.1-Sol) proposes the
   layout family from the first page's text.
2. **Originals.** PDFs fetched from the original URL (company data platform) or the CommonCrawl WARC record; a 4-page
   thumbnail sheet is checked by a VLM for layout family, column count (single- vs double-column papers), language
   and legibility.
3. **Pages.** Up to 2 random pages per document (covers skipped for books, textbooks, reports, magazines), rendered
   with PyMuPDF at long side ≈ 2000 px (DPI recorded per page).
4. **Regions.** Boxes come from the PP-DocLayoutV3 layout detector plus the PDF text layer (text-layer blocks the
   detector missed become extra regions); line boxes come from the text layer.
5. **Annotation.** Three annotators work independently on the same numbered-box image (set-of-mark): Gemini 4 Argon
   (effort high), GPT-6-Astra (max), Claude Opus 5.5 (max; xhigh fallback when max-effort thinking exhausted the
   output budget). Each fixes categories, drops false boxes, confirms or transcribes text, writes LaTeX for display
   formulas and HTML for tables, orders the regions and reports text no box covers.
6. **Consensus.** Category by majority vote; text from the PDF text layer when at least 2 annotators confirm it,
   otherwise the medoid of the three transcriptions; LaTeX / HTML by medoid; reading order by mean rank; text no box
   covers is added when at least 2 annotators report it (box copied from the neighbouring region and flagged
   `attribute.box_approx`); text blocks without any letter or digit (answer lines, leader dots) become `abandon`.

No human verification pass was run for v1. Annotator agreement: mean region-category agreement
{sum(ca) / max(1, len(ca)):.3f}, mean pairwise reading-order agreement {sum(oa) / max(1, len(oa)):.3f} (both can be
inflated by anchoring on the detector's proposals). Text sources: {dict(ts)}.

## Evaluating models that served as annotators

GPT-6-Astra and Claude Opus 5.5 are among the annotators. `annotations/<annotator>/` keeps every raw answer, so the
ground truth can be rebuilt without one annotator (leave-one-out) before scoring that model; Gemini 4 Argon, an
annotator that is not a benchmark subject, breaks ties.

## Files

- `omnidocbench_gt.json` — ground truth, one record per page; `page_info.page_attribute` adds `sdd_lang`,
  `sdd_doc_type`, `born_digital`.
- `manifest.jsonl` — per page: source URL, domain, PDF SHA-256, page index, DPI, image size, licence tier, CommonCrawl
  dump / WARC file / offset.
- `images/` — tier-A page images (`<page_id>.jpg`).
- `render_pages.py` — rebuilds any page image from the original PDF (URL or CommonCrawl WARC) and checks the SHA-256.
- `agreement.jsonl`, `annotations/` — per-page agreement statistics and raw annotator answers.

## Licence

Annotations: CC BY 4.0. Page images and underlying documents remain under their owners' terms: tier A ships images of
government / education / inter-governmental documents; tier B ships pointers only, for research use. The tier is
assigned from the web domain; **check each tier-A document's licence before redistributing**. Removal requests: open
an issue with the page id.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


RENDER = '''"""Rebuild SynthDoG-Doc RealEval page images from the original PDFs.

  python3 render_pages.py --manifest manifest.jsonl --out images [--tier B]

Fetches each source PDF once -- from the place it was originally fetched (original URL or the CommonCrawl WARC record
at warc_file / warc_offset), falling back to the other -- checks its SHA-256 against the manifest, renders the listed
page at the recorded DPI with PyMuPDF (pip install pymupdf) and writes <page_id>.jpg.
"""
import argparse, hashlib, json, urllib.request, zlib
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (research; SynthDoG-Doc RealEval)"}


def from_url(m):
    return urllib.request.urlopen(urllib.request.Request(m["url"], headers=UA), timeout=120).read()


def from_warc(m):
    req = urllib.request.Request("https://data.commoncrawl.org/" + m["warc_file"],
                                 headers={**UA, "Range": f"bytes={m['warc_offset']}-{m['warc_offset'] + (64 << 20) - 1}"})
    rec = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(urllib.request.urlopen(req, timeout=300).read())
    _, _, rest = rec.partition(b"\\r\\n\\r\\n")             # WARC header
    http, _, body = rest.partition(b"\\r\\n\\r\\n")         # HTTP header
    if b"chunked" in http.lower() and not body.startswith(b"%PDF"):
        out, i = b"", 0
        while i < len(body):
            j = body.find(b"\\r\\n", i)
            if j < 0:
                break
            n = int(body[i:j].split(b";")[0] or b"0", 16)
            if n == 0:
                break
            out += body[j + 2:j + 2 + n]
            i = j + 2 + n + 2
        body = out
    return body[body.find(b"%PDF"):]


def get_pdf(m):
    order = [from_warc, from_url] if m.get("fetch_source") == "commoncrawl" else [from_url, from_warc]
    for f in order:
        if f is from_warc and not m.get("warc_file"):
            continue
        try:
            data = f(m)
        except Exception as e:  # noqa: BLE001
            print("  fetch failed", f.__name__, repr(e)[:120])
            continue
        if hashlib.sha256(data).hexdigest() == m["pdf_sha256"]:
            return data
        print("  sha256 mismatch via", f.__name__)
    return None


def main():
    import fitz
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="manifest.jsonl")
    ap.add_argument("--out", default="images")
    ap.add_argument("--tier", default="B", help="A, B or all")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    man = [json.loads(x) for x in open(a.manifest, encoding="utf-8") if x.strip()]
    cache, n_ok, n_fail = {}, 0, 0
    for m in man:
        if (a.tier != "all" and m["tier"] != a.tier) or (out / f"{m['page_id']}.jpg").exists():
            continue
        if m["pdf_sha256"] not in cache:
            cache[m["pdf_sha256"]] = get_pdf(m)
        data = cache[m["pdf_sha256"]]
        if data is None:
            print("FAIL", m["page_id"])
            n_fail += 1
            continue
        pg = fitz.open(stream=data, filetype="pdf")[m["page_index"]]
        z = min(220.0, 2000 * 72.0 / max(pg.rect.width, pg.rect.height)) / 72.0   # as rendered for the release
        pix = pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
        if (pix.width, pix.height) != (m["width"], m["height"]):
            print("SIZE MISMATCH", m["page_id"], (pix.width, pix.height), (m["width"], m["height"]))
        pix.save(str(out / f"{m['page_id']}.jpg"), jpg_quality=92)
        n_ok += 1
    print(f"rendered {n_ok}, failed {n_fail}")


if __name__ == "__main__":
    main()
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="/data/synthdog-doc/evalset/pages")
    ap.add_argument("--candidates", default="/data/synthdog-doc/evalset/candidates")
    ap.add_argument("--pdfs", default="/data/synthdog-doc/evalset/pdfs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--annotators", default="gemini,astra,opus")
    a = ap.parse_args()
    root, out = Path(a.pages), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    warc = {}
    for f in Path(a.candidates).glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                warc[c["id"]] = (c.get("dump"), c.get("file_path"), c.get("offset"))
    seen = collections.defaultdict(set)                  # an id can be logged twice (fetch, then re-log on merge)
    for line in (Path(a.pdfs) / "fetch_log.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r.get("status") == "ok" and r.get("source"):
            seen[r["id"]].add(r["source"])
    src = {i: "original_url" if v & {"platform_original_url", "original_url"} else "commoncrawl" for i, v in seen.items()}
    gts = {p["page_info"]["image_path"][:-4]: p for p in json.loads((root / "omnidocbench_gt.json").read_text())}
    man = []
    for m in (json.loads(x) for x in (root / "manifest.jsonl").read_text().splitlines() if x.strip()):
        if m["page_id"] not in gts:
            continue
        dump, wf, off = warc.get(m["doc_id"], (None, None, None))
        man.append({**{k: m[k] for k in ("page_id", "lang", "doc_type", "url", "domain", "pdf_sha256", "page_index",
                                         "n_pages", "dpi", "width", "height", "born_digital")},
                    "tier": tier_of(m["domain"]), "fetch_source": src.get(m["doc_id"]), "cc_dump": dump,
                    "warc_file": wf, "warc_offset": off,
                    "doc_id": m["doc_id"]})
    (out / "images").mkdir(exist_ok=True)
    for m in man:
        if m["tier"] == "A":
            shutil.copyfile(root / "images" / m["lang"] / f"{m['page_id']}.jpg", out / "images" / f"{m['page_id']}.jpg")
    (out / "omnidocbench_gt.json").write_text(json.dumps([gts[m["page_id"]] for m in man], ensure_ascii=False))
    (out / "manifest.jsonl").write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in man))
    keep = {m["page_id"] for m in man}
    agree = [json.loads(x) for x in (root / "agreement.jsonl").read_text().splitlines() if x.strip()]
    agree = [x for x in agree if x["page_id"] in keep]
    (out / "agreement.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in agree))
    for n in a.annotators.split(","):
        d = out / "annotations" / n
        d.mkdir(parents=True, exist_ok=True)
        for pid in keep:
            src = root / "raw" / n / f"{pid}.json"
            if src.exists():
                r = json.loads(src.read_text())
                (d / f"{pid}.json").write_text(json.dumps({k: r.get(k) for k in ("model", "answer", "effort_fallback")},
                                                          ensure_ascii=False))
    (out / "render_pages.py").write_text(RENDER, encoding="utf-8")
    card(man, agree, out)
    tiers = collections.Counter(m["tier"] for m in man)
    print(f"RELEASE_DONE pages={len(man)} tierA={tiers.get('A', 0)} tierB={tiers.get('B', 0)} out={out}", flush=True)


if __name__ == "__main__":
    main()

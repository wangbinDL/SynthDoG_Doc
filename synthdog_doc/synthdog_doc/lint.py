"""Automatic page lint: detect objective defects in rendered pages from the exported GT (ODB json) + meta.

Each check has a severity (3 = high: GT/text is wrong or the page is visibly broken; 2 = mid: a reader would notice;
1 = low: layout smell). A page's defect score is the sum of severities of the distinct checks it fails; a page is
"clean" when it fails no high/mid check.

  python3 -m synthdog_doc.lint --renders /data/synthdog-doc/renders/v1 --out /data/synthdog-doc/metrics/lint_v1.json
"""
import argparse
import collections
import json
import re
from pathlib import Path

from .langs import LANGS

HIGH, MID, LOW = 3, 2, 1
SEVERITY = {
    "clipped_text": HIGH, "head_overflow": HIGH, "math_error": HIGH, "font_error": HIGH, "none_literal": HIGH, "bare_latex": HIGH,
    "fiction_marker": HIGH, "placeholder": HIGH, "json_leak": HIGH,
    "emoji": MID, "english_leak": MID, "dup_label": MID, "dup_text": MID, "markdown_leak": MID,
    "img_upscale": MID, "digit_mix": MID,
    "empty_region": MID, "interior_gap": LOW, "empty_bottom": LOW, "tiny_text": LOW,
}
# pages expected to be full (chapter/article/paper ends, worksheets with ruled answer lines are not)
DENSE_ROLES = {"body", "story", "feature", "lesson", "front", "inside", "briefs", "financials", "first", "twocol"}
FURNITURE = {"header", "footer", "page_number", "abandon"}
NO_TEXT_CHECK = {"reference", "table", "equation_isolated"}

# pictographs; tick marks, ballot boxes and rating stars are legitimate in exams/magazines
_EMOJI_OK = {0x2605, 0x2606, 0x2610, 0x2611, 0x2612, 0x2713, 0x2714, 0x2715, 0x2716, 0x2717, 0x2718, 0x2022}
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF"
                   "\u2B50\u2B55\u231A\u231B\u23E9-\u23FA\uFE0F]")


def _emoji(t):
    for m in EMOJI.finditer(t):
        if ord(m.group(0)) not in _EMOJI_OK:
            return m.group(0)
    return None

FICTION = re.compile(r"\((?:fictional|fictitious|fiktif|fictif|fictive|ficticio|ficticia|fictício|fictícia|fiktiv|"
                     r"вымышлен\w*|काल्पनिक|কাল্পনিক|خيالي|خيالية|فرضی|افسانوی)\)|\bfictional\b|\bfictitious\b", re.I)
PLACEHOLDER = re.compile(r"(?i:lorem ipsum)|\bTODO\b|\bTBD\b|\bXXX\b|\?\?\?|\\n|<\/?(?:p|div|span|br|b|i)>|\{\{|\}\}|"
                         r"\[(?i:name|date|placeholder|insert|citation needed)[^\]]*\]")
JSON_LEAK = re.compile(r'\{\s*"|"\s*:\s*["\[{]|"\s*\}|\[\s*\{')
MARKDOWN = re.compile(r"\*\*\S|(?<![_\w])__[^\W_][^_]*__(?![_\w])|^#{1,4}\s|\]\(http", re.M)
LATEX_CMD = re.compile(r"\\[A-Za-z]{2,}|[_^]\{|\\[,;!{}]")
INLINE_MATH = re.compile(r"\$\$.+?\$\$|\$[^$]+\$", re.S)
URLISH = re.compile(r"\S+@\S+|https?://\S+|www\.\S+|\b10\.\d{4,}/\S+|\bdoi\S*", re.I)
EN_STOP = {"the", "and", "of", "to", "is", "that", "with", "for", "this", "are", "which", "from", "by", "be", "it",
           "have", "has", "been", "were", "their", "these", "into", "between", "its", "we", "our", "can", "will",
           "would", "should", "more", "than", "they", "there"}
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]+")
LABEL = re.compile(r"^\s*([(\[]?)([0-9A-Za-z\u0966-\u096F\u09E6-\u09EF\u0660-\u0669\u06F0-\u06F9\u0900-\u097F"
                   r"\u0980-\u09FF\u0600-\u06FFа-яА-Я]{1,3})([.)\]:])(\s*)")
OPTION_START = re.compile(r"^\s*[(\[]?[A-Da-dअकاأ১1][.)\]]")
DUP_SKIP = {"figure_footnote", "table_footnote", "page_footnote"}


def _texts(odb):
    for d in odb["layout_dets"]:
        t = d.get("text") or ""
        if t:
            yield d["category_type"], t


def _none_literal(lang):
    words = ["NaN", "undefined", "nil"] + ([] if lang == "de" else ["null"]) + ([] if lang == "id" else ["None"])
    return re.compile(r"(?<![\w-])(?:" + "|".join(words) + r")(?![\w-])")


def _poly_box(p):
    xs, ys = p[0::2], p[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def max_empty_rect(occ):
    """Largest all-False axis-aligned rectangle (in cells) of a boolean occupancy grid (histogram method)."""
    h, w = occ.shape
    heights = [0] * w
    best = (0, None)
    for i in range(h):
        row = occ[i]
        for j in range(w):
            heights[j] = heights[j] + 1 if not row[j] else 0
        stack = []
        for j in range(w + 1):
            cur = heights[j] if j < w else 0
            start = j
            while stack and stack[-1][1] >= cur:
                s0, hh = stack.pop()
                if hh * (j - s0) > best[0]:
                    best = (hh * (j - s0), (s0, i - hh + 1, j, i + 1))
                start = s0
            stack.append((start, cur))
    return best


def empty_region(odb, W, H, grid=100):
    """Fraction of the page covered by the largest block-free rectangle inside the content bounding box."""
    import numpy as np
    boxes = [_poly_box(d["poly"]) for d in odb["layout_dets"]]
    if not boxes:
        return 1.0, None
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    gx, gy = W / grid, H / grid
    occ = np.ones((grid, grid), bool)           # outside the content box counts as occupied
    cx0, cy0 = int(x0 // gx), int(y0 // gy)
    cx1, cy1 = int(np.ceil(x1 / gx)), int(np.ceil(y1 / gy))
    occ[cy0:cy1, cx0:cx1] = False
    pad = 0.6                                  # cells: inter-block gutters are not "empty regions"
    for b in boxes:
        occ[max(0, int(b[1] / gy - pad)):int(np.ceil(b[3] / gy + pad)),
            max(0, int(b[0] / gx - pad)):int(np.ceil(b[2] / gx + pad))] = True
    area, rect = max_empty_rect(occ)
    return area / (grid * grid), rect


def check_page(odb, meta):
    """Return {check: [evidence, ...]} for one page."""
    lang = meta.get("lang", "")
    L = LANGS.get(lang)
    found = collections.defaultdict(list)
    st = (meta.get("render") or {}).get("stats") or {}
    if st.get("clipped_tokens"):
        found["clipped_text"].append(f"{st['clipped_tokens']} tokens outside their column")
    if st.get("head_overflow"):
        found["head_overflow"].append(f"{st['head_overflow']} headline blocks taller than their module")
    if st.get("mathErrors"):
        found["math_error"].append(f"{st['mathErrors']} KaTeX errors")
    if (meta.get("render") or {}).get("font_errors"):
        found["font_error"].append(str(meta["render"]["font_errors"])[:120])
    if (st.get("img_upscale") or 0) > 2.2:
        found["img_upscale"].append(f"x{st['img_upscale']}")
    none_re = _none_literal(lang)
    seen = {}
    for cat, t in _texts(odb):
        if cat in ("table",):
            plain = re.sub(r"<[^>]+>", " ", t)
        else:
            plain = t
        if cat == "equation_isolated":
            continue
        m = none_re.search(plain)
        if m:
            found["none_literal"].append(f"{cat}: …{plain[max(0, m.start() - 30):m.end() + 20]}…")
        if FICTION.search(plain):
            found["fiction_marker"].append(f"{cat}: {FICTION.search(plain).group(0)}")
        m = PLACEHOLDER.search(INLINE_MATH.sub(" ", plain))
        if m:
            found["placeholder"].append(f"{cat}: {m.group(0)!r}")
        if JSON_LEAK.search(plain):
            found["json_leak"].append(f"{cat}: {plain[:60]}")
        e = _emoji(plain)
        if e:
            found["emoji"].append(f"{cat}: {e!r}")
        if cat in NO_TEXT_CHECK:
            continue
        outside = INLINE_MATH.sub(" ", plain)
        m = LATEX_CMD.search(outside)
        if m:
            found["bare_latex"].append(f"{cat}: …{outside[max(0, m.start() - 25):m.end() + 15]}…")
        if MARKDOWN.search(outside):
            found["markdown_leak"].append(f"{cat}: {MARKDOWN.search(outside).group(0)!r}")
        # English leaking into a non-English page
        if cat not in FURNITURE and lang != "en":
            ws = [w.lower() for w in LATIN_WORD.findall(URLISH.sub(" ", outside))]
            stop = sum(w in EN_STOP for w in ws)
            if len(ws) >= 6 and stop >= 3 and stop / len(ws) >= 0.22:
                found["english_leak"].append(f"{cat}: {outside[:70]}")
        # duplicated enumeration label ("1. 1.", "(a) a)")
        m1 = LABEL.match(outside)
        if m1 and (m1.group(4) or m1.group(3) in ")]:"):
            m2 = LABEL.match(outside[m1.end():])
            if m2 and m2.group(2) == m1.group(2):
                found["dup_label"].append(f"{cat}: {outside[:30]!r}")
        if cat not in FURNITURE and cat not in DUP_SKIP and len(plain) >= 40 and not OPTION_START.match(plain):
            key = re.sub(r"\s+", " ", plain.strip())
            if key in seen:
                found["dup_text"].append(f"{cat}: {key[:50]}")
            seen[key] = cat
        # digit policy: native vs ASCII digits mixed in body text
        if L and L.native_digits and cat in ("text_block", "title", "figure_caption", "table_caption"):
            body = URLISH.sub(" ", outside)
            body = re.sub(r"\S*[A-Za-z]\S*", " ", body)  # tokens with Latin letters (IDs, units, codes)
            ascii_d = len(re.findall(r"\d", body.translate({ord(c): None for c in L.native_digits})))
            native_d = sum(body.count(c) for c in L.native_digits)
            if meta.get("native_digits") and ascii_d >= 3 and re.search(r"[0-9]", body):
                found["digit_mix"].append(f"{cat}: ascii digits on a native-digit page")
            elif not meta.get("native_digits") and native_d >= 3:
                found["digit_mix"].append(f"{cat}: native digits on an ascii-digit page")
    # geometry smells
    W, H = meta.get("size") or [0, 0]
    if W and H and meta.get("degrade", {}).get("branch") in ("digital", "none", "scan", None):
        boxes = [(_poly_box(d["poly"]), d["category_type"]) for d in odb["layout_dets"]]
        body = [b for b, c in boxes if c not in FURNITURE]
        if body:
            top = min(b[1] for b in body)
            bot = max(b[3] for b in body)
            spans = sorted((b[1], b[3]) for b in body)
            gap, cur = 0.0, spans[0][1]
            for y0, y1 in spans[1:]:
                if y0 > cur:
                    gap = max(gap, y0 - cur)
                cur = max(cur, y1)
            if gap > 0.16 * H and meta.get("doc_type") not in ("ppt", "exam"):
                found["interior_gap"].append(f"{gap / H:.0%} of page height empty between blocks")
            full_roles = {"body", "story", "feature", "lesson", "exercise"}
            if meta.get("doc_type") in ("newspaper", "magazine", "paper", "book", "textbook", "report") \
                    and meta.get("page_role", "body") in full_roles and (H - bot) > 0.25 * H:
                found["empty_bottom"].append(f"bottom {(H - bot) / H:.0%} empty")
        if meta.get("doc_type") not in ("ppt", "exam") and meta.get("page_role", "body") in DENSE_ROLES:
            frac, rect = empty_region(odb, W, H)
            if frac > 0.08:
                found["empty_region"].append(f"{frac:.0%} of the page is one empty rectangle {rect}")
        dpi = (meta.get("page") or {}).get("dpi") or 150
        small = 0
        for d in odb["layout_dets"]:
            if d["category_type"] in FURNITURE:
                continue
            for ln in d.get("line_with_spans") or []:
                x0, y0, x1, y1 = _poly_box(ln["poly"])
                if (y1 - y0) / dpi * 72 < 5.2 and len(ln.get("text", "")) > 3:
                    small += 1
        if small >= 3:
            found["tiny_text"].append(f"{small} lines under ~5pt")
    return dict(found)


def score(found):
    return sum(SEVERITY[k] for k in found)


def lint_dir(renders, skip=()):
    rows = []
    for mf in sorted(Path(renders).glob("*.meta.json")):
        meta = json.loads(mf.read_text())
        jf = mf.with_name(mf.name.replace(".meta.json", ".json"))
        if not jf.exists():
            continue
        odb = json.loads(jf.read_text())
        found = {k: v for k, v in check_page(odb, meta).items() if k not in skip}
        rows.append({"name": meta["name"], "doc_type": meta.get("doc_type"), "lang": meta.get("lang"),
                     "score": score(found), "clean": not any(SEVERITY[k] >= MID for k in found),
                     "has_high": any(SEVERITY[k] == HIGH for k in found), "found": found})
    return rows


def summarize(rows):
    def agg(sub):
        n = len(sub)
        if not n:
            return {}
        cnt = collections.Counter(k for r in sub for k in r["found"])
        return {"n": n, "clean_rate": round(sum(r["clean"] for r in sub) / n, 4),
                "high_rate": round(sum(r["has_high"] for r in sub) / n, 4),
                "mean_score": round(sum(r["score"] for r in sub) / n, 3),
                "checks": {k: round(v / n, 4) for k, v in cnt.most_common()}}
    out = {"all": agg(rows), "by_type": {}, "by_lang": {}}
    for key, field in (("by_type", "doc_type"), ("by_lang", "lang")):
        for v in sorted({r[field] for r in rows}):
            out[key][v] = agg([r for r in rows if r[field] == v])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders", required=True, nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--skip", default="", help="comma-separated checks to ignore (e.g. clipped_text for renders "
                                               "made before the overflow audit was fixed)")
    a = ap.parse_args()
    report = {}
    for d in a.renders:
        rows = lint_dir(d, skip=set(filter(None, a.skip.split(","))))
        s = summarize(rows)
        ex = collections.defaultdict(list)
        for r in rows:
            for k, v in r["found"].items():
                if len(ex[k]) < a.examples:
                    ex[k].append({"name": r["name"], "evidence": v[:2]})
        report[d] = {"summary": s, "examples": ex, "pages": rows}
        al = s["all"]
        print(f"== {d}  n={al['n']} clean={al['clean_rate']:.1%} high={al['high_rate']:.1%} "
              f"score={al['mean_score']:.2f}")
        for k, v in al["checks"].items():
            print(f"   {k:15s} sev{SEVERITY[k]} {v:6.1%}   e.g. {ex[k][0]['name']}: {ex[k][0]['evidence'][0][:90]}")
        print("   by type:", ", ".join(f"{t}={x['clean_rate']:.0%}" for t, x in s["by_type"].items()))
        print("   by lang:", ", ".join(f"{t}={x['clean_rate']:.0%}" for t, x in s["by_lang"].items()))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

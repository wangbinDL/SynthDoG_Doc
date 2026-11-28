"""Per-language text pools (Wikipedia + national web) and LLM content packs, with slot-typed samplers."""
import json
import os
import random
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .textkit import clean_text, fix_punct, is_english, normalize

CORPUS_DIR = Path("/data/synthdog-doc/corpus")
# Real-document prose from the FinePDFs pool (scripts/datapool/build_prose_sample.py): the JFS copy on workers, a small
# /data copy elsewhere. Empty -> pages fall back to Wikipedia text.
POOL_DIRS = [Path(p) for p in os.environ.get(
    "SDD_POOL_DIRS", "/mnt/wangbin02-jfs/processed/synthdog_doc/datapool/v1:/data/synthdog-doc/pool_prose").split(":") if p]
CONTENT_DIR = Path("/data/synthdog-doc/content")

_SITE_SUFFIX = re.compile(r"\s*[|\-–—:»·•]\s*[^|\-–—:»·•]{2,40}$")
_BAD_LINE = re.compile(r"(https?://|www\.|@|©|cookie|javascript|\.php|\.html|\{|\}|\|{2,})", re.I)
# residue of stripped Wikipedia templates / math: "du (m. 922)", "du .", "where  is", "( )", " ,"
_WIKI_RESIDUE = re.compile(r"\(\s*\)|\(\s*[,;]|\s[,.;:](\s|$)|\S\s{2,}\S|\(\s*m\.\s*\d|\bdu \.|\[\d+\]|\{\{|\}\}|\|\s*\w+\s*=")


def _read_jsonl(p):
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
    return out


def clean_headline(t):
    t = normalize(t)
    # drop trailing "| Site name" fragments (once or twice)
    for _ in range(2):
        m = _SITE_SUFFIX.search(t)
        if m and len(t) - len(m.group(0)) >= 15:
            t = t[: m.start()]
    return t.strip(" -|–—:")


def good_para(p, min_len=60):
    if len(p) < min_len or _BAD_LINE.search(p) or _WIKI_RESIDUE.search(p):
        return False
    if p.count("(") != p.count(")"):
        return False
    # count letters incl. combining marks (Indic vowel signs / viramas are category M*, not isalpha)
    letters = sum(1 for ch in p if ch.isalpha() or unicodedata.category(ch).startswith("M"))
    return letters / max(1, len(p)) > 0.6


class Corpus:
    def __init__(self, lang):
        self.lang = lang
        self.wiki = [a for a in _read_jsonl(CORPUS_DIR / lang / "wiki.jsonl") if a.get("sections")]
        web = _read_jsonl(CORPUS_DIR / lang / "web.jsonl")
        self.news = [a for a in web if a.get("kind") == "news"]
        self.national = [a for a in web if a.get("kind") == "national"]
        for a in self.news + self.national:
            a["paras"] = [fix_punct(clean_text(normalize(p), lang), lang) for p in a.get("paras", [])
                          if good_para(p) and not is_english(p, lang)]
            a["title"] = clean_headline(a.get("title") or "")
        self.news = [a for a in self.news if a["paras"]]
        self.national = [a for a in self.national if a["paras"]]
        for a in self.wiki:
            for s in a["sections"]:
                s["paras"] = [fix_punct(clean_text(normalize(p), lang), lang) for p in s["paras"]
                              if good_para(p, 40) and not is_english(p, lang)]
            a["sections"] = [s for s in a["sections"] if s["paras"]]
        self.wiki = [a for a in self.wiki if a["sections"]]
        self.pool = []
        for d in POOL_DIRS:
            f = d / lang / "prose_sample.jsonl" if (d / lang / "prose_sample.jsonl").exists() else d / f"{lang}.jsonl"
            if f.exists():
                cap = int(os.environ.get("SDD_POOL_MAX_DOCS", "600"))   # per renderer process: bounded memory
                rows = []
                with open(f, encoding="utf-8") as fh:
                    for k, line in enumerate(fh):
                        if k >= cap:
                            break
                        try:
                            rows.append(json.loads(line))
                        except Exception:  # noqa: BLE001
                            pass
                cjk = lang in ("zh-Hans", "zh-Hant", "ja", "th")
                for a in rows:
                    n_in = sum(len(sct.get("paras", [])) for sct in a.get("sections", []))
                    for sct in a.get("sections", []):
                        sct["paras"] = [fix_punct(clean_text(normalize(x.replace("\u0640", "")), lang), lang)
                                        for x in sct.get("paras", [])
                                        if good_para(x, 40) and not is_english(x, lang) and self._prose_ok(x, cjk)]
                    a["sections"] = [sct for sct in a.get("sections", []) if sct["paras"]]
                    n_ok = sum(len(sct["paras"]) for sct in a["sections"])
                    chars = sum(len(x) for sct in a["sections"] for x in sct["paras"])
                    # keep documents that are mostly running prose (not catalogues, notices or forms)
                    if a["sections"] and n_ok >= 0.7 * n_in and chars / max(1, n_ok) >= (100 if cjk else 250):
                        a.setdefault("title", "")
                        self.pool.append(a)
                break
        if not self.news and not self.national:
            # no national-web text (fetch failed): fall back to Wikipedia articles shaped like news items
            self.national = [{"title": a["title"], "paras": [p for s in a["sections"] for p in s["paras"]][:12],
                              "kind": "wiki_fallback", "domain": "wikipedia"} for a in self.wiki]

    # -- article level
    def news_article(self, rng, min_chars=0):
        pool = self.news or self.national
        for _ in range(30):
            a = rng.choice(pool)
            if sum(len(p) for p in a["paras"]) >= min_chars and 12 <= len(a["title"]) <= 140:
                return a
        return rng.choice(pool)

    def wiki_article(self, rng, min_chars=0):
        for _ in range(30):
            a = rng.choice(self.wiki)
            if sum(len(p) for s in a["sections"] for p in s["paras"]) >= min_chars:
                return a
        if not hasattr(self, "_long"):
            self._long = sorted(self.wiki, key=lambda a: -sum(len(p) for s in a["sections"] for p in s["paras"]))
        return rng.choice(self._long[: max(1, len(self._long) // 8)])

    @staticmethod
    def _prose_ok(par, cjk):
        """Book-like prose: no extraction garbage (letter runs), no catalogue / table syntax, real sentences."""
        if re.search(r"(\w)\1{3,}", par) or "```" in par:
            return False
        if re.search(r"[\uFB50-\uFDFF\uFE70-\uFEFF]", par):   # Arabic presentation forms: broken PDF extraction
            return False
        if sum(par.count(c) for c in ">|[]{}<") > 0.01 * len(par) or par.count("(") > 4:
            return False
        ends = len(re.findall(r"[.!?।۔؟。！？]", par))
        if ends == 0:
            return False
        return len(par) / ends >= (20 if cjk else 40)

    def pool_article(self, rng, min_chars=0):
        """A real document's prose (FinePDFs pool) shaped like wiki_article(); falls back to Wikipedia."""
        if not self.pool:
            return self.wiki_article(rng, min_chars)
        for _ in range(30):
            a = rng.choice(self.pool)
            if sum(len(p) for s in a["sections"] for p in s["paras"]) >= min_chars:
                if not a.get("title"):
                    a = dict(a, title=next((s["heading"] for s in a["sections"] if s["heading"]), ""))
                return a
        return rng.choice(self.pool)

    def headlines(self, rng, n, max_len=110):
        pool = [a["title"] for a in (self.news or self.national) if 15 <= len(a["title"]) <= max_len]
        rng.shuffle(pool)
        return pool[:n]

    def paragraphs(self, rng, n_chars, source="news"):
        """Concatenate paragraphs from successive articles until n_chars reached."""
        out, total = [], 0
        while total < n_chars:
            if source == "news":
                a = self.news_article(rng)
                ps = a["paras"]
            else:
                a = self.wiki_article(rng)
                ps = [p for s in a["sections"] for p in s["paras"]]
            for p in ps:
                out.append(p)
                total += len(p)
                if total >= n_chars:
                    break
        return out

    def sentence(self, rng, min_len=30, max_len=140, source="news"):
        for _ in range(40):
            p = rng.choice(self.paragraphs(rng, 400, source))
            parts = re.split(r"(?<=[.!?।۔؟])\s+", p)
            parts = [s for s in parts if min_len <= len(s) <= max_len]
            if parts:
                return rng.choice(parts)
        return p[:max_len]


@lru_cache(maxsize=16)
def corpus(lang):
    return Corpus(lang)


# generators like the reserved ".example" TLD; real documents use the country's domains
_TLD = {"hi": "in", "bn": "com.bd", "ar": "com.sa", "ur": "com.pk", "es": "es", "fr": "fr", "pt": "com.br",
        "id": "co.id", "ru": "ru", "de": "de"}
_EXAMPLE_DOM = re.compile(r"\.example\b")
_EMAIL = re.compile(r"[^\s<>()\[\],;:\"']+@[^\s<>()\[\],;:\"']+")
_NONASCII = re.compile(r"[^\x00-\x7F]")


def _fix_contacts(s, lang):
    if ".example" in s:
        s = _EXAMPLE_DOM.sub("." + _TLD.get(lang, "com"), s)
    if "@" in s:
        # e-mail addresses in a native script (or with soft hyphens / zero-width chars) do not exist: drop them
        def fix(m):
            e = m.group(0).replace("\u00ad", "").replace("\u200b", "")
            return e if not _NONASCII.search(e) else ""
        s = _EMAIL.sub(fix, s)
        s = re.sub(r"\s*(?:—|–|-|,|<|\()\s*(?:>|\))?\s*$", "", s)
    return s


def _deep_clean(o, lang):
    if isinstance(o, str):
        return _fix_contacts(clean_text(o, lang), lang)
    if isinstance(o, list):
        return [_deep_clean(x, lang) for x in o]
    if isinstance(o, dict):
        return {k: (_deep_clean(v, lang) if not k.startswith("_") else v) for k, v in o.items()}
    return o


_HEDGE = re.compile(r"hypothetic|hipotétic|hypothétique|hypothetisch|гипотетическ|काल्पनिक|افتراضي|خيالي|فرضی|"
                    r"hipotetis|ficti|fiktiv|fictif|imaginär|imaginaire|imaginari|illustrative example|ilustrativ|"
                    r"illustratif|beispielhaft|نموذج(?:ا|ًا) إجرائي|"
                    # phase 2 languages
                    r"\billustrative\b|\bsimulated\b|for illustration|虚构|虛構|假设性|假設性|示意性|仅供示例|僅供示例|"
                    r"架空|仮想の|想定上|가상의|허구|สมมติ|hư cấu|giả định|minh họa|kurgusal|varsayımsal|temsili|"
                    r"fittizi|ipotetic|fikcyjn|hipotetyczn|fictief|illustratief|خیالی|فرضی", re.I)
_SENT_SPLIT = re.compile(r"(?<=[.!?।۔؟。！？])\s*")


def _strip_hedges(x):
    """Drop sentences that call the study / company / data hypothetical, fictional or illustrative."""
    if isinstance(x, str):
        if not _HEDGE.search(x):
            return x
        kept = [t for t in _SENT_SPLIT.split(x) if t and not _HEDGE.search(t)]
        return " ".join(kept) if kept else x
    if isinstance(x, list):
        return [_strip_hedges(v) for v in x]
    if isinstance(x, dict):
        return {k: (v if str(k).startswith("_") else _strip_hedges(v)) for k, v in x.items()}
    return x
_SCRIPT_OK = {"latin": ("latin",), "cyrillic": ("cyrillic", "latin"), "devanagari": ("devanagari", "latin"),
              "bengali": ("bengali", "latin"), "arabic": ("arabic", "latin")}


@lru_cache(maxsize=1)
def _photo_text_tags():
    from .imagepool import pool
    return {r["path"]: r for r in pool("photo") + pool("photo_gray") if "text" in r}


def _text_ok(path, lang):
    """False for photos with camera stamps / overlays, prominent text, or text in a script foreign to the page."""
    t = _photo_text_tags().get(path)
    if not t:
        return True
    from .langs import LANGS
    ok = _SCRIPT_OK.get(LANGS[lang].script, ("latin",))
    if t.get("overlay") or t.get("text") == "much":
        return False
    return t.get("text") in (None, "none") or t.get("text_script") in ok + ("none",)


# crops that come from research papers (not editorial photos) must not illustrate news / magazine stories
_RESEARCH_FIG = re.compile(r"dataset|simulat|microscop|annotated|bounding box|detection|heatmap|segmentation|x-ray|"
                           r"\bmri\b|ct scan|schematic|infographic|scale bar|measurement|electrode|comparison of|"
                           r"cartoon|facial action|landmark|illustrat|drawing|painting|comic|sketch|poster|caption|"
                           r"signboard|\btext\b|lettering|handwrit", re.I)


@lru_cache(maxsize=64)
def packs(lang, kind):
    rows = [_deep_clean(r, lang) for r in _read_jsonl(CONTENT_DIR / lang / f"{kind}.jsonl")]
    photos = {d.get("_idx"): d.get("photos") or [] for d in _read_jsonl(CONTENT_DIR / lang / f"{kind}_photos.jsonl")}
    if photos:
        for r in rows:
            ph = [p for p in photos.get(r.get("_idx"), []) if Path(p.get("path", "")).exists()
                  and not (kind in ("news", "feature", "ppt") and _RESEARCH_FIG.search(p.get("subject", "")))
                  and _text_ok(p.get("path"), lang)]
            r["_photos"] = [dict(p, caption=clean_text(p.get("caption", ""), lang)) for p in ph]
    if kind == "news":
        out = []
        for r in rows:
            if not r.get("is_news", True) or not r.get("headline") or not r.get("body"):
                continue
            r["body"] = [fix_punct(normalize(p), lang) for p in r["body"] if good_para(p, 40) and not is_english(p, lang)]
            if sum(len(p) for p in r["body"]) >= 500:
                out.append(r)
        return out
    if kind in ("paper", "report"):
        # packs whose text keeps saying the study / company is hypothetical or fictional read as generator output
        rows = [r for r in rows if len(_HEDGE.findall(json.dumps({k: v for k, v in r.items() if not k.startswith("_")},
                                                                 ensure_ascii=False))) < 2] or rows
        rows = [_strip_hedges(r) for r in rows]
        # merge second-pass consistency enrichment (pack_enrich.py) by _idx
        ext = {d.get("_idx"): d for d in _read_jsonl(CONTENT_DIR / lang / f"{kind}_x.jsonl")}
        for r in rows:
            if r.get("_idx") in ext:
                r["_x"] = _deep_clean(ext[r["_idx"]], lang)
    if kind in ("ads", "ads2"):
        flat = []
        for r in rows:
            flat += [a for a in (r.get("ads") or r.get("items") or []) if isinstance(a, dict)]
        return flat
    return rows


MONTH_KEYS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December"]
WEEKDAY_KEYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def date_text(lang, iso, style="long", with_weekday=True):
    """Localized date from an ISO timestamp (e.g. a story's crawl date), month/weekday names from the locale pack."""
    import datetime as _dt
    try:
        d = _dt.date.fromisoformat(str(iso)[:10])
    except ValueError:
        d = _dt.date(2023, 5, 17)
    month = L(lang, MONTH_KEYS[d.month - 1], grp="news")
    wd = L(lang, WEEKDAY_KEYS[d.weekday()], grp="news")
    if style == "short":
        return f"{d.day:02d}.{d.month:02d}.{d.year}"
    if lang in ("de", "ru"):
        core = f"{d.day}. {month} {d.year}" if lang == "de" else f"{d.day} {month} {d.year}"
    elif lang in ("es", "pt"):
        core = f"{d.day} de {month} de {d.year}"
    else:
        core = f"{d.day} {month} {d.year}"
    sep = "، " if lang in ("ar", "ur") else ", "
    return f"{wd}{sep}{core}" if with_weekday else core


_GRP = re.compile(r"^\[(\w+)\]\s*")


@lru_cache(maxsize=16)
def locale(lang):
    rows = packs(lang, "locale")
    loc = dict(rows[0]) if rows else {"strings": {}}
    extra = packs(lang, "locale_x")          # strings added for later template versions
    if extra:
        loc["strings"] = {**(extra[0].get("strings") or {}), **(loc.get("strings") or {})}
    norm, qual = {}, {}
    for k, v in (loc.get("strings") or {}).items():
        m = _GRP.match(k)
        grp = m.group(1) if m else ""
        base = _GRP.sub("", k).split(" (")[0].strip()
        if isinstance(v, str):
            norm.setdefault(base, v)
            qual[(grp, base)] = v
    loc["_norm"], loc["_qual"] = norm, qual
    return loc


def L(lang, key, default=None, grp=None):
    """Localized UI string (falls back to default / the English key)."""
    loc = locale(lang)
    if grp and (grp, key) in loc["_qual"]:
        return loc["_qual"][(grp, key)]
    if key in loc["_norm"]:
        return loc["_norm"][key]
    return default if default is not None else key


def names(lang, kind, rng, n=1):
    lst = locale(lang).get(kind) or []
    if not lst:
        return [kind] * n
    return [rng.choice(lst) for _ in range(n)]


def person(lang, rng):
    f = names(lang, "person_first", rng)[0]
    s = names(lang, "person_last", rng)[0]
    return f"{f} {s}"

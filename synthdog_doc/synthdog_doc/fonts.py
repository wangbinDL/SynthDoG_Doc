"""Font pools per script and typographic role, and @font-face CSS generation.

Fonts come from a sparse checkout of github.com/google/fonts (OFL/Apache/UFL); the manifest is
built by scripts/build_font_manifest.py and records cmap coverage per script.
"""
import json
import os
import random
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

FONT_ROOT = Path(os.environ.get("SDD_FONT_ROOT", "/data/synthdog-doc/fonts"))
MANIFEST = FONT_ROOT / "font_manifest.json"

# Curated role pools (family names as in the manifest). Weights bias toward faces common in print.
POOLS = {
    "latin": {
        "serif": {"Noto Serif": 3, "PT Serif": 3, "Merriweather": 2, "Lora": 2, "EB Garamond": 2,
                  "Source Serif 4": 3, "Tinos": 3, "Literata": 2, "Alegreya": 1, "Crimson Pro": 2,
                  "Libre Baskerville": 1, "Gelasio": 2, "Domine": 1, "Noticia Text": 1, "IBM Plex Serif": 1,
                  "Spectral": 1, "STIX Two Text": 2, "Old Standard TT": 1},
        "sans": {"Noto Sans": 3, "Roboto": 3, "Open Sans": 3, "PT Sans": 2, "Source Sans 3": 3, "Fira Sans": 2,
                 "IBM Plex Sans": 2, "Inter": 2, "Lato": 3, "Arimo": 3, "Rubik": 1, "Work Sans": 1, "Nunito": 1,
                 "Libre Franklin": 2, "Public Sans": 1, "Ubuntu": 1},
        "display": {"Playfair Display": 3, "Montserrat": 3, "Raleway": 2, "Oswald": 3, "Roboto Condensed": 3,
                    "Archivo Narrow": 2, "Barlow Condensed": 2, "PT Sans Narrow": 2, "Fira Sans Condensed": 2,
                    "Roboto Slab": 2, "Anton": 1, "Exo 2": 1, "Libre Franklin": 2, "Merriweather": 1,
                    "Noto Serif Display": 2, "Noto Sans Display": 2},
        "mono": {"Roboto Mono": 2, "Source Code Pro": 2, "Fira Mono": 1, "JetBrains Mono": 1, "IBM Plex Mono": 1,
                 "Cousine": 2, "PT Mono": 1},
        "hand": {"Caveat": 2, "Kalam": 2, "Patrick Hand": 2, "Comic Neue": 1, "Shadows Into Light": 1,
                 "Architects Daughter": 1, "Indie Flower": 1},
    },
    "cyrillic": {
        "serif": {"Noto Serif": 3, "PT Serif": 4, "Merriweather": 2, "Lora": 2, "EB Garamond": 2,
                  "Source Serif 4": 2, "Tinos": 3, "Literata": 2, "Alegreya": 1, "IBM Plex Serif": 1,
                  "Spectral": 1, "STIX Two Text": 2, "Old Standard TT": 2, "Cormorant Garamond": 1},
        "sans": {"Noto Sans": 3, "Roboto": 3, "Open Sans": 3, "PT Sans": 4, "Source Sans 3": 2, "Fira Sans": 2,
                 "IBM Plex Sans": 2, "Inter": 2, "Lato": 1, "Arimo": 3, "Rubik": 1, "Ubuntu": 1, "Exo 2": 1},
        "display": {"Playfair Display": 2, "Montserrat": 2, "Raleway": 2, "Oswald": 3, "Roboto Condensed": 3,
                    "PT Sans Narrow": 3, "Fira Sans Condensed": 2, "Roboto Slab": 2, "Noto Serif Display": 2,
                    "Noto Sans Display": 2, "Exo 2": 1},
        "mono": {"Roboto Mono": 2, "Source Code Pro": 2, "Fira Mono": 1, "JetBrains Mono": 1, "PT Mono": 2,
                 "Cousine": 2},
        "hand": {"Caveat": 3, "Marck Script": 1, "Neucha": 2, "Amatic SC": 1},
    },
    "devanagari": {
        "serif": {"Noto Serif Devanagari": 4, "Tiro Devanagari Hindi": 3, "Martel": 3, "Karma": 2, "Eczar": 1,
                  "Laila": 2, "Kurale": 1, "Sura": 1},
        "sans": {"Noto Sans Devanagari": 4, "Hind": 4, "Mukta": 4, "Poppins": 2, "Palanquin": 2, "Sarala": 2,
                 "Biryani": 1, "Akshar": 1, "Gotu": 1},
        "display": {"Rozha One": 2, "Yatra One": 1, "Teko": 2, "Khand": 2, "Rajdhani": 2, "Baloo 2": 2,
                    "Pragati Narrow": 2, "Martel": 2, "Noto Serif Devanagari": 2, "Eczar": 2},
        "mono": {},
        "hand": {"Kalam": 3, "Amita": 1},
    },
    "bengali": {
        "serif": {"Noto Serif Bengali": 4, "Tiro Bangla": 4},
        "sans": {"Noto Sans Bengali": 4, "Hind Siliguri": 4, "Anek Bangla": 3, "Mina": 1},
        "display": {"Galada": 2, "Atma": 1, "Baloo Da 2": 2, "Anek Bangla": 2, "Noto Serif Bengali": 2,
                    "Tiro Bangla": 1, "Hind Siliguri": 2},
        "mono": {},
        "hand": {"Atma": 1},
    },
    "arabic": {
        "serif": {"Amiri": 4, "Noto Naskh Arabic": 4, "Scheherazade New": 3, "Markazi Text": 2, "Lateef": 1,
                  "Mirza": 1},
        "sans": {"Noto Sans Arabic": 4, "Cairo": 3, "Tajawal": 3, "Almarai": 2, "IBM Plex Sans Arabic": 3,
                 "Readex Pro": 2, "Changa": 1, "Mada": 2, "Harmattan": 1, "Vazirmatn": 2, "Rubik": 1},
        "display": {"Noto Kufi Arabic": 3, "Reem Kufi": 2, "Lalezar": 2, "Rakkas": 1, "Baloo Bhaijaan 2": 1,
                    "El Messiri": 2, "Aref Ruqaa": 1, "Cairo": 2, "Changa": 2},
        "mono": {},
        "hand": {"Aref Ruqaa": 1},
    },
    "urdu": {
        # Nastaliq dominates Urdu print; Naskh appears in headings, web text and some textbooks.
        "nastaliq": {"Noto Nastaliq Urdu": 5, "Gulzar": 3},
        "serif": {"Noto Naskh Arabic": 3, "Amiri": 2, "Scheherazade New": 2, "Lateef": 2, "Mirza": 1},
        "sans": {"Noto Sans Arabic": 3, "Vazirmatn": 2, "IBM Plex Sans Arabic": 1, "Mada": 1},
        "display": {"Noto Kufi Arabic": 2, "Lalezar": 1, "Reem Kufi": 1, "Gulzar": 2, "Noto Nastaliq Urdu": 2},
        "mono": {},
        "hand": {},
    },
}

POOLS.update({
    # ---- phase 2. Han-unified scripts get language-specific faces (SC / TC-HK / JP / KR glyph standards).
    "hans": {
        "serif": {"Noto Serif SC": 5},
        "sans": {"Noto Sans SC": 5},
        "display": {"Noto Serif SC": 3, "Noto Sans SC": 3, "ZCOOL QingKe HuangYou": 2, "站酷小薇体": 2,
                    "ZCOOL KuaiLe": 1, "Ma Shan Zheng": 1},
        "kai": {"LXGW WenKai TC": 3},
        "mono": {},
        "hand": {"Long Cang": 2, "Zhi Mang Xing": 1, "Liu Jian Mao Cao": 1, "Ma Shan Zheng": 1},
    },
    "hant": {
        "serif": {"Noto Serif TC": 4, "Noto Serif HK": 2, "Cactus Classical Serif": 2, "Chiron Sung HK": 2},
        "sans": {"Noto Sans TC": 4, "Noto Sans HK": 2, "Chiron Hei HK": 3},
        "display": {"Noto Serif TC": 2, "Noto Sans TC": 2, "Chiron Hei HK": 2, "Chiron Sung HK": 1, "Iansui": 1},
        "kai": {"LXGW WenKai TC": 3},
        "mono": {},
        "hand": {"Iansui": 2, "LXGW WenKai TC": 1},
    },
    "japanese": {
        "serif": {"Noto Serif JP": 4, "Shippori Mincho": 3, "Zen Old Mincho": 2, "BIZ UDPMincho": 3,
                  "Sawarabi Mincho": 2, "Hina Mincho": 1, "Kaisei Opti": 1},
        "sans": {"Noto Sans JP": 4, "BIZ UDPGothic": 3, "Zen Kaku Gothic New": 3, "M PLUS 1p": 2,
                 "Sawarabi Gothic": 2, "Murecho": 1},
        "display": {"Zen Maru Gothic": 2, "Rounded Mplus 1c": 2, "Kiwi Maru": 1, "DotGothic16": 1,
                    "Shippori Mincho": 2, "Noto Serif JP": 2, "Noto Sans JP": 2},
        "mono": {},
        "hand": {"Yuji Syuku": 1, "Kiwi Maru": 1},
    },
    "hangul": {
        "serif": {"Noto Serif KR": 4, "NanumMyeongjo": 4, "Gowun Batang": 3, "Song Myung": 2, "Hahmlet": 2},
        "sans": {"Noto Sans KR": 4, "NanumGothic": 4, "IBM Plex Sans KR": 3, "Gowun Dodum": 2, "Orbit": 1,
                 "Sunflower": 1},
        "display": {"Black Han Sans": 2, "Do Hyeon": 2, "Jua": 1, "Noto Sans KR": 2, "NanumMyeongjo": 1},
        "mono": {},
        "hand": {"Nanum Pen": 2},
    },
    "thai": {
        # looped faces are the print / government norm (Sarabun is the official government font)
        "serif": {"Sarabun": 4, "Noto Serif Thai": 3, "Taviraj": 2, "Trirong": 2, "Pridi": 2, "Maitree": 2,
                  "Noto Sans Thai Looped": 2, "IBM Plex Sans Thai Looped": 2},
        "sans": {"Noto Sans Thai": 4, "Prompt": 3, "Kanit": 3, "Anuphan": 2, "IBM Plex Sans Thai": 3, "Athiti": 1,
                 "Mitr": 2, "Niramit": 2},
        "display": {"Kanit": 3, "Prompt": 2, "Mitr": 2, "Chakra Petch": 2, "Taviraj": 1},
        "mono": {},
        "hand": {"Niramit": 1},
    },
    "persian": {
        "serif": {"Noto Naskh Arabic": 4, "Amiri": 2, "Scheherazade New": 2, "Markazi Text": 2, "Lateef": 1,
                  "Mirza": 1},
        "sans": {"Vazirmatn": 5, "Noto Sans Arabic": 3, "IBM Plex Sans Arabic": 2, "Cairo": 1, "Mada": 1,
                 "Harmattan": 1},
        "display": {"Lalezar": 3, "Noto Kufi Arabic": 2, "Reem Kufi": 1, "El Messiri": 1, "Changa": 1,
                    "Vazirmatn": 2},
        "mono": {},
        "hand": {"Aref Ruqaa": 1},
    },
})
POOLS["latin"]["sans"]["Be Vietnam Pro"] = 1

# Fallback face per script (rare characters missing from a display face must not fall back to system fonts).
SCRIPT_FALLBACK = {"hans": "Noto Sans SC", "hant": "Noto Sans TC", "japanese": "Noto Sans JP",
                   "hangul": "Noto Sans KR", "thai": "Noto Sans Thai", "persian": "Noto Naskh Arabic",
                   "arabic": "Noto Naskh Arabic", "urdu": "Noto Naskh Arabic", "devanagari": "Noto Sans Devanagari",
                   "bengali": "Noto Sans Bengali"}
# Latin-script languages whose letters many Latin faces lack: filter pools by manifest coverage.
COVERAGE_NEED = {"vi": "vietnamese", "tr": "turkish", "pl": "polish"}

LATIN_COMPANION = {  # Latin face to pair with non-Latin scripts for embedded Latin text / digits
    "serif": ["Noto Serif", "Tinos", "PT Serif", "Source Serif 4"],
    "sans": ["Noto Sans", "Roboto", "Open Sans", "Arimo"],
    "display": ["Noto Sans Display", "Roboto Condensed", "Oswald"],
    "mono": ["Roboto Mono", "Cousine"],
    "hand": ["Caveat", "Kalam"],
}

SCRIPT_OF_LANG = {"hi": "devanagari", "bn": "bengali", "ar": "arabic", "ur": "urdu", "ru": "cyrillic",
                  "es": "latin", "fr": "latin", "pt": "latin", "id": "latin", "de": "latin",
                  "en": "latin", "it": "latin", "pl": "latin", "nl": "latin", "tr": "latin", "vi": "latin",
                  "zh-Hans": "hans", "zh-Hant": "hant", "ja": "japanese", "ko": "hangul", "th": "thai",
                  "fa": "persian"}


@lru_cache(maxsize=1)
def manifest():
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))
    fam = defaultdict(list)
    for r in rows:
        fam[r["family"]].append(r)
    return fam


def family_faces(family):
    """Return list of face dicts for a family (variable or static)."""
    return manifest().get(family, [])


def has_family(family):
    return family in manifest()


def covers(family, need):
    return not need or any(f["coverage"].get(need, 0) >= 0.98 for f in family_faces(family))


def pick(rng, script, role, need=None):
    pool = POOLS[script].get(role) or POOLS[script].get("sans") or {}
    pool = {k: v for k, v in pool.items() if has_family(k) and covers(k, need)}
    if not pool and need:
        pool = {k: 1 for k in ("Noto Serif", "Noto Sans") if has_family(k) and covers(k, need)}
    if not pool:
        raise KeyError(f"no fonts for {script}/{role}")
    names, weights = zip(*pool.items())
    return rng.choices(names, weights=weights, k=1)[0]


def face_css(family, alias=None):
    """@font-face rules for a family; alias lets two roles use the same family independently."""
    name = alias or family
    rules = []
    for f in family_faces(family):
        path = f["path"]
        style = "italic" if f["italic"] else "normal"
        if "wght" in f["axes"]:
            lo, hi = f["axes"]["wght"]
            weight = f"{int(lo)} {int(hi)}"
        else:
            weight = str(f["weight"])
        stretch = ""
        if "wdth" in f["axes"]:
            lo, hi = f["axes"]["wdth"]
            stretch = f"font-stretch: {lo:g}% {hi:g}%;"
        rules.append(f"@font-face{{font-family:'{name}';src:url('file://{path}');font-style:{style};"
                     f"font-weight:{weight};{stretch}font-display:block;}}")
    return "\n".join(rules)


def has_italic(family):
    return any(f["italic"] for f in family_faces(family))


def weights_available(family):
    ws = set()
    for f in family_faces(family):
        if "wght" in f["axes"]:
            lo, hi = f["axes"]["wght"]
            ws.update(w for w in range(100, 1000, 100) if lo <= w <= hi)
        else:
            ws.add(f["weight"])
    return sorted(ws)


def bold_weight(family):
    ws = weights_available(family)
    for w in (700, 600, 800, 500):
        if w in ws:
            return w
    return max(ws) if ws else 700


class FontSet:
    """A document-level font selection: role -> (family, css stack)."""

    def __init__(self, rng, lang, prefer=None):
        self.lang = lang
        self.script = SCRIPT_OF_LANG[lang]
        self.need = COVERAGE_NEED.get(lang)
        self.fams = {}
        prefer = prefer or {}
        for role in ("serif", "sans", "display", "mono", "hand", "nastaliq", "kai"):
            if role not in POOLS[self.script] or not POOLS[self.script][role]:
                continue
            self.fams[role] = prefer.get(role) or pick(rng, self.script, role, self.need)
        self.latin = {r: rng.choice([f for f in LATIN_COMPANION[r] if has_family(f)]) for r in LATIN_COMPANION}
        self.fallback = SCRIPT_FALLBACK.get(self.script)

    def stack(self, role):
        fam = self.fams.get(role) or self.fams.get("sans") or self.fams.get("serif")
        lat_role = role if role in self.latin else ("serif" if role in ("nastaliq",) else "sans")
        parts = [f"'{fam}'"]
        if self.script != "latin" and self.script != "cyrillic":
            parts.append(f"'{self.latin[lat_role]}'")
        if self.fallback and self.fallback != fam:
            parts.append(f"'{self.fallback}'")
        parts.append("'Noto Sans'")
        parts.append("sans-serif")
        return ", ".join(parts)

    def css(self):
        fams = set(self.fams.values()) | set(self.latin.values()) | {"Noto Sans"} | ({self.fallback} - {None})
        return "\n".join(face_css(f) for f in sorted(fams) if has_family(f))

    def describe(self):
        return {"script": self.script, **self.fams, "latin_companion": self.latin}

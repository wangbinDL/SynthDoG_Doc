"""Document-level base: page geometry, font set, script typography, digit policy and helpers."""
import random

from . import corpus as C
from .fonts import FontSet, bold_weight, has_italic
from .geometry import IN, PT, sample_page
from .langs import LANGS
from .render import PageSpec
from . import textkit
from .textkit import fmt_num, to_native_digits

# Script typography rules (multipliers relative to Latin settings).
TYPO = {
    "latin": dict(lh=1.0, size=1.0, ls_ok=True, italic=True, hyph=True, justify=0.85, caps=True),
    "cyrillic": dict(lh=1.0, size=1.0, ls_ok=True, italic=True, hyph=True, justify=0.9, caps=True),
    "devanagari": dict(lh=1.32, size=1.1, ls_ok=False, italic=False, hyph=False, justify=0.55, caps=False),
    "bengali": dict(lh=1.32, size=1.1, ls_ok=False, italic=False, hyph=False, justify=0.55, caps=False),
    "arabic": dict(lh=1.38, size=1.12, ls_ok=False, italic=False, hyph=False, justify=0.75, caps=False),
    "nastaliq": dict(lh=1.78, size=1.16, ls_ok=False, italic=False, hyph=False, justify=0.35, caps=False),
    # phase 2
    "persian": dict(lh=1.38, size=1.12, ls_ok=False, italic=False, hyph=False, justify=0.8, caps=False),
    "hans": dict(lh=1.28, size=0.96, ls_ok=False, italic=False, hyph=False, justify=0.97, caps=False),
    "hant": dict(lh=1.3, size=0.96, ls_ok=False, italic=False, hyph=False, justify=0.97, caps=False),
    "japanese": dict(lh=1.3, size=0.96, ls_ok=False, italic=False, hyph=False, justify=0.97, caps=False),
    "hangul": dict(lh=1.24, size=0.98, ls_ok=False, italic=False, hyph=False, justify=0.85, caps=False),
    "thai": dict(lh=1.42, size=1.12, ls_ok=False, italic=False, hyph=False, justify=0.45, caps=False),
}
# Latin-script languages with stacked diacritics need a little more leading.
LH_LANG = {"vi": 1.1}

# Probability that a document of this type uses native digits (where the script has them).
NATIVE_DIGIT_P = {
    "bn": {"default": 0.85, "paper": 0.45, "report": 0.5, "ppt": 0.6},
    "hi": {"default": 0.25, "paper": 0.08, "report": 0.08, "ppt": 0.12, "exam": 0.3, "textbook": 0.35},
    "ar": {"default": 0.5, "paper": 0.35, "report": 0.4, "ppt": 0.45},
    "ur": {"default": 0.4, "paper": 0.25, "report": 0.25, "newspaper": 0.55, "exam": 0.45},
}


class Doc:
    def __init__(self, doc_type, lang, rng: random.Random, version=0, page=None):
        self.doc_type = doc_type
        self.lang = lang
        self.L = LANGS[lang]
        self.rng = rng
        self.version = version
        self.rtl = self.L.rtl
        self.page = page or sample_page(rng, doc_type.replace("paper_single", "paper_single"))
        self.fonts = FontSet(rng, lang)
        script = self.fonts.script
        self.nastaliq = script == "urdu" and rng.random() < 0.75
        self.typo = TYPO["nastaliq"] if self.nastaliq else TYPO["arabic" if script == "urdu" else script]
        p = NATIVE_DIGIT_P.get(lang, {})
        base_type = doc_type.split("_")[0]
        self.native_digits = rng.random() < p.get(base_type, p.get("default", 0.0))
        # document-wide digit policy (applies to every text token; LaTeX keeps Latin digits)
        script_name = "arabic" if script == "urdu" else script
        textkit.DOC.update(lang=lang, script=script_name,
                           digits=("native" if self.native_digits else "latin") if self.L.native_digits else None)
        self.W = self.page["w_in"] * IN
        self.H = self.page["h_in"] * IN
        self.meta = {"doc_type": doc_type, "lang": lang, "page": self.page, "fonts": self.fonts.describe(),
                     "nastaliq": self.nastaliq, "native_digits": self.native_digits, "version": version}

    # ---- text helpers
    def img_cap(self, d, up=1.8):
        """Largest CSS width (px) at which image record d is upscaled at most `up` x at the page DPI."""
        w = (d or {}).get("w") or 0
        return w * 96.0 / self.page["dpi"] * up if w else 1e9

    def t(self, key, default=None):
        return C.L(self.lang, key, default)

    def num(self, s):
        s = str(s)
        return to_native_digits(s, self.lang) if self.native_digits else s

    def fnum(self, x, decimals=None, pct=False):
        """Locale-formatted number (decimal/thousand separators); digits follow the document policy."""
        return fmt_num(x, self.lang, decimals, pct)

    def iso(self, s):
        """Bidi-isolated LTR run for numeric folios like '7 / 16' inside RTL pages."""
        return f"\u2066{s}\u2069" if self.rtl else s

    def upper(self, s):
        if not self.typo["caps"]:
            return s
        if self.lang == "tr":                 # Turkish dotted / dotless i: i -> İ, ı -> I (str.upper gets this wrong)
            s = s.replace("i", "İ").replace("ı", "I")
        return s.upper()

    def body_font(self, role="serif"):
        if self.nastaliq and role in ("serif", "sans"):
            return self.fonts.stack("nastaliq")
        return self.fonts.stack(role)

    def italic(self, family_role="serif"):
        fam = self.fonts.fams.get(family_role)
        return "italic" if (self.typo["italic"] and fam and has_italic(fam)) else "normal"

    def bw(self, role="serif"):
        fam = self.fonts.fams.get("nastaliq" if self.nastaliq else role) or self.fonts.fams.get(role)
        return bold_weight(fam) if fam else 700

    def pt(self, size_pt):
        """Script-compensated font size in CSS px."""
        return size_pt * PT * self.typo["size"]

    def lh(self, base):
        return round(base * self.typo["lh"] * LH_LANG.get(self.lang, 1.0), 3)

    def ls(self, em):
        return f"{em}em" if self.typo["ls_ok"] else "0"

    def justify(self):
        return "justify" if self.rng.random() < self.typo["justify"] else "start"

    def hyph(self):
        return self.typo["hyph"] and bool(self.L.pyphen_lang)

    def warm_specs(self):
        specs = []
        sample = {"latin": "Aa Ññ Éé ß ăơư ğış ąłż 0123", "cyrillic": "Аа Бб Жж 0123", "devanagari": "कखग क्ष १२३ Aa",
                  "bengali": "কখগ ক্ষ ১২৩ Aa", "arabic": "ابت ٹ ۔ ١٢٣ Aa", "urdu": "ابت ٹ ۔ ۱۲۳ Aa",
                  "persian": "پچژگکی ۱۲۳ Aa", "hans": "汉字简体，。中文 Aa1", "hant": "漢字繁體，。「」 Aa1",
                  "japanese": "日本語かなカナ。「」 Aa1", "hangul": "한국어 가나다 Aa1",
                  "thai": "ภาษาไทย กขค ๑๒๓ Aa"}[self.fonts.script]
        if self.fonts.fallback:
            specs.append([f"normal 400 16px '{self.fonts.fallback}'", sample])
        for role, fam in list(self.fonts.fams.items()) + [(r, f) for r, f in self.fonts.latin.items()]:
            for wt in (400, 700):
                for st in ("normal", "italic"):
                    specs.append([f"{st} {wt} 16px '{fam}'", sample])
        return specs

    def spec(self, body, css, page_style=""):
        meta = dict(self.meta)
        return PageSpec(doc_type=self.doc_type, lang=self.lang, width_in=self.page["w_in"],
                        height_in=self.page["h_in"], dpi=self.page["dpi"], body=body, css=css,
                        font_css=self.fonts.css(), font_warm=self.warm_specs(), rtl=self.rtl,
                        page_style=page_style, meta=meta)

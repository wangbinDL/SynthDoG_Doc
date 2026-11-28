"""Text utilities: HTML escaping, word-span tokenisation, hyphenation, digits and punctuation."""
import html
import re
import unicodedata
from functools import lru_cache

from .langs import LANGS

SHY = "­"
NNBSP = " "
NBSP = " "

_WORD_RE = re.compile(r"\S+\s*")
_LATEX_INLINE = re.compile(r"(\$[^$]+\$)")
# variable-like tokens written in plain text by LLMs: Y_i, x_{ik}, \bar{X}_{post}, a^2, P(y=1|x)
_MATHY = re.compile(r"^((?:\\[A-Za-z]+(?:\{[^}]*\})*|[A-Za-zα-ωΑ-Ω][A-Za-z0-9α-ωΑ-Ω]{0,3})"
                    r"(?:[_^](?:\{[^}]*\}|[A-Za-z0-9α-ω+\-*]+))+(?:\([^()\s]*\))?|"
                    r"[A-Za-z]\([^()\s]*[=|][^()\s]*\)|\\[A-Za-z]+(?:\{[^}]*\})+(?:[_^](?:\{[^}]*\}|\w))*)"
                    r"([.,;:)]*)$")

# Unicode subscript letters/digits written by LLMs ("Yᵢⱼ", "εᵢⱼ", "x₁") -> LaTeX subscripts
_UNI_SUB = dict(zip("₀₁₂₃₄₅₆₇₈₉ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼᵣᵤᵥᵦᵧᵨᵩᵪ₊₋", "0123456789aeoxhklmnpstijruvβγρφχ+-"))
_UNI_SUB_RE = re.compile("([" + "".join(_UNI_SUB) + "]+)")


def _uni_sub_to_latex(word):
    m = re.match(r"^(\W*)(.*?)(\W*)$", word)
    pre, core, post = m.group(1), m.group(2), m.group(3)
    if not _UNI_SUB_RE.search(core):
        return None
    core = _UNI_SUB_RE.sub(lambda g: "_{" + "".join(_UNI_SUB[c] for c in g.group(1)) + "}", core)
    return pre, core, post


_ACC_CMD = {"\u0302": "hat", "\u0304": "bar", "\u0303": "tilde", "\u0307": "dot", "\u20d7": "vec"}
_COMB_ACC = re.compile(r"([A-Za-zα-ωΑ-Ω])([\u0302\u0304\u0303\u0307\u20d7])")
_GLUED_AR = re.compile(r"^([\u0600-\u06FF\u0750-\u077F]{1,2})((?:\\[A-Za-z]+|[A-Za-z]).*)$")
_GREEK_BARE = re.compile(r"^(?:alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|iota|kappa|lambda|mu|"
                         r"nu|xi|pi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|"
                         r"Sigma|Phi|Psi|Omega)(?=[_^])")

# Document-level digit policy, set by Doc for the page being built: "native" | "latin" | None (leave as is).
DOC = {"digits": None, "lang": None}
_NATIVE_SETS = ["०१२३४५६७८९", "০১২৩৪৫৬৭৮৯", "٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹", "๐๑๒๓๔๕๖๗๘๙"]
_TO_LATIN = {ch: str(i) for ds in _NATIVE_SETS for i, ch in enumerate(ds)}
SCRIPT_RANGES = {
    "latin": [(0x0041, 0x024F), (0x1E00, 0x1EFF), (0xFF21, 0xFF5A)],
    "greek": [(0x0370, 0x03FF)],
    "cyrillic": [(0x0400, 0x04FF)],
    "devanagari": [(0x0900, 0x097F), (0xA8E0, 0xA8FF)],
    "bengali": [(0x0980, 0x09FF)],
    "arabic": [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "han": [(0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0xF900, 0xFAFF), (0x3005, 0x3007), (0x20000, 0x2EBEF),
            (0x2F800, 0x2FA1F)],
    "kana": [(0x3040, 0x309F), (0x30A0, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9F)],
    "hangul": [(0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xD7B0, 0xD7FF)],
    "thai": [(0x0E00, 0x0E7F)],
    "hebrew": [(0x0590, 0x05FF), (0xFB1D, 0xFB4F)],
}
_ALLOWED = {"latin": ("latin", "greek"), "cyrillic": ("cyrillic", "latin", "greek"),
            "devanagari": ("devanagari", "latin", "greek"), "bengali": ("bengali", "latin", "greek"),
            "arabic": ("arabic", "latin", "greek"), "persian": ("arabic", "latin", "greek"),
            "hans": ("han", "latin", "greek"), "hant": ("han", "latin", "greek"),
            "japanese": ("han", "kana", "latin", "greek"), "hangul": ("hangul", "han", "latin", "greek"),
            "thai": ("thai", "latin", "greek"), "vietnamese": ("latin", "greek"), "hebrew": ("hebrew", "latin", "greek")}


def _script_of_char(c):
    o = ord(c)
    for name, rngs in SCRIPT_RANGES.items():
        for a, b in rngs:
            if a <= o <= b:
                return name
    return None


def foreign_token(tok, lang_script):
    """True if the token contains letters of a script that should not occur in this language's documents."""
    allowed = _ALLOWED.get(lang_script, ("latin",))
    for c in tok:
        if c.isalpha():
            sc = _script_of_char(c)
            if sc is None or sc not in allowed:
                return True
    return False


_LATIN_LETTER = re.compile(r"[A-Za-z]")


def apply_digits(s):
    mode, lang = DOC.get("digits"), DOC.get("lang")
    if mode == "native" and _LATIN_LETTER.search(s):
        return s  # identifiers / codes / DOIs / units keep Latin digits
    if mode == "native" and lang:
        return to_native_digits("".join(_TO_LATIN.get(c, c) for c in s), lang)
    if mode == "latin":
        return "".join(_TO_LATIN.get(c, c) for c in s)
    return s


_SP_SUP = re.compile(r"(\\[,;:!>]|\\ |\\quad|\\qquad)\s*([\^_])")
_TEXTCMD = re.compile(r"(\\text|\\textrm|\\mbox)\{([^{}]*)\}")


def sanitize_latex(tex):
    """Repair LaTeX that KaTeX rejects but LLMs write often (validated over all content packs)."""
    t = str(tex).strip()
    t = re.sub(r"(\\?[A-Za-z]+)_\{(hat|bar|tilde|dot|vec)\}", r"\\\2{\1}", t)
    for _ in range(3):
        t2 = re.sub(r"_\{([^{}]*)\}_(\{([^{}]*)\}|([A-Za-z0-9]))", lambda m: "_{" + m.group(1) + "," + (m.group(3) or m.group(4)) + "}", t)
        if t2 == t:
            break
        t = t2
    # fill-in blanks inside math ("Y = ________") -> an underlined gap
    t = re.sub(r"(?<!\\)_{3,}", r"\\underline{\\hspace{3em}}", t)
    # sup/subscript right after a spacing command: 25\,^{\circ}C -> 25\,{}^{\circ}C
    t = _SP_SUP.sub(lambda m: m.group(1) + "{}" + m.group(2), t)

    def fix_text(m):
        body = m.group(2)
        if "\\" in body or "·" in body or "^" in body:   # math inside text mode -> upright math
            return "\\mathrm{" + body.replace("·", "\\cdot ").replace(" ", "\\ ") + "}"
        return m.group(1) + "{" + re.sub(r"(?<!\\)_", r"\\_", body) + "}"
    t = _TEXTCMD.sub(fix_text, t)
    t = _SP_SUP.sub(lambda m: m.group(1) + "{}" + m.group(2), t)
    # balance braces (LLM output sometimes truncates the closing brace)
    depth = low = 0
    for i, ch in enumerate(t):
        if ch == "{" and (i == 0 or t[i - 1] != "\\"):
            depth += 1
        elif ch == "}" and (i == 0 or t[i - 1] != "\\"):
            depth -= 1
            low = min(low, depth)
    if low < 0:
        t = "{" * (-low) + t
        depth -= low
    if depth > 0:
        t += "}" * depth
    return t


def is_blank_math(tex):
    """$_____$ written by LLMs for fill-in blanks: not math."""
    return bool(re.fullmatch(r"[\s_]*_{3,}[\s_]*|\\text\{_+\}|\\underline\{\\hspace\{[^}]*\}\}", str(tex).strip()))


def fix_math_delims(text):
    text = re.sub(r"\\\((.+?)\\\)", lambda m: "$" + m.group(1).strip() + "$", text)
    text = re.sub(r"\\\[(.+?)\\\]", lambda m: "$" + m.group(1).strip() + "$", text)
    return text.replace("$$", "$")


def esc(s):
    return html.escape(str(s), quote=True)


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\uFE0F\u200D\u2764]")
_FICT = re.compile(r"\s*[\(\[]\s*(fikti\w*|ficti\w*|fictif\w*|fictício|ficticio|fictional|вымышлен\w*|условн\w*|"
                   r"काल्पनिक|কাল্পনিক|خيالي\w*|فرضی|خیالی|placeholder)\s*[\)\]]", re.I)
_FICT_WORD = re.compile(r"\b(Fiktive?|fiktive?|Fictive|fictive|Ficticia|ficticia|Fictícia|fictícia)\s+", re.U)
_NOSPACE = re.compile(r"(?<=[a-zäöüßàâçéèêëîïôûùüÿñæœáíóúãõа-яё])([.!?;:])(?=[A-ZÄÖÜÀÂÇÉÈÊËÎÏÔÛÙÜŸÑÆŒÁÍÓÚÃÕА-ЯЁ][a-zäöüßàâçéèêëîïôûùüÿñæœáíóúãõа-яё])")
_EN_STOP = set("the and of to in is was for on with as by that at from are were this be have has it an which their".split())
_OWN_STOP = {"de": set("der die das und ist nicht mit von zu den des ein eine sich auf für dem".split()),
             "fr": set("le la les et est des une pour dans que qui sur pas du au avec par".split()),
             "es": set("el la los las y es de que en un una por con para del se no".split()),
             "pt": set("o a os as e é de que em um uma para com do da não se por".split()),
             "id": set("yang dan di ini itu dengan untuk dari tidak ke pada dalam akan adalah".split()),
             "it": set("il la di e che per un una non con del della sono gli le si come".split()),
             "pl": set("i w na nie z do to jest się że jak o po przez od".split()),
             "nl": set("de het een en van in is dat op te met voor niet zijn die".split()),
             "tr": set("ve bir bu da de için ile olarak çok daha gibi olan ama ne var".split()),
             "vi": set("và của là có trong các được cho với những không một này người đã".split())}


def strip_emoji(s):
    return _EMOJI.sub("", s)


_TEX_N = r"(?:u|eq|e|eg|abla|ot|i|mid|atural|earrow|warrow|ewline|oindent|olimits|leq|geq|subseteq|supseteq|parallel|exists|cong|sim|vdash|Rightarrow|Leftarrow|rightarrow|leftarrow|less|gtr|prec|succ)"
_TEX_T = r"(?:heta|au|imes|ext\w*|an|anh|o|op|riangle\w*|ilde|frac|t|extstyle|herefore|op)"
_LIT_ESC = re.compile(r"\\n(?!" + _TEX_N + r"(?![A-Za-z]))|\\t(?!" + _TEX_T + r"(?![A-Za-z]))")


def _fix_literal_escapes(s):
    if "\\" not in s:
        return s
    parts = re.split(r"(\$[^$]*\$)", s)       # inside $...$ everything is LaTeX
    return "".join(p if p.startswith("$") and p.endswith("$") and len(p) > 1 else _LIT_ESC.sub(" ", p)
                   for p in parts)


# "alarme.L'installation" -> "alarme. L'installation" ; "télésurveillanceLa" (6+ lowercase letters glued to a
# capitalised word) -> "télésurveillance La" (brand names like YouTube / PowerPoint have shorter lowercase runs)
_NOSPACE2 = re.compile(r"(?<=[a-zàâçéèêëîïôûùüÿñæœáíóúãõäöüß])([.!?])(?=[A-ZÀÂÇÉÈÊËÎÏÔÛÙÜÑÁÍÓÚÃÕÄÖÜ]['’a-zàâçéèêëîïôûùüÿñæœáíóúãõäöüß])")
_CAMELJOIN = re.compile(r"(\b[a-zàâçéèêëîïôûùüÿñæœáíóúãõäöüß]*[a-zàâçéèêëîïôûùüÿñæœáíóúãõäöüß]{6})"
                        r"([A-ZÀÂÇÉÈÊËÎÏÔÛÙÜÑÁÍÓÚÃÕÄÖÜ][a-zàâçéèêëîïôûùüÿñæœáíóúãõäöüß]+)")


def clean_text(s, lang=None):
    """Remove generator artefacts: emoji, '(fictional)' markers, literal \\n, missing space after a sentence end."""
    s = str(s)
    # literal "\n"/"\t" written by generators -- but never touch LaTeX (\nu, \neq, \text, \times, \theta, ...)
    s = _fix_literal_escapes(s)
    s = strip_emoji(s)
    s = _FICT.sub("", s)
    s = _FICT_WORD.sub("", s)
    s = _NOSPACE.sub(r"\1 ", s)
    s = _NOSPACE2.sub(r"\1 ", s)
    s = _CAMELJOIN.sub(r"\1 \2", s)
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def is_english(p, lang):
    """True if a paragraph in a Latin-script non-English document is actually English."""
    if lang not in _OWN_STOP:
        return False
    toks = re.findall(r"[a-zA-Z]+", p.lower())
    if len(toks) < 6:
        return False
    en = sum(t in _EN_STOP for t in toks) / len(toks)
    own = sum(t in _OWN_STOP[lang] for t in toks) / len(toks)
    return en > 0.10 and en > 2 * own


@lru_cache(maxsize=16)
def _pyphen(lang):
    import pyphen
    code = LANGS[lang].pyphen_lang
    if not code:
        return None
    try:
        return pyphen.Pyphen(lang=code, left=2, right=3)
    except KeyError:
        return None


def hyphenate_word(word, lang):
    """Insert soft hyphens into a word (letters only part); keeps punctuation untouched."""
    dic = _pyphen(lang)
    if dic is None or len(word) < 7:
        return word
    m = re.match(r"^(\W*)([\w\-]+?)(\W*)$", word, flags=re.UNICODE)
    if not m:
        return word
    pre, core, post = m.groups()
    if any(ch.isdigit() for ch in core) or "-" in core:
        return word
    return pre + dic.inserted(core, hyphen=SHY) + post


def to_native_digits(s, lang):
    nd = LANGS[lang].native_digits
    if not nd:
        return s
    return "".join(nd[ord(c) - 48] if "0" <= c <= "9" else c for c in s)


def fix_punct(s, lang):
    """Locale punctuation conventions on running text."""
    if lang == "fr":
        s = re.sub(r"\s*([;:!?»%])", lambda m: NNBSP + m.group(1), s)
        s = re.sub(r"«\s*", "«" + NNBSP, s)
        s = s.replace(NNBSP + NNBSP, NNBSP)
    elif lang in ("hi", "bn"):
        # Wikipedia/web text sometimes ends sentences with '.' after Indic letters; prefer danda.
        s = re.sub(r"(?<=[ऀ-৿])\.(\s|$)", "।\\1", s)
    elif lang == "ur":
        s = re.sub(r"(?<=[؀-ۿ])\.(\s|$)", "۔\\1", s)
        s = s.replace(",", "،") if re.search(r"[؀-ۿ],", s) else s
    elif lang == "ar":
        s = re.sub(r"(?<=[؀-ۿ]),", "،", s)
        s = re.sub(r"(?<=[؀-ۿ])\?", "؟", s)
    elif lang == "fa":
        s = s.replace("ي", "ی").replace("ك", "ک")      # Persian yeh / keheh, not the Arabic letters
        s = re.sub(r"(?<=[؀-ۿ]),", "،", s)
        s = re.sub(r"(?<=[؀-ۿ])\?", "؟", s)
        s = re.sub(r"(?<=[؀-ۿ]);", "؛", s)
    elif lang in ("zh-Hans", "zh-Hant", "ja"):
        cjk = r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]"
        s = re.sub(rf"(?<={cjk}) +(?={cjk})", "", s)                 # stray spaces between CJK characters
        full = {",": "、" if lang == "ja" else "，", "?": "？", "!": "！", ":": "：", ";": "；", "(": "（", ")": "）"}
        s = re.sub(rf"(?<={cjk})([,?!:;)])", lambda m: full[m.group(1)], s)
        s = re.sub(rf"\((?={cjk})", "（", s)
        s = re.sub(rf"(?<={cjk})\.(?=\s|$)", "。", s)
        if lang in ("zh-Hant", "ja"):
            s = s.replace("“", "「").replace("”", "」").replace("‘", "『").replace("’", "』")
    return s


def normalize(s):
    s = unicodedata.normalize("NFC", s)
    s = s.replace("​", "")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return s.strip()


_CJK_CHAR = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3005-\u3007"
                       r"\uff66-\uff9f\U00020000-\U0002ebef]")
# kinsoku: never at the start of a line (closing punctuation, small kana, prolonged sound mark) ...
_NO_START = set("、。，．・：；？！ー゛゜ヽヾゝゞ々〻）〕］｝〉》」』】〙〗〟’”｠»ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ"
                "ㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿ‥…%％),.:;!?]}")
# ... and never at the end of one (opening punctuation)
_NO_END = set("（〔［｛〈《「『【〘〖〝‘“｟«([{")


def cjk_tokens(s):
    """Split CJK text into line-breakable tokens: one per ideograph / kana, Latin & digit runs kept whole,
    closing punctuation glued to the previous token and opening punctuation to the next (kinsoku shori)."""
    raw, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if _CJK_CHAR.match(c) or c in _NO_START or c in _NO_END:
            raw.append(c)
            i += 1
            continue
        j = i
        while j < n and not _CJK_CHAR.match(s[j]) and s[j] not in _NO_END and \
                not (s[j] in _NO_START and not s[j].isascii()):
            j += 1
        raw.append(s[i:j])
        i = j
    out = []
    for t in raw:
        if out and (t[0] in _NO_START or out[-1][-1] in _NO_END):
            out[-1] += t
        else:
            out.append(t)
    return out


def _segment_of(lang):
    lang = lang or DOC.get("lang")
    return LANGS[lang].segment if lang in LANGS else "space"


def words_html(text, lang=None, hyph=False, cls="w", digits=False, extra_cls=""):
    """Tokenise text into <span class="w"> tokens (word + trailing space). Inline $latex$ -> math token.

    Applies the document digit policy (textkit.DOC) and drops tokens in unexpected scripts.
    """
    text = str(text)
    if "\\" in text:
        text = fix_math_delims(text)
    if digits and lang:
        text = to_native_digits(text, lang)
    script = DOC.get("script")
    out = []
    parts = _LATEX_INLINE.split(text) if "$" in text else [text]
    for part in parts:
        if not part:
            continue
        if part.startswith("$") and part.endswith("$") and len(part) > 2:
            if is_blank_math(part[1:-1]):
                out.append(f'<span class="{cls}">__________ </span>')
            else:
                out.append(f'<span class="m" data-latex="{esc(sanitize_latex(part[1:-1]))}"></span> ')
            continue
        for m in _WORD_RE.finditer(part):
            tok = m.group(0)
            word = strip_emoji(tok.rstrip())
            space = tok[len(word):] if word else ""
            if not word:
                continue
            if _GREEK_BARE.match(word):          # "alpha_{12}" written without the backslash
                word = "\\" + word
            if _COMB_ACC.search(word) and re.search(r"[_^]", word):
                # R̂_{k,t} / x̄_i written with combining accents -> \hat{R}_{k,t}, \bar{x}_i
                word = _COMB_ACC.sub(lambda m: "\\" + _ACC_CMD[m.group(2)] + "{" + m.group(1) + "}", word)
            gl = _GLUED_AR.match(word)
            if gl and _MATHY.match(gl.group(2)):
                # Arabic-script conjunction glued to a variable ("وu_{i-1}"): prefix as text, variable as math
                out.append(f'<span class="{cls}">{esc(gl.group(1))}</span>')
                word = gl.group(2)
            us = _uni_sub_to_latex(word)
            if us:                               # "Yᵢⱼ," -> $Y_{ij}$ + ","
                pre, core, post = us
                out.append((f'<span class="{cls}">{esc(pre)}</span>' if pre else "") +
                           f'<span class="m" data-latex="{esc(sanitize_latex(core))}"></span>' +
                           (f'<span class="{cls}">{esc(post)}{" " if space else ""}</span>' if post else
                            (" " if space else "")))
                continue
            mm = _MATHY.match(word)
            if not mm and "\\" in word and re.search(r"[_^]", word) and "://" not in word:
                # e.g. "SE(\hat{β}_j)," -- LaTeX inside a function call: the whole token is math
                m2 = re.match(r"^(.*?)([.,;:]*)$", word)
                mm = m2 if m2 and m2.group(1) else None
            if mm and "@" not in word and "://" not in word and not word.startswith("www."):
                core, tail = mm.group(1), mm.group(2)
                # LaTeX subscripts take one token: O_ij means O_i j -> brace multi-character sub/superscripts
                core = re.sub(r"([_^])([A-Za-z0-9]{2,})", r"\1{\2}", core)
                out.append(f'<span class="m" data-latex="{esc(sanitize_latex(core))}"></span>' +
                           (f'<span class="{cls}">{esc(tail)}{" " if space else ""}</span>' if tail else (" " if space else "")))
                continue
            word = apply_digits(word)
            if script and foreign_token(word, script):
                continue
            if hyph and lang:
                word = hyphenate_word(word, lang)
            c = cls + (" " + extra_cls if extra_cls else "")
            seg = _segment_of(lang)
            if seg == "cjk" and _CJK_CHAR.search(word):
                toks = cjk_tokens(word)
                for k, t in enumerate(toks):
                    out.append(f'<span class="{c}">{esc(t)}{" " if space and k == len(toks) - 1 else ""}</span>')
                continue
            if seg == "thai" and re.search(r"[\u0e00-\u0e7f]", word):
                # split into dictionary words in the page by Intl.Segmenter (engine.js SDD.segmentThai)
                out.append(f'<span class="{c} seg">{esc(word)}{" " if space else ""}</span>')
                continue
            out.append(f'<span class="{c}">{esc(word)}{" " if space else ""}</span>')
    return "".join(out)


def rich_html(segments, lang=None, hyph=False):
    """segments: list of (style, text) with style in {'', 'b', 'i', 'bi', 'u', 'code'}."""
    out = []
    for style, text in segments:
        out.append(words_html(text, lang, hyph=hyph and style != "code", extra_cls=style))
    return "".join(out)


def truncate_words(text, n):
    if _CJK_CHAR.search(text) and len(text.split()) < n / 4:
        return text[:int(n * 1.6)]           # ~1.6 CJK characters per word-equivalent
    if re.search(r"[\u0e00-\u0e7f]", text) and len(text.split()) < n / 4:
        return text[:int(n * 5.5)]           # Thai: spaces separate phrases, not words
    ws = text.split()
    return " ".join(ws[:n])


def sentences(text, lang):
    """Rough sentence split preserving the terminal punctuation."""
    pat = r"(?<=[.!?।۔؟])\s+|(?<=[。！？])"
    return [s for s in re.split(pat, text) if s and s.strip()]


def title_case_ok(lang):
    return lang in ("es", "fr", "pt", "id", "de", "ru", "en")


# ----------------------------------------------------------------------------- locale number formatting
DEC_COMMA = {"de", "es", "pt", "id", "fr", "ru", "it", "pl", "nl", "tr", "vi"}
THOUSANDS = {"de": ".", "es": ".", "pt": ".", "id": ".", "fr": "\u202f", "ru": "\u202f", "it": ".", "pl": "\u00a0",
             "nl": ".", "tr": ".", "vi": "."}


def fmt_num(x, lang, decimals=None, pct=False):
    """Format a number with the locale's decimal/thousands separators (digits converted by DOC policy later)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if decimals is None:
        decimals = 0 if abs(v) >= 100 and not pct else (1 if abs(v) >= 1 else 2)
    s = f"{abs(v):,.{decimals}f}"
    if lang in DEC_COMMA:
        s = s.replace(",", "\x00").replace(".", ",").replace("\x00", THOUSANDS.get(lang, "."))
    elif lang in ("hi", "bn") and abs(v) >= 100000:
        ip, _, fp = f"{abs(v):.{decimals}f}".partition(".")
        head, tail = ip[:-3], ip[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail]) + ("." + fp if fp else "")
    if lang == "fa":                         # Persian decimal / thousands separators
        s = s.replace(",", "\x00").replace(".", "٫").replace("\x00", "٬")
    if v < 0:
        s = "−" + s
    if pct:
        if lang == "tr":                     # Turkish writes the percent sign first: %25
            s = "%" + s
        elif lang == "fa":
            s = s + "٪"
        else:
            s = s + ("\u202f%" if lang in ("fr", "de", "ru") else "%")
    return s

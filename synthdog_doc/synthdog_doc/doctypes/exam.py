"""Exam paper pages: header block (first page) / running header, sections, typed questions, answer space.

v1 (after judge round 1): one marks style per paper with locale plural rules, consistent folios
("page x of y", "turn over" only before the last page), continuation only from same-subject packs,
cleaned matching tasks, localized true/false, figures only for math/physics, section heads kept with their
first question, leftover space filled by growing the last answer area, more header / emblem variants.
"""
import re

from .. import blocks as B
from .. import corpus as C
from ..diagrams import figure_for
from ..doc import Doc
from ..geometry import IN
from ..textkit import esc, words_html

HEADER_STYLES = ["board", "school_box", "university", "simple", "ministry", "grid", "left"]
NUM_STYLES = ["dot", "paren", "q", "word", "bold_dot"]
TF = {"es": "V / F", "fr": "V / F", "pt": "V / F", "de": "R / F", "id": "B / S", "ru": "Да / Нет",
      "ar": "صح / خطأ", "ur": "درست / غلط", "hi": "सही / गलत", "bn": "সত্য / মিথ্যা"}
MARK_WORDS = {"es": ("punto", "puntos"), "fr": ("point", "points"), "pt": ("ponto", "pontos"),
              "de": ("Punkt", "Punkte"), "id": ("poin", "poin"), "hi": ("अंक", "अंक"), "bn": ("নম্বর", "নম্বর"),
              "ur": ("نمبر", "نمبر")}
MATH_SUBJ = re.compile(r"math|matem|mathé|математ|गणित|গণিত|ریاضی|رياضيات|fisika|physi|física|физик|भौतिक|"
                       r"পদার্থ|طبیعیات|فيزياء|matemática|mathematik|matematika", re.I)
FAKE = re.compile(r"fikti|fictic|fictif|fictional|ficcion|फर्जी|কাল্পনিক|خيالي|فرضی", re.I)


def plural_marks(lang, n):
    if lang == "ru":
        m10, m100 = n % 10, n % 100
        return "балл" if (m10 == 1 and m100 != 11) else ("балла" if 2 <= m10 <= 4 and not 12 <= m100 <= 14 else "баллов")
    if lang == "ar":
        return "درجة" if n == 1 or n > 10 else ("درجتان" if n == 2 else "درجات")
    sg, pl = MARK_WORDS.get(lang, ("mark", "marks"))
    return sg if n == 1 else pl


_QWORDS = r"(?:Question|Q|Pregunta|Questão|Frage|Aufgabe|Soal|Вопрос|Задание|प्रश्न|প্রশ্ন|سوال|السؤال|Exercice|Ejercicio|Exercício)"
_QLEAD = re.compile(r"^\s*(?:" + _QWORDS + r"\s*)?[0-9০-৯०-९٠-٩۰-۹]{1,3}\s*[\.\):：۔।॥\-–]\s*", re.I)
_INLINE_SUBS = re.compile(r"(?:^|\s)\(?([a-dа-гअ-घক-ঘ])\)\s")


UNIV = re.compile(r"univ|جامعة|کلیة|كلية|विश्वविद्यालय|महाविद्यालय|বিশ্ববিদ্যালয়|یونیورسٹی|университет|институт|"
                  r"universitas|universidad|université|universität|hochschule|faculdade|faculté|fakultas|college",
                  re.I)
SUBMARK = {"hi": ["(क)", "(ख)", "(ग)", "(घ)"], "bn": ["(ক)", "(খ)", "(গ)", "(ঘ)"],
           "ur": ["(الف)", "(ب)", "(ج)", "(د)"], "ar": ["أ)", "ب)", "ج)", "د)"], "ru": ["а)", "б)", "в)", "г)"]}
OWN_MARK = re.compile(r"^\s*(?:\(?(?:[a-dA-D]|[ivx]{1,3}|[а-г]|[क-घ]|[ক-ঘ]|الف|[أبجد])\)|[a-d]\.)\s")


def strip_qlabel(s):
    prev = None
    s = str(s)
    while prev != s:
        prev = s
        s = _QLEAD.sub("", s, count=1)
    return s.strip()


def split_inline_subs(stem):
    """'Solve: a) x+1=2 b) 2x=4' -> ('Solve:', ['x+1=2', '2x=4']) when >= 2 inline sub-items are present."""
    parts = _INLINE_SUBS.split(" " + stem)
    if len(parts) < 5:
        return stem, []
    head = parts[0].strip()
    subs = [parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)]
    return head, [x for x in subs if x]


def strip_enum(s):
    return re.sub(r"^\s*(\(?[0-9A-Za-zА-Яа-яऀ-ॿঀ-৿؀-ۿ]{1,2}[\.\)]\s*)+", "", str(s)).strip()


_EFL = re.compile(r"ingl|inggris|angl|engl|अंग्रेज|ইংরেজ|الإنجليز|انگریز|англ", re.I)

class ExamPage(Doc):
    def __init__(self, rng, lang, version=0):
        super().__init__("exam", lang, rng, version)
        # English-as-a-foreign-language papers would put English text on a non-English page: skip them
        pool = [p for p in C.packs(lang, "exam") if not _EFL.search(str(p.get("subject", "")))]
        self.pack = rng.choice(pool) if pool else {"sections": []}
        self.landscape = self.page["orientation"] == "l"
        self.first = rng.random() < 0.4
        self.meta.update(page_role="first" if self.first else "continuation", pack=self.pack.get("_idx"),
                         layout="double_column" if self.landscape else "single_column")

    def style(self):
        r = self.rng
        s = {}
        s["body_pt"] = r.choice([10, 10.5, 11, 11, 12, 12.5]) if not self.landscape else r.choice([10.5, 11, 11.5, 12])
        s["lh"] = r.uniform(1.3, 1.6)
        s["body_role"] = r.choice(["serif", "serif", "sans"])
        s["head"] = r.choice(HEADER_STYLES)
        s["num"] = r.choice(NUM_STYLES)
        s["marks_pos"] = r.choice(["right", "right", "inline", "margin", "none"])
        s["marks_fmt"] = r.choice(["bracket_num", "paren_word", "bracket_word", "paren_num"])
        s["cols"] = 2 if self.landscape else (2 if r.random() < 0.25 else 1)
        s["margin_x"] = r.uniform(0.55, 0.95) * IN
        s["margin_t"] = r.uniform(0.5, 0.8) * IN
        s["margin_b"] = r.uniform(0.5, 0.8) * IN
        s["side_strip"] = r.random() < 0.15
        s["answer_lines"] = r.random() < 0.65
        s["section_box"] = r.choice(["none", "bar", "box", "underline", "caps"])
        labs = list(C.locale(self.lang).get("option_labels") or ["A", "B", "C", "D"])
        alt = list(C.locale(self.lang).get("option_labels_alt") or labs)
        s["opt_labels"] = labs if r.random() < 0.6 else alt
        s["opt_fmt"] = r.choice(["{}.", "({})", "{})", "{}"])
        s["watermark"] = r.random() < 0.06
        s["emblem"] = r.choice(["none", "none", "seal", "shield", "crest"])
        s["ink"] = "#111"
        s["answer_box"] = r.random() < 0.45
        return s

    # ------------------------------------------------------------------ helpers
    def qnum(self, n):
        st = self.s["num"]
        nn = self.num(n)
        if st in ("dot", "bold_dot"):
            return f"{nn}."
        if st == "paren":
            return f"{nn})"
        if st == "q" and self.typo["caps"] and self.lang not in ("ru",):
            return f"{C.L(self.lang, 'Question', grp='exam')[:1]}{nn}."
        if st == "q":
            return f"{nn}."
        return f"{C.L(self.lang, 'Question', grp='exam')} {nn}:"

    def marks_txt(self, m):
        f = self.s["marks_fmt"]
        n = self.num(m)
        w = plural_marks(self.lang, int(m))
        return {"bracket_num": f"[{n}]", "paren_word": f"({n} {w})", "bracket_word": f"[{n} {w}]",
                "paren_num": f"({n})"}[f]

    def fill_blanks(self, text):
        return re.sub(r"_{2,}|\.{4,}|…{2,}", "________", str(text))

    def stem_block(self, n, q, stem_text):
        s = self.s
        marks = int(q.get("marks") or 1)
        if self.version >= 4 and q.get("type") in ("mcq", "truefalse", "fill") and marks > 4:
            marks = self.rng.choice([1, 1, 2])
        bold = s["num"] in ("bold_dot", "word")
        mk = ""
        stem = self.fill_blanks(stem_text)
        if s["marks_pos"] == "inline":
            stem = stem + " " + self.marks_txt(marks)
        elif s["marks_pos"] in ("right", "margin"):
            mk = (f'<span class="mk" data-cat="text_block" data-bid="{B.bid("mk")}">'
                  f'{words_html(self.marks_txt(marks), self.lang)}</span>')
        num_html = f'<span class="qn{" b" if bold else ""}">{words_html(self.qnum(n) + " ", self.lang)}</span>'
        return (f'<div class="q"><div class="qs" data-cat="text_block" data-bid="{B.bid("q")}">'
                f'{num_html}{words_html(stem, self.lang)}</div>{mk}</div>')

    def options_block(self, opts):
        s = self.s
        labs = list(s["opt_labels"])
        if len(opts) > len(labs):
            labs = labs + [{"latin": "E", "cyrillic": "Д"}.get(self.fonts.script, "E")]
        items = []
        for i, o in enumerate(opts[:len(labs)]):
            lab = s["opt_fmt"].format(labs[i])
            # trailing spaces keep "A. text B. text" separated in the line-level ground truth
            items.append(f'<div class="opt">{words_html(lab + " ", self.lang)}{words_html(strip_enum(o) + " ", self.lang)}</div>')
        return (f'<div class="opts" data-prefs="4,2,1" data-cat="text_block" data-textmode="lines" '
                f'data-bid="{B.bid("o")}">{"".join(items)}</div>')

    def answer_space(self, kind, marks):
        r, s = self.rng, self.s
        lh = self.pt(s["body_pt"]) * 2.0
        n = {"short": r.randint(2, 3), "long": r.randint(4, 7), "calc": r.randint(3, 6)}.get(kind, 0)
        n = min(n, 2 + int(marks or 1))
        if n <= 0:
            return ""
        lines = (s["answer_lines"] or (not self.is_math and kind in ("short", "long") and r.random() < 0.8)) \
            and kind != "calc"
        if self.version >= 5 and not self.is_math and kind != "calc":
            lines = True          # written answers get ruled lines (no unexplained blank space)
        if lines:
            return (f'<div class="lines" data-grow="{lh:.2f}" style="height:{n * lh:.1f}px;'
                    f'background-size:100% {lh:.1f}px"></div>')
        if s.get("answer_box") or self.version >= 5:
            # framed working / answer area (common on math and science papers)
            return (f'<div class="space abox" data-grow="1" style="height:{n * lh * 0.8:.1f}px">'
                    f'{B.span_text(C.L(self.lang, "Answer", grp="exam") + ":", self.lang, "text_block", cls="aboxl")}'
                    f'</div>')
        return f'<div class="space" data-grow="1" style="height:{n * lh * 0.8:.1f}px"></div>'

    def question(self, n, q):
        r = self.rng
        t = q.get("type", "short")
        stem = strip_qlabel(q.get("stem", ""))
        if not q.get("subquestions"):
            stem, inline = split_inline_subs(stem)
            if inline:
                q = dict(q, subquestions=inline)
        if t == "truefalse":
            stem = f"{stem} ({TF.get(self.lang, 'T / F')})" if r.random() < 0.6 else f"{stem} (    )"
        parts = []
        passage = ('<div class="passage">' + B.para(q["passage"], self.lang, cls="pp", split=True, hyph=self.hyph())
                   + "</div>") if (t == "passage" and q.get("passage")) else ""
        if passage and self.version < 4:
            parts.append(passage)
        parts.append(self.stem_block(n, q, stem))
        if passage and self.version >= 4:
            parts.append(passage)
        if q.get("has_figure") and q.get("figure_kind") in ("geometry", "graph") and self.is_math:
            w = self.cw_col * r.uniform(0.32, 0.45)
            svg = figure_for(q.get("figure_kind"), r, w, self.fonts.stack("serif"), self.lang,
                             fs=self.pt(self.s["body_pt"]) * 0.95)
            g = B.bid("g")
            self.fig_n += 1
            cap = f"{C.L(self.lang, 'Figure', 'Fig.', grp='paper')} {self.num(self.fig_n)}"
            parts.append(f'<div class="qfig" style="width:{w:.0f}px"><div data-cat="figure" data-bid="{B.bid("f")}" '
                         f'data-group="{g}">{svg}</div><div class="qfcap" data-cat="figure_caption" '
                         f'data-bid="{B.bid("c")}" data-group="{g}">{words_html(cap, self.lang)}</div></div>')
        if t == "mcq" and q.get("options"):
            parts.append(self.options_block(q["options"]))
        elif t == "match" and q.get("pairs"):
            pairs = [p for p in q["pairs"][:5] if isinstance(p, (list, tuple)) and len(p) >= 2]
            right = [strip_enum(p[1]) for p in pairs]
            r.shuffle(right)
            labs = list(self.s["opt_labels"]) + ["E"]
            rows = [[self.num(f"{i + 1}."), strip_enum(p[0]), f"{labs[i % len(labs)]}.", rr]
                    for i, (p, rr) in enumerate(zip(pairs, right))]
            parts.append(B.table(None, rows, self.lang, cls="mtbl", num_align=False))
        markers = (SUBMARK.get(self.lang) if self.version >= 4 else None) or \
            C.locale(self.lang).get("list_markers") or ["a)", "b)", "c)", "d)"]
        for k, sq in enumerate((q.get("subquestions") or [])[:4]):
            own = OWN_MARK.match(str(sq)) if self.version >= 4 else None
            if own:   # the item already carries its own marker, e.g. "(الف)" -> keep it, do not add a second one
                txt = str(sq).strip()
            else:
                txt = self.num(str(markers[k % len(markers)])) + " " + strip_enum(sq)
            parts.append(f'<div class="sq" data-cat="text_block" data-bid="{B.bid("s")}">'
                         f'{words_html(self.fill_blanks(txt), self.lang)}</div>')
        parts.append(self.answer_space(t, q.get("marks")))
        return f'<div class="qwrap">{"".join(parts)}</div>'

    def section_head(self, sec, first_q=None, own_first=None):
        """first_q: printed number of the section's first question; own_first: its number inside the pack."""
        title = str(sec.get("title", ""))
        if self.s["section_box"] == "caps":
            title = self.upper(title)
        out = B.heading(title, self.lang, level=2, cls=f"sec {self.s['section_box']}", kwn=False)
        inst = str(sec.get("instruction") or "")
        if inst and first_q is not None and own_first is not None and first_q != own_first:
            n_q = len(sec.get("questions") or [])
            own = set(range(own_first, own_first + n_q))
            nums = [int(x) for x in re.findall(r"(?<![\d.,])\d{1,2}(?![\d.,%])", inst)]
            if nums and all(n in own for n in nums) and len(nums) <= 3:
                # question references ("answer questions 1 to 4") follow the printed numbering
                inst = re.sub(r"(?<![\d.,])\d{1,2}(?![\d.,%])", lambda m: str(int(m.group(0)) - own_first + first_q),
                              inst)
            elif nums:
                # mixed numbers (marks, counts): keep only sentences without digits
                sents = [x for x in re.split(r"(?<=[.!?।۔؟])\s+", inst) if not re.search(r"\d", x)]
                inst = " ".join(sents)
        if inst:
            out += B.para(inst, self.lang, cls="sinst", split=False)
        return out

    def emblem(self, inst):
        kind = self.s["emblem"]
        ini = "".join(w[0] for w in re.findall(r"\w+", inst)[:3]).upper()[:3] or "S"
        if self.fonts.script not in ("latin", "cyrillic"):
            ini = "★"   # initials of Indic / Arabic-script words are not written as monograms
        if kind == "none":
            return ""
        if kind == "seal":
            svg = (f'<svg viewBox="0 0 100 100" width="100%" height="100%"><circle cx="50" cy="50" r="46" fill="none" '
                   f'stroke="#222" stroke-width="3"/><circle cx="50" cy="50" r="38" fill="none" stroke="#222" '
                   f'stroke-width="1"/><text x="50" y="58" text-anchor="middle" font-size="24" font-weight="700">'
                   f'{esc(ini)}</text><path d="M30 72 L50 64 L70 72" fill="none" stroke="#222" stroke-width="2"/></svg>')
        elif kind == "shield":
            svg = (f'<svg viewBox="0 0 100 110" width="100%" height="100%"><path d="M50 4 L92 18 L88 62 Q80 92 50 106 '
                   f'Q20 92 12 62 L8 18 Z" fill="#f2f2f2" stroke="#222" stroke-width="3"/><text x="50" y="66" '
                   f'text-anchor="middle" font-size="26" font-weight="700">{esc(ini)}</text></svg>')
        else:
            svg = ('<svg viewBox="0 0 100 100" width="100%" height="100%"><polygon points="50,6 61,38 95,38 67,58 '
                   '78,92 50,72 22,92 33,58 5,38 39,38" fill="none" stroke="#222" stroke-width="3"/>'
                   '<circle cx="50" cy="52" r="12" fill="#222"/></svg>')
        return f'<div class="crest" data-cat="figure" data-bid="{B.bid("lg")}">{svg}</div>'

    def header_first(self):
        r, s, pk = self.rng, self.s, self.pack
        inst = pk.get("institution") or r.choice(C.locale(self.lang).get("schools") or ["School"])
        if FAKE.search(inst):
            inst = r.choice(C.locale(self.lang).get("schools") or ["School"])
        title = pk.get("exam_title", "")
        subj = pk.get("subject", "")
        if subj and subj in title:
            subj = ""
        dur = int(pk.get("duration_minutes") or 120)
        mm = int(pk.get("max_marks") or 100)
        t_allowed = C.L(self.lang, "Time allowed", grp="exam")
        t_max = C.L(self.lang, "Maximum marks", grp="exam")
        hrs = (f"{self.num(dur // 60)} {C.L(self.lang, 'hours', grp='exam')}" if dur % 60 == 0 else
               f"{self.num(dur)} {C.L(self.lang, 'minutes', grp='exam')}")
        time_txt = B.span_text(f"{t_allowed}: {hrs}", self.lang, "text_block", cls="h-l")
        max_txt = B.span_text(f"{t_max}: {self.num(mm)}", self.lang, "text_block", cls="h-r")
        hs = s["head"]
        if self.version >= 5 and hs in ("ministry", "board") and UNIV.search(inst):
            hs = "university"   # a ministry / exam-board banner does not head a university examination
        parts = []
        if hs == "grid":
            fields = [C.L(self.lang, "Name", grp="exam"), C.L(self.lang, "Class/Grade", grp="exam")]
            parts.append('<table class="hgrid"><tr><td colspan="2" class="gi">'
                         + B.heading(inst, self.lang, level=1, cls="h-inst", kwn=False, fit_lines="2")
                         + '</td></tr><tr><td colspan="2" class="gt">'
                         + B.heading(title, self.lang, level=2, cls="h-title", kwn=False, fit_lines="2")
                         + f'</td></tr><tr><td>{time_txt}</td><td>{max_txt}</td></tr><tr>'
                         + "".join(f'<td>{B.span_text(f + ":", self.lang, "text_block", cls="fl")}</td>' for f in fields)
                         + '</tr></table>')
        elif hs == "left":
            parts.append(f'<div class="hleft"><div>{self.emblem(inst)}'
                         f'{B.heading(inst, self.lang, level=1, cls="h-inst", kwn=False, fit_lines="2")}'
                         f'{B.span_text(subj, self.lang, "text_block", cls="h-subj") if subj else ""}</div>'
                         f'<div class="hright">{B.heading(title, self.lang, level=2, cls="h-title", kwn=False, fit_lines="3")}'
                         f'{time_txt}{max_txt}</div></div>')
        else:
            if hs == "ministry":
                board = r.choice(C.locale(self.lang).get("exam_boards") or [inst])
                parts.append(B.span_text(board, self.lang, "text_block", cls="h-board"))
            parts.append(self.emblem(inst))
            parts.append(B.heading(inst, self.lang, level=1, cls="h-inst", kwn=False, fit_lines="2"))
            parts.append(B.heading(title, self.lang, level=2, cls="h-title", kwn=False, fit_lines="2"))
            if subj:
                parts.append(B.span_text(f"{C.L(self.lang, 'Subject', grp='exam')}: {subj}", self.lang, "text_block",
                                         cls="h-subj"))
            parts.append(f'<div class="h-row">{time_txt}{max_txt}</div>')
        if hs != "grid" and (hs in ("school_box", "simple") or r.random() < (0.75 if self.version >= 4 else 0.35)):
            fields = [C.L(self.lang, "Name", grp="exam"), C.L(self.lang, "Class/Grade", grp="exam"),
                      C.L(self.lang, "Roll number", grp="exam"), C.L(self.lang, "Date", grp="exam")]
            cells = "".join(f'<div class="fld">{B.span_text(f + ":", self.lang, "text_block", cls="fl")}'
                            f'<span class="fline"></span></div>' for f in fields[: r.randint(2, 4)])
            parts.append(f'<div class="fields">{cells}</div>')
        if pk.get("instructions") and r.random() < 0.8:
            gi = C.L(self.lang, "General instructions", grp="exam")
            items = "".join(B.para(f"{self.num(i + 1)}. {strip_enum(x)}", self.lang, cls="ins", split=False)
                            for i, x in enumerate(pk["instructions"][:5]))
            box = " boxed" if r.random() < 0.6 else ""
            parts.append(f'<div class="instr{box}">' + B.heading(gi, self.lang, level=3, cls="ih", kwn=False)
                         + items + "</div>")
        n_mcq = sum(1 for sec in pk.get("sections") or [] for q in sec.get("questions") or [] if q.get("type") == "mcq")
        if n_mcq >= 4 and r.random() < 0.3:
            labs = list(s["opt_labels"])[:4]
            n = min(n_mcq, r.choice([10, 15, 20]))
            per_row = 5 if n > 10 else n
            head = []
            rows = []
            for k in range(0, n, per_row):
                rows.append(sum(([self.num(i + 1)] + ["  ".join(f"○{lb}" if self.typo["caps"] else f"{lb}○" for lb in labs)]
                                 for i in range(k, min(n, k + per_row))), []))
            parts.append(B.heading(C.L(self.lang, "Answer", grp="exam"), self.lang, level=3, cls="ih", kwn=False))
            parts.append(B.table(head, rows, self.lang, cls="omr", num_align=False))
        if r.random() < 0.25 and pk.get("sections"):
            secs = pk["sections"][:5]
            labels = [str(sec.get("title", "")).split(":")[0][:14] or self.num(i + 1) for i, sec in enumerate(secs)]
            parts.append(B.table([C.L(self.lang, "Section", grp="exam")] + labels + [C.L(self.lang, "Total", grp="exam")],
                                 [[C.L(self.lang, "Score", grp="exam")] + [""] * (len(labels) + 1)], self.lang,
                                 cls="score", num_align=False))
        return "".join(parts)

    def running_header(self):
        pk = self.pack
        subj, title = str(pk.get("subject", "")).strip(), str(pk.get("exam_title", "")).strip()
        inst = str(pk.get("institution", "")).strip()
        if subj and subj.lower() in title.lower():
            subj = ""
        parts = [x for x in (inst if self.rng.random() < 0.4 else "", subj, title) if x]
        return B.span_text(" — ".join(parts[:2]) or title or subj, self.lang, "header", cls="rh")

    # ------------------------------------------------------------------ page
    def build(self):
        r = self.rng
        self.s = s = self.style()
        self.is_math = bool(MATH_SUBJ.search(str(self.pack.get("subject", ""))))
        self.fig_n = 0
        W, H = self.W, self.H
        mx, mt, mb = s["margin_x"], s["margin_t"], s["margin_b"]
        strip_w = 0.32 * IN if s["side_strip"] else 0
        x0 = mx + (0 if self.rtl else strip_w)
        cw = W - 2 * mx - strip_w
        ncol = s["cols"]
        gap = (0.6 if self.landscape else 0.3) * IN
        self.cw_col = (cw - gap * (ncol - 1)) / ncol
        body_px = self.pt(s["body_pt"])
        secs = self.pack.get("sections") or []
        n_total = sum(len(sec.get("questions") or []) for sec in secs)
        qpp = (10 if self.landscape else 6) * (1.4 if ncol == 2 else 1.0)   # questions per page (estimate)
        start_sec = 0 if self.first else r.randint(0, max(0, len(secs) - 1))
        skip0 = 0
        if not self.first and start_sec < len(secs) and len(secs[start_sec].get("questions") or []) > 2:
            skip0 = r.randint(0, len(secs[start_sec].get("questions") or []) // 2)
        q_first = 1 + sum(len(sec.get("questions") or []) for sec in secs[:start_sec]) + skip0
        pg = 1 if self.first else max(2, 1 + int((q_first - 1 + qpp * 0.4) // qpp) + 1)
        tot = max(pg + 1, pg + int(max(0, n_total - q_first) // qpp) + r.randint(0, 1))
        zones = []
        if s["side_strip"]:
            sx = W - mx * 0.6 - strip_w if self.rtl else mx * 0.6
            txt = C.L(self.lang, "Do not write in this margin", grp="exam")
            zones.append(f'<div class="zone strip" style="left:{sx:.1f}px;top:{mt:.1f}px;width:{strip_w:.1f}px;'
                         f'height:{H - mt - mb:.1f}px"><div class="striptx" data-cat="abandon" '
                         f'data-bid="{B.bid("st")}">{words_html(txt, self.lang)}</div></div>')
        top = mt
        top_from = None
        head_float = None
        if self.first and ncol == 2 and self.landscape:
            head_float = f'<div class="ehead" data-place="top" data-col="0">{self.header_first()}</div>'
        elif self.first:
            zones.append(B.zone(x0, top, cw, 0, self.header_first(), zid="examhead", auto_h=True, cls="ehead"))
            top_from = "#examhead"
        else:
            rh = self.running_header()
            if r.random() < 0.5:
                rh += B.span_text(self.iso(self.num(pg)), self.lang, "page_number", cls="rhcode")
            zones.append(B.zone(x0, top - body_px * 1.9, cw, body_px * 1.6, f'<div class="rhrow">{rh}</div>'))
        flow = [head_float] if head_float else []
        qn = 1
        for si, sec in enumerate(secs):
            qs = sec.get("questions") or []
            if si < start_sec:
                qn += len(qs)
                continue
            skip = skip0 if si == start_sec else 0
            qn += skip
            head = "" if skip else self.section_head(sec, qn, qn)
            for k, q in enumerate(qs[skip:]):
                qh = self.question(qn, q)
                if k == 0 and head:
                    qh = f'<div class="secwrap">{head}{qh}</div>'
                flow.append(qh)
                qn += 1
        same = [p for p in C.packs(self.lang, "exam") if p.get("subject") == self.pack.get("subject")
                and p is not self.pack]
        if same and self.version < 4:
            # the paper continues with more sections of the same subject (numbering continues)
            other = r.choice(same)
            own = 1
            for sec in (other.get("sections") or [])[:2]:
                for k, q in enumerate(sec.get("questions") or []):
                    qh = self.question(qn, q)
                    if k == 0:
                        qh = f'<div class="secwrap">{self.section_head(sec, qn, own)}{qh}</div>'
                    flow.append(qh)
                    qn += 1
                    own += 1
        bz = B.zone(x0, top, cw, H - mt - mb, "".join(flow), flow=True, cols=ncol, gap=f"{gap:.1f}px",
                    rule=("0.8px solid #555" if self.landscape and r.random() < 0.7 else None), zorder=1,
                    top_from=top_from, gap_top=body_px * 0.8, minhead=1)
        # vertical justification: spread leftover column space over the gaps between questions
        bz = bz.replace('class="zone flow', f'data-vjustify=".qwrap" data-vjmax="{body_px * 2.2:.1f}" class="zone flow', 1)
        if self.version >= 5:
            bz = bz.replace('class="zone flow', 'data-compact="1" data-stopondrop="1" data-growall="1" class="zone flow', 1)
        zones.append(bz)
        pat = C.L(self.lang, "Page {x} of {y}", "{x} / {y}", grp="exam")
        pn = pat.replace("{x}", self.num(pg)).replace("{y}", self.num(tot))
        foot = [B.span_text(self.iso(pn) if "/" in pat else pn, self.lang, "page_number", cls="pn")]
        if pg < tot and r.random() < 0.4:
            foot.append(B.span_text(C.L(self.lang, "Turn over", grp="exam"), self.lang, "footer", cls="pto"))
        if self.landscape and r.random() < 0.6:
            zones.append(B.zone(x0, H - mb + body_px * 0.6, cw, body_px * 2.0,
                                f'<div class="foot2">{B.span_text(self.num(pg * 2 - 1), self.lang, "page_number", cls="pn")}'
                                f'{B.span_text(self.num(pg * 2), self.lang, "page_number", cls="pn")}</div>'))
        else:
            zones.append(B.zone(x0, H - mb + body_px * 0.6, cw, body_px * 2.0, f'<div class="foot">{"".join(foot)}</div>'))
        if s["watermark"]:
            inst = self.pack.get("institution") or "School"
            zones.append(f'<div class="zone wm" style="left:0;top:{H * 0.42:.1f}px;width:{W:.1f}px;height:{H * 0.2:.1f}px">'
                         f'<div class="wmt" data-cat="abandon" data-bid="{B.bid("wm")}">{words_html(inst, self.lang)}</div></div>')
            self.meta["special_issue"] = ["watermark"]
        return self.spec("".join(zones), self.css(body_px))

    def css(self, body_px):
        r, s = self.rng, self.s
        f_body = self.body_font(s["body_role"])
        f_head = self.fonts.stack("sans" if r.random() < 0.5 else "serif") if not self.nastaliq else self.fonts.stack("nastaliq")
        bw = self.bw(s["body_role"])
        lh = self.lh(s["lh"])
        sec = {"none": "", "bar": "background:#e6e6e6;padding:0.15em 0.4em;", "box": "border:1px solid #222;padding:0.15em 0.4em;",
               "underline": "border-bottom:1.2px solid #222;padding-bottom:0.1em;", "caps": ""}[s["section_box"]]
        mk_pos = "position:absolute;inset-inline-end:0;top:0;" if s["marks_pos"] in ("right", "margin") else ""
        q_pad = "padding-inline-end:4.6em;" if s["marks_pos"] in ("right", "margin") else ""
        return f"""
#page{{font-family:{f_body};font-size:{body_px:.2f}px;line-height:{lh};color:{s['ink']};--bw:{bw};}}
.ehead{{text-align:center;}}
.crest{{width:{body_px * 4.2:.1f}px;height:{body_px * 4.2:.1f}px;margin:0 auto 0.3em;}}
.h-board{{font-size:{body_px * 1.05:.1f}px;font-weight:600;margin-bottom:0.2em;}}
.h-inst{{font-family:{f_head};font-size:{body_px * r.uniform(1.35, 1.8):.1f}px;font-weight:{bw};margin:0 0 0.15em;line-height:{self.lh(1.2)};}}
.h-title{{font-family:{f_head};font-size:{body_px * r.uniform(1.15, 1.4):.1f}px;font-weight:{bw};margin:0 0 0.2em;line-height:{self.lh(1.2)};}}
.h-subj{{font-weight:600;margin-bottom:0.2em;}}
.h-row{{display:flex;justify-content:space-between;border-top:1px solid #222;border-bottom:1px solid #222;padding:0.15em 0;margin:0.3em 0;font-weight:600;}}
table.hgrid{{width:100%;border-collapse:collapse;margin-bottom:0.4em;}}
table.hgrid td{{border:1px solid #222;padding:0.25em 0.5em;text-align:start;}}
table.hgrid td.gi,table.hgrid td.gt{{text-align:center;}}
.hleft{{display:flex;justify-content:space-between;gap:1em;text-align:start;border-bottom:1.5px solid #222;padding-bottom:0.3em;margin-bottom:0.4em;}}
.hleft .crest{{margin:0 0 0.2em;}}
.hright{{text-align:end;}}
.fields{{display:flex;flex-wrap:wrap;gap:0.4em 1.2em;margin:0.5em 0;text-align:start;}}
.fld{{display:flex;align-items:flex-end;gap:0.3em;flex:1 1 40%;}}
.fline{{flex:1;border-bottom:1px solid #333;height:1.1em;}}
.instr{{text-align:start;margin:0.4em 0;font-size:{body_px * 0.92:.1f}px;}}
.instr.boxed{{border:1px solid #333;padding:0.4em 0.6em;}}
.ih{{font-size:{body_px:.1f}px;font-weight:{bw};margin:0 0 0.2em;}}
.ins{{margin:0.1em 0;}}
table.score{{border-collapse:collapse;margin:0.4em auto;font-size:{body_px * 0.9:.1f}px;}}
table.score td,table.score th{{border:1px solid #333;padding:0.2em 0.6em;min-width:2.6em;height:1.6em;}}
.rhrow{{display:flex;justify-content:space-between;border-bottom:0.8px solid #333;font-size:{body_px * 0.85:.1f}px;}}
.sec{{font-family:{f_head};font-size:{body_px * 1.08:.1f}px;font-weight:{bw};margin:0.8em 0 0.35em;{sec}line-height:{self.lh(1.25)};}}
.col>.secwrap:first-child .sec{{margin-top:0;}}
.sinst{{font-style:{self.italic(s['body_role'])};margin:0 0 0.4em;}}
.qwrap{{margin:0 0 {r.uniform(0.5, 1.0):.2f}em;}}
.q{{position:relative;{q_pad}}}
.qs{{text-align:start;}}
.qn{{margin-inline-end:0.35em;}}
.qn.b{{font-weight:{bw};}}
.mk{{{mk_pos}font-size:{body_px * 0.9:.1f}px;white-space:nowrap;}}
.opts{{display:grid;column-gap:1.2em;row-gap:0.15em;margin:0.25em 0 0.2em;padding-inline-start:1.4em;}}
.opts.g4{{grid-template-columns:repeat(4,minmax(0,1fr));}}
.opts.g3{{grid-template-columns:repeat(3,minmax(0,1fr));}}
.opts.g2{{grid-template-columns:repeat(2,minmax(0,1fr));}}
.opts.g1{{grid-template-columns:minmax(0,1fr);}}
.opt{{min-width:0;}}
.opt .w:first-child{{margin-inline-end:0.3em;}}
.sq{{padding-inline-start:1.6em;margin:0.15em 0;}}
.qfig{{margin:0.3em auto;text-align:center;}}
.qfcap{{font-size:{body_px * 0.85:.1f}px;margin-top:0.15em;}}
.passage{{border:1px solid #444;padding:0.4em 0.6em;margin:0.3em 0;font-size:{body_px * 0.95:.1f}px;}}
.pp{{text-align:{'justify' if self.typo['justify'] > 0.5 else 'start'};text-indent:1.2em;}}
.lines{{background-image:linear-gradient(to bottom,transparent calc(100% - 1px),#777 calc(100% - 1px));margin:0.2em 0 0.3em;}}
.abox{{border:1px solid #888;border-radius:{self.rng.choice([0, 3])}px;margin:0.3em 0 0.4em;padding:0.2em 0.4em;}}
.aboxl{{font-size:0.8em;color:#555;}}
table.mtbl{{border-collapse:collapse;margin-block:0.3em;margin-inline-start:1.4em;}}
table.omr{{border-collapse:collapse;margin:0.2em auto 0.5em;font-size:{body_px * 0.9:.1f}px;}}
table.omr td{{border:1px solid #444;padding:0.15em 0.45em;white-space:nowrap;}}
table.omr td:nth-child(odd){{font-weight:700;background:#f0f0f0;}}
table.mtbl td{{padding:0.1em 0.8em 0.1em 0.2em;vertical-align:top;}}
.foot,.foot2{{display:flex;justify-content:{r.choice(['center', 'space-between'])};gap:2.5em;font-size:{body_px * 0.88:.1f}px;}}
.foot2{{justify-content:space-around;}}
.pto{{font-style:{self.italic(s['body_role'])};}}
.strip{{border-inline-end:1px dashed #666;}}
.striptx{{writing-mode:vertical-rl;transform:rotate(180deg);font-size:{body_px * 0.8:.1f}px;color:#555;height:100%;text-align:center;}}
.wm{{display:flex;align-items:center;justify-content:center;pointer-events:none;}}
.wmt{{transform:rotate(-30deg);font-size:{body_px * 4.5:.1f}px;color:rgba(0,0,0,0.07);font-weight:800;white-space:nowrap;}}
.katex{{direction:ltr;unicode-bidi:isolate;}}
"""


def make(rng, lang, version=0):
    return ExamPage(rng, lang, version).build()

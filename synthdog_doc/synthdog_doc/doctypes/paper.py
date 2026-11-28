"""Academic paper pages (single / double column) with page roles, publisher profiles and LaTeX-like floats."""
import random
import re

from .. import blocks as B
from .. import corpus as C
from ..charts import Chart, random_series
from ..doc import Doc
from ..geometry import IN, PT
from ..textkit import truncate_words, esc, words_html

PROFILES = {
    # name: weights per layout (single, double)
    "journal_classic": (3, 3), "ieee_like": (0, 3), "elsevier_like": (2, 2), "springer_like": (3, 1),
    "local_word": (4, 1), "arxiv_preprint": (3, 1), "manuscript": (2, 0),
}
SUP = str.maketrans("0123456789,*", "⁰¹²³⁴⁵⁶⁷⁸⁹˒*")
_HNUM = re.compile(r"^\s*(?:[IVX]{1,4}\.|[\d০-৯०-९٠-٩۰-۹]+(?:\.[\d০-৯०-९٠-٩۰-۹]+)*[.)]?)\s+")
_REFLAB = re.compile(r"^\s*(?:\[\s*[0-9০-৯०-९٠-٩۰-۹]{1,3}\s*\]|\(\s*[0-9০-৯०-९٠-٩۰-۹]{1,3}\s*\)|"
                     r"[0-9০-৯०-९٠-٩۰-۹]{1,3}[.)])\s*(?:[0-9০-৯०-९٠-٩۰-۹]{1,3}[.)]\s*)?")
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def _pick_profile(rng, double, script):
    names = [n for n in PROFILES if PROFILES[n][1 if double else 0] > 0]
    w = [PROFILES[n][1 if double else 0] for n in names]
    if script not in ("latin", "cyrillic"):
        # non-Latin journals are mostly Word-produced or local templates
        w = [x * (2.5 if n == "local_word" else (0.3 if n in ("ieee_like", "arxiv_preprint") else 1)) for n, x in zip(names, w)]
    return rng.choices(names, weights=w)[0]


def _fallback_pack(lang, rng):
    cp = C.corpus(lang)
    a = cp.wiki_article(rng, 4000)
    secs = [{"heading": s["heading"] or a["title"], "paragraphs": s["paras"][:4], "subsections": []}
            for s in a["sections"][:6]]
    return {"title": a["title"], "authors": [C.person(lang, rng) for _ in range(3)], "affiliations": [],
            "abstract": a["sections"][0]["paras"][0], "keywords": [a["title"]], "sections": secs, "equations": [],
            "figures": [], "tables": [], "references": [], "_idx": -1}


class PaperPage(Doc):
    def __init__(self, rng, lang, double, version=0, role=None):
        super().__init__("paper_double" if double else "paper_single", lang, rng, version)
        self.double = double
        self.prof = _pick_profile(rng, double, self.fonts.script)
        pool = C.packs(lang, "paper")
        rich = [p for p in pool if p.get("_x")]
        self.pack = rng.choice(rich or pool) if pool else _fallback_pack(lang, rng)
        self.x = self.pack.get("_x") or {}
        self.role = role or rng.choices(["first", "body", "last"], weights=[0.2, 0.6, 0.2])[0]
        self.meta.update(profile=self.prof, page_role=self.role, pack=self.pack.get("_idx"),
                         layout="double_column" if double else "single_column")

    # ------------------------------------------------------------------ style
    def style(self):
        r, p = self.rng, self.prof
        s = {}
        s["body_role"] = "sans" if (p == "elsevier_like" and r.random() < 0.25) else "serif"
        if p == "local_word":
            s["body_pt"] = r.choice([11, 12, 12, 12, 13]) if not self.double else r.choice([10, 10.5, 11])
            s["lh"] = r.choice([1.35, 1.5, 1.5, 1.15]) if not self.double else r.choice([1.15, 1.25])
        elif self.double:
            s["body_pt"] = r.choice([9, 9.5, 10, 10])
            s["lh"] = r.uniform(1.12, 1.24)
        else:
            s["body_pt"] = r.choice([10, 10.5, 11, 11, 12])
            s["lh"] = r.uniform(1.2, 1.38)
        s["indent"] = r.choice([1.0, 1.2, 1.5, 2.0]) if p != "local_word" else r.choice([0, 1.27 * 37.8 / 16, 2])
        s["parsep"] = 0 if p != "local_word" else r.choice([0, 0, 0.4, 0.6])
        s["head_role"] = "sans" if p in ("elsevier_like", "springer_like") and r.random() < 0.7 else s["body_role"]
        s["head_center"] = p in ("ieee_like",) or (p == "local_word" and r.random() < 0.4)
        s["head_num"] = "roman" if (p == "ieee_like" and self.typo["caps"]) else r.choice(["dot", "plain"])
        s["head_upper"] = p == "ieee_like" and self.typo["caps"]
        s["ink"] = "#111"
        s["accent"] = r.choice(["#003366", "#8B0000", "#1F4E79", "#00467F", "#4B2E83", "#004D40"]) \
            if p in ("elsevier_like", "springer_like", "journal_classic") and r.random() < 0.6 else "#111"
        s["table"] = r.choices(["booktabs", "grid", "light"], weights=[6, 2, 2] if p != "local_word" else [2, 5, 2])[0]
        s["cap_label_bold"] = r.random() < 0.75
        s["cap_center"] = r.random() < 0.5
        s["pn_pos"] = r.choice(["bottom-center", "header-outer", "bottom-outer"])
        s["margin_x"] = (r.uniform(0.55, 0.8) if self.double else r.uniform(0.85, 1.25)) * IN
        s["margin_top"] = r.uniform(0.6, 0.95) * IN
        s["margin_bot"] = r.uniform(0.6, 0.95) * IN
        s["gap"] = r.uniform(0.2, 0.33) * IN
        s["justify"] = "justify" if (r.random() < self.typo["justify"] + 0.1) else "start"
        s["rule"] = "0.6px solid #444" if (self.double and r.random() < 0.15) else None
        if p == "manuscript":   # author-submitted manuscript: 12 pt, double spaced, ragged right, line numbers
            s.update(body_pt=r.choice([11, 12, 12]), lh=r.choice([2.0, 2.0, 1.8]), justify="start",
                     indent=r.choice([2.0, 2.5]), parsep=0, head_center=False, head_upper=False, accent="#111",
                     table=r.choice(["grid", "light"]), pn_pos="bottom-center", margin_x=r.uniform(1.0, 1.2) * IN,
                     head_num=r.choice(["dot", "plain"]), lineno=r.choice([1, 5, 5]))
        return s

    # ------------------------------------------------------------------ content
    def _sec_title(self, n, text, sub=None):
        s = self.s
        text = _HNUM.sub("", str(text)).strip()   # packs sometimes number their own headings
        if s["head_num"] == "roman" and sub is None:
            lab = f"{ROMAN[(n - 1) % 10]}. "
        elif sub is not None:
            lab = f"{n}.{sub} " if s["head_num"] == "plain" else f"{n}.{sub}. "
        else:
            lab = f"{n} " if s["head_num"] == "plain" else f"{n}. "
        text = self.upper(text) if (s["head_upper"] and sub is None) else text
        return self.num(lab) + text

    def _blocks_from_pack(self):
        """Flatten the pack into an ordered list of (kind, payload).

        v1: equations go where the enrichment says, introduced by a lead-in sentence and followed by a
        'where ...' paragraph; figures carry data consistent with the prose and are mentioned before they float.
        """
        pk, seq, x = self.pack, [], self.x
        eqs = list(pk.get("equations") or [])
        figs = list(pk.get("figures") or [])
        tabs = list(pk.get("tables") or [])
        secs = pk.get("sections") or []
        place = {}
        for e in x.get("equation_placement") or []:
            try:
                place.setdefault((int(e["section"]), int(e["after_paragraph"])), []).append(e)
            except (KeyError, TypeError, ValueError):
                continue
        fdata = {}
        for f in x.get("figure_data") or []:
            try:
                fdata[int(f["fig"])] = f
            except (KeyError, TypeError, ValueError):
                continue
        fig_by_sec = {}
        for fi, f in fdata.items():
            fig_by_sec.setdefault(int(f.get("section", 2) or 2), []).append(fi)
        used_eq, used_fig, used_tab = set(), set(), set()

        def emit_eqs(si, pi):
            for e in place.get((si, pi), []):
                k = e.get("eq")
                if isinstance(k, int) and 0 <= k < len(eqs) and k not in used_eq:
                    used_eq.add(k)
                    if e.get("lead_in"):
                        seq.append(("p_lead", e["lead_in"]))
                    seq.append(("eq", eqs[k]))
                    if e.get("follow_up"):
                        seq.append(("p_where", e["follow_up"]))

        for i, sec in enumerate(secs):
            seq.append(("h", (i + 1, None, sec.get("heading", ""))))
            for j, ptxt in enumerate(sec.get("paragraphs") or []):
                seq.append(("p", ptxt))
                emit_eqs(i, j)
                if j == 0:
                    for fi in fig_by_sec.get(i, []):
                        if fi not in used_fig and fi < len(figs):
                            used_fig.add(fi)
                            f = fdata[fi]
                            if f.get("mention"):
                                seq.append(("p", f["mention"]))
                            seq.append(("fig", dict(figs[fi], **{"_data": f, "_fi": fi})))
            for k, sub in enumerate(sec.get("subsections") or [], 1):
                seq.append(("h", (i + 1, k, sub.get("heading", ""))))
                for ptxt in sub.get("paragraphs") or []:
                    seq.append(("p", ptxt))
            if i >= 1 and tabs and len(used_tab) < len(tabs) and self.rng.random() < 0.6:
                ti = len(used_tab)
                used_tab.add(ti)
                seq.append(("tab", tabs[ti]))
        if not place:   # no enrichment: v0 behaviour (equations interleaved after paragraphs)
            out, rest = [], list(eqs)
            for kind, pay in seq:
                out.append((kind, pay))
                if kind == "p" and rest and self.rng.random() < 0.35:
                    out.append(("eq", rest.pop(0)))
            seq = out
        return seq

    def _para(self, text, first=False, cont=False):
        cls = "bp" + (" first" if first else "") + (" cont" if cont else "")
        return B.para(text, self.lang, cls=cls, hyph=self.hyph(), digits=self.native_digits)

    def _fig(self, f, num, width_px):
        r = self.rng
        d = f.get("_data") or {}
        kind = d.get("kind") or f.get("kind", "bar")
        cats = [str(c) for c in (d.get("categories") or f.get("categories") or ["A", "B", "C", "D"])][:7]
        names = [str(n) for n in (f.get("series_names") or ["S1"])][:3]
        dser = []
        for sr in (d.get("series") or [])[:3]:
            vals = [v for v in (sr.get("values") or []) if isinstance(v, (int, float))][:len(cats)]
            if len(vals) == len(cats):
                dser.append({"name": str(sr.get("name", "")), "values": vals})
        h = width_px * (r.uniform(0.34, 0.48) if width_px > 520 else r.uniform(0.55, 0.72))
        ch = Chart(width_px, h, self.fonts.stack("sans"), self.lang, rtl=self.rtl, digits_native=self.native_digits,
                   palette=r.choice(["mpl", "gray", "office", "excel2"]), fs=max(9, self.s["body_pt"] * PT * 0.82),
                   grid=r.random() < 0.6, frame=r.random() < 0.3)
        if kind == "pie":
            vals = [abs(v) for v in dser[0]["values"]] if dser else [abs(v) + 1 for v in random_series(r, len(cats), 1)[0]]
            svg = ch.pie(cats, vals)
        else:
            k = {"bar": "bar", "line": "line", "scatter": "scatter"}.get(kind, r.choice(["bar", "line"]))
            series = dser or [{"name": n, "values": v} for n, v in zip(names, random_series(r, len(cats), len(names), k))]
            svg = ch.xy(cats, series, kind=k, xlabel=d.get("x_label") or f.get("x_label", ""),
                        ylabel=d.get("y_label") or f.get("y_label", ""))
        lab = C.L(self.lang, "Figure", "Fig.", grp="paper")
        cap = f"{lab} {self.num(num)}. {f.get('caption', '')}"
        html = B.figure(svg, cap, self.lang, cls="fig", capcls="cap", digits=False)
        if isinstance(f, dict) and f.get("_fi") is not None:   # identity marker (span float de-duplication)
            html = html.replace('<div class="fig"', f'<div data-fi="{f["_fi"]}" class="fig"', 1)
        return html

    def _tab(self, t, num):
        lab = C.L(self.lang, "Table", "Table", grp="paper")
        cap = f"{lab} {self.num(num)}. {t.get('caption', '')}"
        header = [str(h) for h in (t.get("header") or [])][:6]
        rows = [[str(c) for c in row][: len(header) or 6] for row in (t.get("rows") or [])][:8]
        rows = [[self.num(c) for c in row] for row in rows]
        return B.table(header, rows, self.lang, caption=cap, cls="tbl " + self.s["table"], capcls="cap tcap")

    def _eq(self, e, num):
        latex = e.get("latex") if isinstance(e, dict) else str(e)
        return B.equation(latex.strip().strip("$"), f"({self.num(num)})", lang=self.lang)

    def vol_issue(self, vol, issue, cm=", "):
        """Volume / issue label in the local journal convention."""
        v, n = self.num(vol), self.num(issue)
        if self.lang == "ja":
            return f"第{v}巻 第{n}号"
        if self.lang == "zh-Hans":
            return f"第{v}卷 第{n}期"
        if self.lang == "zh-Hant":
            return f"第{v}卷 第{n}期"
        if self.lang == "ko":
            return f"제{v}권 제{n}호"
        return f"{C.L(self.lang, 'Vol.', grp='paper')} {v}{cm}{C.L(self.lang, 'No.', grp='paper')} {n}"

    def build_flow(self, start_frac, col_w):
        seq = self._blocks_from_pack()
        n = len(seq)
        st = int(start_frac * n)
        # do not start on a heading-less float; first block becomes a continuation paragraph
        out = []
        fig_n = 1 + sum(1 for k, _ in seq[:st] if k == "fig")
        tab_n = 1 + sum(1 for k, _ in seq[:st] if k == "tab")
        eq_n = 1 + sum(1 for k, _ in seq[:st] if k == "eq")
        first_after_head = False
        started = False
        for kind, pay in seq[st:]:
            if kind == "h":
                i, k, txt = pay
                lvl = 2 if k is None else 3
                out.append(B.heading(self._sec_title(i, txt, k), self.lang, level=lvl, cls=f"sh{lvl}",
                                     digits=False))
                first_after_head = True
            elif kind == "p":
                if not started and self.role != "first":
                    words = pay.split()
                    cut = self.rng.randint(len(words) // 4, max(len(words) // 4 + 1, len(words) // 2))
                    pay = " ".join(words[cut:])
                    out.append(self._para(pay, cont=True))
                else:
                    out.append(self._para(pay, first=first_after_head))
                first_after_head = False
            elif kind in ("p_lead", "p_where"):
                cls = "bp first" if kind == "p_where" else "bp"
                out.append(B.para(pay, self.lang, cls=cls, hyph=self.hyph(),
                                  extra='data-kwn="1" data-eqlead="1"' if kind == "p_lead" else 'data-eqwhere="1"'))
            elif kind == "eq":
                out.append(self._eq(pay, eq_n)); eq_n += 1
            elif kind == "fig":
                out.append(self._fig(pay, fig_n, col_w * self.rng.uniform(0.8, 0.98))); fig_n += 1
            elif kind == "tab":
                out.append(self._tab(pay, tab_n)); tab_n += 1
            started = True
        return out

    def references(self):
        refs = self.pack.get("references") or []
        out = [B.heading(C.L(self.lang, "References", grp="paper"), self.lang, level=2, cls="sh2 refh")]
        if self.version >= 6:
            # packs often number their references already ("1. Mennell ..."): strip that label and apply ONE
            # house style per journal (never "[1] 1. Mennell")
            style = "bracket" if self.prof == "ieee_like" else self.rng.choices(
                ["bracket", "dot", "none"], weights=[4, 3, 2 if self.prof in ("journal_classic", "springer_like") else 0.5])[0]
            for i, r in enumerate(refs, 1):
                body = _REFLAB.sub("", str(r)).strip()
                txt = {"bracket": f"[{i}] {body}", "dot": f"{i}. {body}", "none": body}[style]
                out.append(B.para(self.num(txt) if self.native_digits else txt, self.lang, cls="ref", cat="reference",
                                  split=True, hyph=self.hyph()))
            return out
        for i, r in enumerate(refs, 1):
            txt = r if r.lstrip().startswith("[") else f"[{i}] {r}"
            out.append(B.para(self.num(txt) if self.native_digits else txt, self.lang, cls="ref", cat="reference",
                              split=True, hyph=self.hyph()))
        return out

    # ------------------------------------------------------------------ page
    def build(self):
        r = self.rng
        self.s = s = self.style()
        W, H = self.W, self.H
        mx, mt, mb = s["margin_x"], s["margin_top"], s["margin_bot"]
        cw = W - 2 * mx
        ncol = 2 if self.double else 1
        col_w = (cw - s["gap"] * (ncol - 1)) / ncol
        body_px = self.pt(s["body_pt"])
        ital = self.italic("serif")
        bw = self.bw(s["body_role"])
        pk = self.pack
        x = self.x
        journal = x.get("journal") or r.choice(C.locale(self.lang).get("journals") or ["Journal"])
        vol = int(x.get("volume") or r.randint(3, 68))
        issue = int(x.get("issue") or r.randint(1, 12))
        year = int(x.get("year") or r.randint(2008, 2026))
        first_page = int(x.get("first_page") or r.randint(2, 300))
        n_pages = r.randint(10, 22)
        rel = 0 if self.role == "first" else (n_pages - 1 if self.role == "last" else r.randint(1, n_pages - 2))
        page_no = first_page + rel
        parts = []
        # ---- running header / footer
        head_h = body_px * 2.2
        cm = "، " if self.lang in ("ar", "ur", "fa") else ", "
        hdr_txt_l = f"{journal}{cm}{self.vol_issue(vol, issue, cm)} ({self.num(year)})"
        short_title = truncate_words(pk.get("title", ""), 8)
        hdr_right = short_title if r.random() < 0.6 else (pk.get("authors") or ["X"])[0] + " " + \
            C.L(self.lang, "et al.", grp="paper")
        show_header = self.prof not in ("arxiv_preprint", "manuscript") and \
            not (self.role == "first" and r.random() < 0.5)
        if self.prof == "manuscript" and r.random() < 0.6:
            parts.append(B.zone(mx, mt - head_h - 4, cw, head_h,
                                B.span_text(self.upper(short_title) if self.typo["caps"] else short_title, self.lang,
                                            "header", cls="rh", tag="div", zorder=-10),
                                style="text-align:end;font-size:0.85em"))
        pn_text = self.num(page_no)
        if show_header:
            left = B.span_text(hdr_txt_l if (page_no % 2 == 0 or r.random() < 0.5) else hdr_right, self.lang,
                               "header", cls="rh", tag="div", zorder=-10)
            inner = left
            if s["pn_pos"] == "header-outer":
                inner = (B.span_text(pn_text, self.lang, "page_number", cls="rhpn", zorder=-9) + left) \
                    if page_no % 2 == 0 else (left + B.span_text(pn_text, self.lang, "page_number", cls="rhpn",
                                                                 zorder=-9))
            parts.append(B.zone(mx, mt - head_h - 4, cw, head_h, f'<div class="rhrow">{inner}</div>',
                                cls="hdrz" + (" ruled" if r.random() < 0.6 else "")))
        if s["pn_pos"] != "header-outer" or not show_header:
            al = "center" if s["pn_pos"] == "bottom-center" else ("end" if page_no % 2 else "start")
            parts.append(B.zone(mx, H - mb + body_px * 0.9, cw, body_px * 1.8,
                                B.span_text(pn_text, self.lang, "page_number", cls="pn", zorder=9999),
                                style=f"text-align:{al}"))
        # arXiv side stamp (preprint, first page)
        if self.prof == "arxiv_preprint" and self.role == "first" and self.typo["caps"]:
            stamp = f"arXiv:{r.randint(1500, 2612)}.{r.randint(10000, 29999)}v{r.randint(1, 3)}  [{r.choice(['cs.CL', 'physics.app-ph', 'math.OC', 'q-bio.QM', 'econ.GN', 'stat.ML'])}]  {r.randint(1, 28)} {r.choice(['Jan', 'Mar', 'May', 'Sep', 'Oct', 'Nov'])} {year}"
            parts.append(f'<div class="zone arx" style="left:{mx * 0.25:.1f}px;top:{H * 0.3:.1f}px">'
                         f'<div data-cat="abandon" data-bid="arx">{words_html(stamp, self.lang)}</div></div>')
        top = mt
        flow = []
        front_id = None
        if self.role == "first":
            fm = []
            fs = r.choice(["classic", "classic", "banner", "panel"]) if self.version >= 2 else "classic"
            self.meta["first_style"] = fs
            if fs in ("banner", "panel"):
                issn = f"ISSN {r.randint(1000, 2999)}-{r.randint(1000, 9999)}"
                oa = r.random() < 0.5
                ban = (f'<div class="jban" style="border-color:{s["accent"]}">'
                       + B.span_text(journal, self.lang, "header", cls="jban-t", style=f"color:{s['accent']}")
                       + B.span_text(f"{issn} · {self.vol_issue(vol, issue, ', ')} · {self.num(year)}",
                                     self.lang, "header", cls="jban-m")
                       + (f'<span class="oa" data-cat="abandon" data-bid="{B.bid("oa")}">Open Access</span>' if oa else "")
                       + '</div>')
                fm.append(ban)
            if self.prof in ("elsevier_like", "journal_classic") and r.random() < 0.6:
                fm.append(B.span_text(f"{journal} {self.num(vol)} ({self.num(year)}) "
                                      f"{self.num(page_no)}–{self.num(page_no + r.randint(8, 25))}",
                                      self.lang, "header", cls="jline"))
            fm.append(B.heading(pk.get("title", ""), self.lang, level=1, cls="ptitle", kwn=False,
                                fit_lines="3"))
            authors = (pk.get("authors") or [])[:6]
            affs = (pk.get("affiliations") or [])[:3]
            if len(affs) >= 2 and authors:
                # superscript markers link every author to an affiliation; the corresponding author gets '*'
                marks = []
                for i, a in enumerate(authors):
                    k = sorted({min(i * len(affs) // len(authors), len(affs) - 1)} |
                               ({r.randrange(len(affs))} if r.random() < 0.2 else set()))
                    marks.append(a + ",".join(str(j + 1) for j in k).translate(SUP) + ("*" if i == 0 else ""))
                fm.append(B.span_text(", ".join(marks), self.lang, "text_block", cls="authors"))
                fm.append("".join(B.span_text(f"{str(j + 1).translate(SUP)} {af}", self.lang, "text_block",
                                              cls="affil") for j, af in enumerate(affs)))
            else:
                fm.append(B.span_text(", ".join(authors), self.lang, "text_block", cls="authors"))
                if affs:
                    fm.append(B.span_text("; ".join(affs), self.lang, "text_block", cls="affil"))
            if r.random() < 0.6 and x.get("received") and x.get("accepted"):
                dl = f"{C.L(self.lang, 'Received', grp='paper')}: {x['received']}; " \
                     f"{C.L(self.lang, 'Accepted', grp='paper')}: {x['accepted']}"
                if x.get("doi") and r.random() < 0.5:
                    dl += f" · DOI: {x['doi']}"
                fm.append(B.span_text(dl, self.lang, "text_block", cls="dates"))
            ab_lab = C.L(self.lang, "Abstract", grp="paper")
            abs_style = r.choice(["box", "indent", "inline"])
            if fs == "panel":
                info = [f"{C.L(self.lang, 'Received', grp='paper')}: {x.get('received', '')}",
                        f"{C.L(self.lang, 'Accepted', grp='paper')}: {x.get('accepted', '')}",
                        f"DOI: {x.get('doi', '')}"]
                kw = (pk.get("keywords") or [])[:6]
                side = ('<div class="ainfo">' + B.heading(C.L(self.lang, "Article", grp="paper"), self.lang, level=3,
                                                         cls="abh", kwn=False)
                        + "".join(B.para(t, self.lang, cls="ai", split=False) for t in info if t.split(": ", 1)[-1])
                        + B.heading(C.L(self.lang, "Keywords", grp="paper"), self.lang, level=3, cls="abh", kwn=False)
                        + "".join(B.para(k, self.lang, cls="ai", split=False) for k in kw) + "</div>")
                main = ('<div class="amain">' + B.heading(ab_lab, self.lang, level=3, cls="abh", kwn=False)
                        + B.para(pk.get("abstract", ""), self.lang, cls="abp", split=False, hyph=self.hyph()) + "</div>")
                fm.append(f'<div class="apanel">{side}{main}</div>')
                abs_style = None
            ab = "" if abs_style is None else f'<div class="abs {abs_style}">' + \
                B.heading(ab_lab, self.lang, level=3, cls="abh", kwn=False) + \
                B.para(pk.get("abstract", ""), self.lang, cls="abp", split=False, hyph=self.hyph()) + \
                B.para(f"{C.L(self.lang, 'Keywords', grp='paper')}: " + "; ".join(pk.get("keywords") or []),
                       self.lang, cls="kw", split=False) + "</div>"
            if ab:
                fm.append(ab)
            parts.append(B.zone(mx, top, cw, 0, "".join(fm), zid="front", auto_h=True, cls="front"))
            front_id = "#front"
            flow = self.build_flow(0.0, col_w)
            # corresponding-author footnote as bottom float in first column
            em = (x.get("emails") or [""])[0] or f"{(pk.get('authors') or ['a'])[0].split()[-1].lower()}@univ.edu"
            if not em.split("@")[0].isascii():   # CJK / Thai names: e-mail local parts are ASCII in print
                em = f"{r.choice(['corr', 'contact', 'office', 'lab', 'research'])}{r.randint(1, 99)}@" + \
                     (em.split("@")[1] if "@" in em and em.split("@")[1].isascii() else "univ.edu")
            mail = f"{C.L(self.lang, 'Corresponding author', grp='paper')}: {(pk.get('authors') or ['A'])[0]}, " \
                   f"{C.L(self.lang, 'E-mail', grp='paper')}: {em}"
            flow.insert(0, f'<div class="fnote" data-place="bottom" data-col="0">' +
                        B.para(mail, self.lang, cls="fn", cat="page_footnote", split=False) + "</div>")
        elif self.role == "body":
            sf = r.uniform(0.05, 0.4)
            flow = self.build_flow(sf, col_w)
        else:  # last page: tail of the paper + references
            sf = max(0.0, 1.0 - r.uniform(0.12, 0.3))
            flow = self.build_flow(sf, col_w)
        # the paper always ends with (acknowledgments +) references; they show up only if space remains
        if self.x.get("acknowledgments") and r.random() < 0.6:
            flow.append(B.heading(C.L(self.lang, "Acknowledgments", grp="paper"), self.lang, level=2, cls="sh2"))
            flow.append(self._para(self.x["acknowledgments"]))
        flow += self.references()
        # spanning float at page top for double-column body pages (figure*/table*)
        span_id = None
        if self.double and self.role == "body" and r.random() < 0.3:
            figs = self.pack.get("figures") or []
            fd = {int(f.get("fig", -1)): f for f in (self.x.get("figure_data") or []) if isinstance(f.get("fig"), int)}
            in_flow = [int(m) for b in flow for m in re.findall(r'data-fi="(\d+)"', b)]
            if figs and in_flow:
                fi = min(in_flow)
                sp = self._fig(dict(figs[fi], **({"_data": fd[fi]} if fi in fd else {})), fi + 1, cw * 0.75)
                flow = [b for b in flow if f'data-fi="{fi}"' not in b]   # never show the same figure twice
                parts.append(B.zone(mx, top, cw, 0, sp, zid="spanfig", auto_h=True, cls="spanz"))
                span_id = "#spanfig"
        body_top_from = front_id or span_id
        bz = B.zone(mx, top, cw, H - mt - mb, "".join(flow), flow=True, cols=ncol, gap=f"{s['gap']:.1f}px",
                    rule=s["rule"], zorder=1, top_from=body_top_from,
                    gap_top=body_px * (1.6 if front_id else 1.0),
                    balance=self.role == "last" and self.rng.random() < 0.6)
        if s.get("lineno"):
            start = 1 if self.role == "first" else r.randint(30, 600)
            bz = bz.replace('class="zone flow', f'data-lineno="{s["lineno"]}" data-lnstart="{start}" '
                                                f'data-lnx="{mx * 0.45:.1f}" class="zone flow', 1)
        parts.append(bz)
        # column-top float in a double-column body page
        css = self.css(body_px, ital, bw)
        return self.spec("".join(parts), css)

    def css(self, body_px, ital, bw):
        s = self.s
        lh = self.lh(s["lh"])
        f_body = self.body_font(s["body_role"])
        f_head = self.body_font(s["head_role"]) if not self.nastaliq else self.fonts.stack("serif")
        f_sans = self.fonts.stack("sans")
        ind = f"{s['indent']}em"
        cap_px = body_px * 0.9
        head_align = "center" if s["head_center"] else "start"
        tb = {"booktabs": "border-top:1.6px solid #000;border-bottom:1.6px solid #000;",
              "grid": "border:1px solid #333;", "light": "border-top:1px solid #555;border-bottom:1px solid #555;"}[s["table"]]
        cell = {"booktabs": "border:none;", "grid": "border:1px solid #444;", "light": "border-bottom:0.5px solid #bbb;"}[s["table"]]
        thb = {"booktabs": "border-bottom:1px solid #000;", "grid": "background:#eee;", "light": "border-bottom:1px solid #555;"}[s["table"]]
        return f"""
#page{{font-family:{f_body};font-size:{body_px:.2f}px;line-height:{lh};color:{s['ink']};--bw:{bw};}}
.bp{{text-align:{s['justify']};text-indent:{ind};margin-bottom:{s['parsep']}em;}}
.bp.first{{text-indent:0;}}
.sh2{{font-family:{f_head};font-size:{body_px * 1.12:.2f}px;font-weight:{bw};margin:{0.9}em 0 0.45em;text-align:{head_align};color:{s['accent']};line-height:{self.lh(1.25)};}}
.sh3{{font-family:{f_head};font-size:{body_px * 1.02:.2f}px;font-weight:{bw};font-style:{ital if s['head_num'] != 'roman' else 'italic' if ital == 'italic' else 'normal'};margin:0.7em 0 0.35em;line-height:{self.lh(1.25)};}}
.col>.sh2:first-child,.col>.sh3:first-child{{margin-top:0;}}
.rhrow{{display:flex;justify-content:space-between;align-items:flex-end;height:100%;font-size:{body_px * 0.82:.2f}px;font-style:{ital};gap:1em;line-height:1.25;}}
.hdrz.ruled .rhrow{{border-bottom:0.7px solid #333;padding-bottom:2px;}}
.rh{{white-space:nowrap;overflow:hidden;text-overflow:clip;}}
.pn,.rhpn{{font-size:{body_px * 0.9:.2f}px;}}
.ptitle{{font-family:{f_head};font-size:{body_px * self.rng.uniform(1.6, 2.1):.2f}px;line-height:{self.lh(1.2)};font-weight:{bw};text-align:{'center' if self.rng.random() < 0.7 else 'start'};margin:0.2em 0 0.5em;color:{s['accent']};}}
.authors{{text-align:center;font-size:{body_px * 1.05:.2f}px;margin-bottom:0.3em;}}
.affil{{text-align:center;font-size:{body_px * 0.85:.2f}px;font-style:{ital};margin-bottom:0.4em;}}
.dates,.jline{{text-align:center;font-size:{body_px * 0.8:.2f}px;margin-bottom:0.4em;color:#333;}}
.abs{{margin:0.6em {'1.5em' if not self.double else '0'};font-size:{body_px * 0.92:.2f}px;}}
.abs.box{{border-top:1px solid #000;border-bottom:1px solid #000;padding:0.5em 0;}}
.abs.inline .abh{{display:inline;}}
.abh{{font-family:{f_head};font-weight:{bw};font-size:{body_px:.2f}px;margin:0 0 0.2em;}}
.abp{{text-align:justify;}}
.kw{{margin-top:0.4em;font-style:{ital};}}
.jban{{display:flex;justify-content:space-between;align-items:baseline;border-top:4px solid;border-bottom:1px solid #999;padding:0.2em 0;margin-bottom:0.8em;gap:1em;}}
.jban-t{{font-family:{f_head};font-weight:{bw};font-size:{body_px * 1.25:.1f}px;}}
.jban-m{{font-size:{body_px * 0.8:.1f}px;color:#444;}}
.oa{{font-family:{f_sans};font-size:{body_px * 0.75:.1f}px;color:#fff;background:#f68212;padding:0.1em 0.5em;border-radius:3px;}}
.apanel{{display:flex;gap:1.2em;border-top:1px solid #000;border-bottom:1px solid #000;padding:0.5em 0;margin:0.6em 0;font-size:{body_px * 0.9:.1f}px;}}
.ainfo{{flex:0 0 30%;border-inline-end:0.6px solid #888;padding-inline-end:0.8em;}}
.ai{{margin:0.1em 0;line-height:1.3;}}
.amain{{flex:1;}}
.fnote{{border-top:0.6px solid #000;width:100%;padding-top:3px;margin-top:6px;}}
.fn{{font-size:{body_px * 0.78:.2f}px;line-height:1.25;}}
.eqrow{{display:flex;align-items:center;justify-content:center;margin:0.5em 0;position:relative;}}
.eqrow .eq{{flex:0 1 auto;max-width:100%;overflow:visible;}}
.eqrow .eqno{{position:absolute;inset-inline-end:0;}}
.katex{{direction:ltr;unicode-bidi:isolate;}}
.m .katex{{font-size:1.0em;}}
.fig{{margin:0.6em 0 0.8em;display:flex;flex-direction:column;align-items:center;}}
.fig .figimg{{max-width:100%;}}
.cap{{font-size:{cap_px:.2f}px;line-height:{self.lh(1.22)};text-align:{'center' if s['cap_center'] else 'justify'};margin-top:0.35em;width:100%;}}
.tblwrap{{margin:0.6em 0 0.8em;}}
.tcap{{margin:0 0 0.35em;}}
table.tbl{{border-collapse:collapse;margin:0 auto;font-size:{body_px * 0.86:.2f}px;line-height:1.25;{tb}}}
table.tbl td,table.tbl th{{padding:2px 6px;{cell}text-align:center;}}
table.tbl tr:first-child th{{{thb}font-weight:{bw};}}
.ref{{font-size:{body_px * 0.86:.2f}px;padding-inline-start:2em;text-indent:-2em;text-align:start;margin-bottom:0.15em;line-height:{self.lh(1.22)};}}
.refh{{margin-top:0.6em;}}
.arx{{transform:rotate(-90deg);transform-origin:left top;font-family:{self.fonts.stack('serif')};font-size:{body_px * 1.6:.1f}px;color:#777;white-space:nowrap;}}
"""


def make(rng, lang, double, version=0, role=None):
    return PaperPage(rng, lang, double, version, role).build()

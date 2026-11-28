"""Colorful textbook pages: unit/lesson banners, objectives, callout boxes, activities, examples, exercises."""
from .. import imagepool as A
from .. import blocks as B
from .. import corpus as C
from ..doc import Doc
from ..geometry import IN
import re

from ..textkit import _TO_LATIN, esc, words_html

SUBJ_TOPIC = [("scien|wissen|ciên|cienc|naturw|विज्ञान|বিজ্ঞান|سائنس|علوم|наук|ipa|sains", "science"),
              ("geo|भूगोल|ভূগোল|جغراف|географ", "nature"), ("bio|जीव|জীব|حیات|احياء|биолог", "nature"),
              ("hist|इतिहास|ইতিহাস|تاریخ|تاريخ|истор|sejarah", "culture"),
              ("civ|नागरिक|পৌর|শহর|مدنی|وطن|обществ|pkn|citoy|cidad", "politics"),
              ("env|पर्यावरण|পরিবেশ|ماحول|بيئ|окруж|lingkungan|umwelt|ambient|environ", "nature"),
              ("phys|भौतिक|পদার্থ|طبیعیات|فيزياء|физ|fisika|físic", "science"),
              ("chem|रसायन|রসায়ন|کیمیا|كيمياء|хим|kimia|quím", "science")]


def _strip_num(h):
    return re.sub(r"^\s*[\d০-৯०-९٠-٩۰-۹]+[\.\)]\s*", "", str(h)).strip()

THEMES = [("#0077b6", "#caf0f8", "#ff9f1c"), ("#2a9d8f", "#e9f5f2", "#e76f51"), ("#6a4c93", "#efe7f7", "#ffca3a"),
          ("#d62828", "#fdecea", "#003049"), ("#1b4332", "#e3f2e9", "#f4a261"), ("#3a0ca3", "#e9e5fb", "#f72585"),
          ("#ef8354", "#fff1e6", "#2d3142"), ("#007f5f", "#e6f4ef", "#ffbe0b")]


class TextbookPage(Doc):
    def __init__(self, rng, lang, version=0):
        super().__init__("textbook", lang, rng, version)
        pool = C.packs(lang, "lesson")
        self.pack = rng.choice(pool) if pool else None
        subj = " ".join(str((self.pack or {}).get(k, "")) for k in ("unit_title", "lesson_title")).lower()
        self.topic = next((t for pat, t in SUBJ_TOPIC if re.search(pat, subj)), "education")
        if version >= 3:
            self.role = rng.choices(["opener", "body", "exercise", "review"], weights=[0.28, 0.36, 0.18, 0.18])[0]
        else:
            self.role = rng.choice(["opener", "body", "exercise"])
        self.meta.update(page_role=self.role, layout="other_layout", special_issue=["colorful_backgroud"])

    def box(self, kind, title, inner_html, th):
        c1, c2, c3 = th
        style = self.rng.choice(["side", "full", "tab"])
        tcol = c3 if kind in ("dyk", "act") else c1
        head = B.heading(title, self.lang, level=3, cls="bxh", kwn=False, style=f"color:{'#fff' if style == 'full' else tcol}")
        if style == "full":
            head = f'<div class="bxhead" style="background:{tcol}">{head}</div>'
        cls = f"tbox {style}"
        return f'<div class="{cls}" style="--bc:{tcol};background:{c2}">{head}<div class="bxb">{inner_html}</div></div>'

    def build(self):
        r = self.rng
        W, H = self.W, self.H
        th = self.th = r.choice(THEMES)
        pk = self.pack or {}
        cp = C.corpus(self.lang)
        body_pt = r.uniform(10.5, 12.5)
        body_px = self.pt(body_pt)
        m = r.uniform(0.55, 0.8) * IN
        self.m0 = m
        cw = W - 2 * m
        two = (W > 9 * IN or r.random() < 0.25) and self.role != "exercise"   # worksheets: one column
        ncol = 2 if two else 1
        zones = []
        top = m
        # page tab / folio
        pn = self.num(r.randint(5, 180))
        side = "right" if (r.random() < 0.5) != self.rtl else "left"
        zones.append(f'<div class="zone" style="{side}:0;top:{H - m * 1.1:.1f}px;width:{m * 1.6:.1f}px;height:{body_px * 2.2:.1f}px;'
                     f'background:{th[0]};border-radius:{"0 99px 99px 0" if side == "left" else "99px 0 0 99px"};'
                     f'display:flex;align-items:center;justify-content:center">'
                     f'{B.span_text(pn, self.lang, "page_number", cls="tpn")}</div>')
        flow = []
        top_from = None
        big = [p for p in (pk.get("_photos") or []) if (p.get("w") or 0) >= W * self.page["dpi"] / 96.0 / 2.0]
        self.margin_col = self.version >= 3 and self.role in ("opener", "body") and r.random() < 0.35 and W < 9 * IN
        if self.role == "opener" and self.version >= 3 and big and r.random() < 0.45:
            # full-bleed photo opener: the unit / lesson title sits on a colour strip across the photo
            ph = big[0]
            pk = dict(pk, _photos=[x for x in pk.get("_photos") or [] if x is not ph])
            band_h = min(H * r.uniform(0.3, 0.4), W * ph["h"] / ph["w"])
            g = B.bid("g")
            zones.append(f'<div class="zone" style="left:0;top:0;width:{W:.1f}px;height:{band_h:.1f}px">'
                         f'<div class="tbleed" data-cat="figure" data-bid="{B.bid("f")}" data-group="{g}" '
                         f'data-nw="{ph["w"]}" data-nh="{ph["h"]}" style="height:100%;'
                         f'background-image:url(\'file://{esc(ph["path"])}\')"></div></div>')
            unit = f"{C.L(self.lang, 'Unit', grp='textbook')} {self.num(r.randint(1, 9))}"
            strip = (B.span_text(unit, self.lang, "title", cls="unit", extra='data-sub="1"') +
                     B.heading(pk.get("unit_title", "") or cp.wiki_article(r)["title"], self.lang, level=1,
                               cls="utitle", kwn=False, fit_lines="2"))
            zones.append(B.zone(0, band_h - body_px * 4.2, W, body_px * 4.2,
                                f'<div class="ustrip" style="background:{th[0]}e6">{strip}</div>'))
            top = band_h + body_px
            les = f"{C.L(self.lang, 'Lesson', grp='textbook')} {self.num(r.randint(1, 6))}: {pk.get('lesson_title', '')}"
            zones.append(B.zone(m, top, cw, 0, B.heading(les, self.lang, level=2, cls="ltitle", kwn=False,
                                                         style=f"color:{th[0]}"), zid="tbhead", auto_h=True))
            top_from = "#tbhead"
            if pk.get("intro"):
                flow.append(B.para(pk["intro"], self.lang, cls="tp first", hyph=self.hyph()))
            if pk.get("objectives"):
                items = "".join(f'<div class="li">{B.span_text("✓ " + o, self.lang, "text_block", cls="lit")}</div>'
                                for o in pk["objectives"][:4])
                flow.append(self.box("obj", C.L(self.lang, "Learning objectives", grp="textbook"), items, th))
        elif self.role == "opener":
            unit = f"{C.L(self.lang, 'Unit', grp='textbook')} {self.num(r.randint(1, 9))}"
            band_h = H * r.uniform(0.11, 0.16)
            zones.append(f'<div class="zone" style="left:0;top:0;width:{W:.1f}px;height:{band_h:.1f}px;background:{th[0]}"></div>')
            unit_html = B.span_text(unit, self.lang, "title", cls="unit", extra='data-sub="1"')
            ut = pk.get("unit_title", "") or cp.wiki_article(r)["title"]
            ut_html = B.heading(ut, self.lang, level=1, cls="utitle", kwn=False, fit_lines="2")
            zones.append(B.zone(m, band_h * 0.18, cw, band_h * 0.75, f'<div class="unitrow">{unit_html}{ut_html}</div>'))
            top = band_h + body_px
            les = f"{C.L(self.lang, 'Lesson', grp='textbook')} {self.num(r.randint(1, 6))}: {pk.get('lesson_title', '')}"
            intro = [B.heading(les, self.lang, level=2, cls="ltitle", kwn=False, style=f"color:{th[0]}")]
            if pk.get("objectives"):
                items = "".join(f'<div class="li">{B.span_text("✓ " + o, self.lang, "text_block", cls="lit")}</div>'
                                for o in pk["objectives"][:4])
                intro.append(self.box("obj", C.L(self.lang, "Learning objectives", grp="textbook"), items, th))
            zones.append(B.zone(m, top, cw, 0, "".join(intro), zid="tbhead", auto_h=True))
            top_from = "#tbhead"
            if pk.get("intro"):
                flow.append(B.para(pk["intro"], self.lang, cls="tp first", hyph=self.hyph()))
        elif self.role == "review" and self.version >= 3:
            return self.build_review(pk, th, m, cw, body_px, zones)
        else:
            hs = r.choice(["rule", "rule", "band", "tab"]) if self.version >= 3 else "rule"
            if hs == "band":
                zones.append(f'<div class="zone" style="left:0;top:0;width:{W:.1f}px;height:{m * 0.85:.1f}px;'
                             f'background:{th[0]}"></div>')
                zones.append(B.zone(m, m * 0.18, cw, m * 0.6, B.span_text(pk.get("unit_title", ""), self.lang, "header",
                                                                        cls="trht band")))
                top = m * 1.1
            elif hs == "tab":
                zones.append(B.zone(m, m * 0.35, cw, body_px * 2.4,
                                    f'<div class="ttab"><span class="ttabn" style="background:{th[0]}">'
                                    f'{words_html(self.num(r.randint(1, 12)), self.lang)}</span>'
                                    f'{B.span_text(pk.get("unit_title", ""), self.lang, "header", cls="trht")}</div>'))
                top = m * 0.35 + body_px * 3.2
            else:
                zones.append(B.zone(m, m * 0.5, cw, body_px * 1.8,
                                    f'<div class="trh" style="border-color:{th[0]}">'
                                    f'{B.span_text(pk.get("unit_title", ""), self.lang, "header", cls="trht")}</div>'))
        secs = pk.get("sections") or [{"heading": s["heading"], "paragraphs": s["paras"][:2]}
                                      for s in cp.wiki_article(r, 2000)["sections"][:3]]
        side, side_terms = [], []
        if self.role != "exercise":
            for si, sec in enumerate(secs):
                flow.append(B.heading(f"{self.num(si + 1)}. {_strip_num(sec.get('heading', ''))}", self.lang, level=2, cls="tsh",
                                      style=f"color:{th[0]}"))
                for p in sec.get("paragraphs") or []:
                    flow.append(B.para(p, self.lang, cls="tp", hyph=self.hyph()))
                photos = list(pk.get("_photos") or [])
                if si < len(photos) and si < 2:
                    ph = photos[si]
                    flow.append(B.figure(B.img(ph["path"], f"width:100%;max-width:{self.img_cap(ph):.0f}px;margin:0 auto;"
                                                           f"max-height:{H * 0.22:.0f}px;object-fit:contain;"
                                                           f"border-radius:{r.choice([0, 8, 16])}px;display:block"),
                                         ph.get("caption", ""), self.lang, cls="tfig", capcls="tcap"))
                elif self.version >= 6 and si < 2 and not getattr(self, "_fig_done", 0) >= 1 + (si > 0):
                    # no photo that shows this lesson: a drawn figure built from the lesson itself
                    fig = self.timeline_fig(secs, cw) if si == 1 or r.random() < 0.35 else None
                    fig = fig or self.concept_map(pk, secs, cw)
                    if fig:
                        flow.append(fig)
                        self._fig_done = getattr(self, "_fig_done", 0) + 1
                elif si == 0 and sec.get("key_terms") and 2 <= self.version < 4 and r.random() < 0.5:
                    # key-terms table instead of an unrelated photo
                    terms = [t for s2 in secs for t in (s2.get("key_terms") or [])][:6]
                    sents = [p for s2 in secs for p in (s2.get("paragraphs") or [])]
                    rows = []
                    for t in terms:
                        d = next((x for x in sents if t.lower() in x.lower()), "")
                        d = re.split(r"(?<=[.!?।۔؟])\s+", d)[0][:110] if d else ""
                        if d:
                            rows.append([t, d])
                    if len(rows) >= 3:
                        flow.append(B.table([C.L(self.lang, "Key words", grp="textbook"),
                                             C.L(self.lang, "Note", grp="textbook")], rows, self.lang, cls="kttbl",
                                            num_align=False))
                if sec.get("key_terms") and self.margin_col:
                    side_terms.extend(t for t in sec["key_terms"][:5] if t not in side_terms)
                elif sec.get("key_terms"):
                    kt = " · ".join(sec["key_terms"])
                    flow.append(f'<div class="kt" style="border-color:{th[2]}">' +
                                B.span_text(f"{C.L(self.lang, 'Key words', grp='textbook')}: {kt}", self.lang,
                                            "text_block", cls="ktt") + "</div>")
            if pk.get("did_you_know"):
                (side if self.margin_col else flow).append(
                    self.box("dyk", C.L(self.lang, "Did you know?", grp="textbook"),
                             B.para(pk["did_you_know"], self.lang, cls="tp", split=False), th))
            if pk.get("example"):
                ex = pk["example"]
                inner = B.para(str(ex.get("problem", "")), self.lang, cls="tp", split=False) + \
                    B.para(f"{C.L(self.lang, 'Solution', grp='textbook')}: {ex.get('solution', '')}", self.lang, cls="tp",
                           split=False)
                flow.append(self.box("ex", C.L(self.lang, "Example", grp="textbook"), inner, th))
            if pk.get("activity"):
                act = pk["activity"]
                inner = "".join(B.para(f"{self.num(i + 1)}. {s}", self.lang, cls="tp", split=False)
                                for i, s in enumerate(act.get("steps") or []))
                flow.append(self.box("act", f"{C.L(self.lang, 'Activity', grp='textbook')}: {act.get('title', '')}",
                                     inner, th))
        # exercises of THIS lesson only (mixing other lessons made pages topic-incoherent); on exercise pages
        # every question gets ruled answer lines that share the leftover space (worksheet look)
        ex_items = list(pk.get("exercises") or [])
        lines_after = bool(ex_items) and (self.role == "exercise" or r.random() < 0.35)
        pitch = float(round(body_px * 1.6))
        if ex_items:
            flow.append(B.heading(C.L(self.lang, "Exercises", grp="textbook"), self.lang, level=2, cls="tsh exh",
                                  style=f"background:{th[0]};color:#fff"))
            for i, q in enumerate(ex_items):
                flow.append(B.para(f"{self.num(i + 1)}. {_strip_num(q)}", self.lang, cls="tq", split=False))
                if lines_after:
                    flow.append(f'<div class="wl" data-grow="{pitch:.2f}" style="height:{pitch * 2:.1f}px"></div>')
        if side_terms:   # one key-words box in the margin (not one per section)
            side.insert(0, self.box("kw", C.L(self.lang, "Key words", grp="textbook"),
                                    "".join(B.para("• " + t, self.lang, cls="sbi", split=False) for t in side_terms[:10]),
                                    th))
        main_w = cw
        if self.margin_col and side:
            side_w = cw * 0.29
            main_w = cw - side_w - 0.22 * IN
            sx = m if self.rtl else m + main_w + 0.22 * IN
            zones.append(B.zone(sx, top, side_w, H - top - m * 1.4, "".join(side), flow=True, cols=1, zorder=2,
                                top_from=top_from, gap_top=body_px * 0.8, minhead=1))
            if self.rtl:
                m = m + side_w + 0.22 * IN
            ncol = 1
            self.meta["layout"] = "1andmore_column"
        bz = B.zone(m, top, main_w, H - top - m * 1.4 if not self.rtl else H - top - self.m0 * 1.4, "".join(flow),
                    flow=True, cols=ncol, gap=f"{0.3 * IN:.1f}px", zorder=1, top_from=top_from, gap_top=body_px * 0.8,
                    minhead=1, balance=not lines_after)
        if lines_after:
            bz = bz.replace('class="zone flow', 'data-growall="1" class="zone flow', 1)
        zones.append(bz)
        page_bg = r.choice(["#ffffff", "#ffffff", th[1], "#fffdf5"])
        return self.spec("".join(zones), self.css(body_px, th), page_style=f"background:{page_bg};")

    # ------------------------------------------------------------------ drawn figures (v6)
    def _svg_text(self, x, y, s, size, fill, weight=400, anchor="middle"):
        d = ' direction="rtl"' if self.rtl else ""
        return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size:.1f}" font-weight="{weight}" fill="{fill}" '
                f'text-anchor="{anchor}" dominant-baseline="middle"{d}>{esc(s)}</text>')

    def concept_map(self, pk, secs, cw):
        """Lesson title in the centre, its key terms around it (a classic textbook concept map)."""
        r = self.rng
        terms = []
        for s2 in secs:
            for t in s2.get("key_terms") or []:
                if t not in terms and len(t) <= 28:
                    terms.append(t)
        terms = terms[:6]
        if len(terms) < 3:
            return None
        th = self.th
        w = min(cw * 0.96, 760.0)
        h = w * 0.56
        fs = self.pt(9.5)
        cx, cy = w / 2, h / 2
        title = str(pk.get("lesson_title") or pk.get("unit_title") or "")
        title = title if len(title) <= 34 else title[:33] + "…"
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}" '
               f'style="font-family:{esc(self.fonts.stack("sans"))};display:block;max-width:100%;height:auto;margin:0 auto">']
        n = len(terms)
        pos = []
        for i in range(n):
            a = -1.5708 + 2 * 3.14159 * i / n + r.uniform(-0.12, 0.12)
            pos.append((cx + w * 0.36 * __import__("math").cos(a), cy + h * 0.36 * __import__("math").sin(a)))
        for x, y in pos:
            out.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{th[0]}" stroke-width="2"/>')
        tw = max(fs * 0.6 * len(title), w * 0.3)
        out.append(f'<rect x="{cx - tw / 2 - 10:.1f}" y="{cy - fs * 1.4:.1f}" width="{tw + 20:.1f}" height="{fs * 2.8:.1f}" '
                   f'rx="{fs:.1f}" fill="{th[0]}"/>')
        out.append(self._svg_text(cx, cy, title, fs * 1.05, "#fff", 700))
        for (x, y), t in zip(pos, terms):
            bw_ = max(fs * 0.62 * len(t) + 18, w * 0.16)
            out.append(f'<rect x="{x - bw_ / 2:.1f}" y="{y - fs * 1.15:.1f}" width="{bw_:.1f}" height="{fs * 2.3:.1f}" '
                       f'rx="{fs * 0.5:.1f}" fill="{th[1]}" stroke="{th[0]}" stroke-width="1.5"/>')
            out.append(self._svg_text(x, y, t, fs, "#222", 600))
        out.append("</svg>")
        self.fig_no = getattr(self, "fig_no", r.randint(1, 6)) + 1
        cap = f"{C.L(self.lang, 'Figure', 'Fig.', grp='paper')} {self.num(self.fig_no)}: " \
              f"{C.L(self.lang, 'Concept map', grp='textbook')} — {title}"
        return B.figure("".join(out), cap, self.lang, cls="tfig", capcls="tcap", shrink=True)

    def timeline_fig(self, secs, cw):
        """Years mentioned in the lesson on a time line (history / civics lessons)."""
        r = self.rng
        evs = {}
        for s2 in secs:
            for p in s2.get("paragraphs") or []:
                txt = "".join(_TO_LATIN.get(c, c) for c in str(p))
                for m in re.finditer(r"(?<!\d)(1[0-9]{3}|20[0-2][0-9])(?!\d)", txt):
                    y = int(m.group(1))
                    if 500 <= y <= 2025 and y not in evs:
                        words = re.findall(r"[^\s,.;:()«»“”]+", str(p)[m.end():m.end() + 80])[:3]
                        if words:
                            evs[y] = " ".join(words)
        if len(evs) < 3:
            return None
        ys = sorted(evs)[:6]
        th = self.th
        w = min(cw * 0.96, 760.0)
        h = w * 0.3
        fs = self.pt(8.8)
        x0, x1 = w * 0.06, w * 0.94
        ymid = h * 0.45
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}" '
               f'style="font-family:{esc(self.fonts.stack("sans"))};display:block;max-width:100%;height:auto;margin:0 auto">',
               f'<line x1="{x0:.1f}" y1="{ymid:.1f}" x2="{x1:.1f}" y2="{ymid:.1f}" stroke="{th[0]}" stroke-width="4"/>']
        for i, y in enumerate(ys):
            f = i / max(1, len(ys) - 1)
            x = x1 - f * (x1 - x0) if self.rtl else x0 + f * (x1 - x0)
            up = i % 2 == 0
            out.append(f'<circle cx="{x:.1f}" cy="{ymid:.1f}" r="{fs * 0.55:.1f}" fill="{th[2]}" stroke="{th[0]}" stroke-width="2"/>')
            out.append(self._svg_text(x, ymid + (-1 if up else 1) * fs * 1.6, self.num(str(y)), fs * 1.1, th[0], 800))
            lab = evs[y] if len(evs[y]) <= 22 else evs[y][:21] + "…"
            out.append(self._svg_text(x, ymid + (-1 if up else 1) * fs * 3.0, lab, fs * 0.9, "#333", 400))
        out.append("</svg>")
        self.fig_no = getattr(self, "fig_no", r.randint(1, 6)) + 1
        cap = f"{C.L(self.lang, 'Figure', 'Fig.', grp='paper')} {self.num(self.fig_no)}"
        return B.figure("".join(out), cap, self.lang, cls="tfig", capcls="tcap", shrink=True)

    def build_review(self, pk, th, m, cw, body_px, zones):
        """Chapter review page: key points, key-word table, fill-in-the-blanks, true/false, review questions."""
        r = self.rng
        W, H = self.W, self.H
        secs = pk.get("sections") or []
        sent_split = lambda t: [x for x in re.split(r"(?<=[.!?।۔؟])\s+", str(t)) if len(x) > 25]  # noqa: E731
        zones.append(B.zone(m, m * 0.5, cw, body_px * 1.8,
                            f'<div class="trh" style="border-color:{th[0]}">'
                            f'{B.span_text(pk.get("unit_title", ""), self.lang, "header", cls="trht")}</div>'))
        head = (B.heading(C.L(self.lang, "Chapter review", grp="textbook"), self.lang, level=1, cls="tsh exh",
                          kwn=False, style=f"background:{th[0]};color:#fff;font-size:{body_px * 1.6:.1f}px")
                + B.heading(pk.get("lesson_title", ""), self.lang, level=2, cls="ltitle", kwn=False,
                            style=f"color:{th[0]}"))
        zones.append(B.zone(m, m * 0.5 + body_px * 2.6, cw, 0, head, zid="rvhead", auto_h=True))
        flow = []
        pts = [sent_split((sec.get("paragraphs") or [""])[0])[:1] for sec in secs]
        pts = [x[0] for x in pts if x][:5]
        if self.version >= 6:
            self.th = th
            cm = self.concept_map(pk, secs, cw)
            if cm:
                flow.append(cm)
        if pts:
            flow.append(self.box("sum", C.L(self.lang, "Key points", grp="textbook"),
                                 "".join(B.para("• " + x, self.lang, cls="rvl", split=False) for x in pts), th))
        terms = [t for sec in secs for t in (sec.get("key_terms") or [])]
        sents = [x for sec in secs for p in (sec.get("paragraphs") or []) for x in sent_split(p)]
        blanks = []
        for t in terms:
            # the term must stand as a whole word: no letter / combining mark directly before or after it
            pat = re.compile(r"(?<![\w\u0900-\u0DFF\u0600-\u06FF])" + re.escape(t) + r"(?![\w\u0900-\u0DFF\u0600-\u06FF])")
            s_ = next((x for x in sents if pat.search(x) and x not in [b[1] for b in blanks]), None)
            if s_:
                blanks.append((t, pat.sub("__________", s_, count=1)))
        if len(blanks) >= 2:
            flow.append(B.heading(C.L(self.lang, "Fill in the blanks", grp="textbook"), self.lang, level=3, cls="tsh",
                                  style=f"color:{th[0]}"))
            for i, (t, s_) in enumerate(blanks[:4]):
                flow.append(B.para(f"{self.num(i + 1)}. " + s_, self.lang, cls="tq", split=False))
        # true / false: first sentences of paragraphs (self-contained, no dangling 'therefore' / 'this method')
        firsts = [sent_split(p)[0] for sec in secs for p in (sec.get("paragraphs") or [])[1:] if sent_split(p)]
        rest = [x for x in firsts if not any(x.replace(b[0], "__________", 1) == b[1] for b in blanks)]
        r.shuffle(rest)
        if len(rest) >= 3:
            flow.append(B.heading(C.L(self.lang, "True or false", grp="textbook"), self.lang, level=3, cls="tsh",
                                  style=f"color:{th[0]}"))
            for i, s_ in enumerate(rest[:3]):
                flow.append(f'<div class="tf">{B.para(f"{self.num(i + 1)}. {s_}", self.lang, cls="tq", split=False)}'
                            f'<span class="tfbox">(&nbsp;&nbsp;&nbsp;&nbsp;)</span></div>')
        ex = list(pk.get("exercises") or [])
        if ex:
            pitch = float(round(body_px * 1.6))
            flow.append(B.heading(C.L(self.lang, "Review questions", grp="textbook"), self.lang, level=3, cls="tsh",
                                  style=f"color:{th[0]}"))
            for i, q in enumerate(ex[:6]):
                flow.append(B.para(f"{self.num(i + 1)}. {_strip_num(q)}", self.lang, cls="tq", split=False))
                flow.append(f'<div class="wl" data-grow="{pitch:.2f}" style="height:{pitch:.1f}px"></div>')
        bz = B.zone(m, m, cw, H - m * 2.4, "".join(flow), flow=True, cols=1, zorder=1, top_from="#rvhead",
                    gap_top=body_px * 0.8, minhead=1)
        zones.append(bz.replace('class="zone flow', 'data-growall="1" class="zone flow', 1))
        self.meta["page_role"] = "review"
        page_bg = r.choice(["#ffffff", "#ffffff", th[1], "#fffdf5"])
        return self.spec("".join(zones), self.css(body_px, th), page_style=f"background:{page_bg};")

    def css(self, body_px, th):
        r = self.rng
        f_body = self.body_font(r.choice(["sans", "sans", "serif"]))
        f_head = self.fonts.stack(r.choice(["display", "sans"])) if not self.nastaliq else self.fonts.stack("nastaliq")
        bw = self.bw("sans")
        lh = self.lh(r.uniform(1.35, 1.6))
        return f"""
#page{{font-family:{f_body};font-size:{body_px:.2f}px;line-height:{lh};color:#222;--bw:{bw};}}
.tp{{text-align:start;margin:0 0 0.55em;}}
.unitrow{{display:flex;align-items:center;gap:0.8em;height:100%;}}
.unit{{background:#fff;color:{th[0]};font-family:{f_head};font-weight:800;padding:0.15em 0.6em;border-radius:6px;font-size:{body_px * 1.5:.1f}px;white-space:nowrap;}}
.utitle{{color:#fff;font-family:{f_head};font-size:{body_px * 2.3:.1f}px;line-height:{self.lh(1.1)};margin:0;}}
.ltitle{{font-family:{f_head};font-size:{body_px * 1.6:.1f}px;margin:0 0 0.5em;line-height:{self.lh(1.2)};}}
.tsh{{font-family:{f_head};font-size:{body_px * 1.3:.1f}px;margin:0.8em 0 0.35em;line-height:{self.lh(1.2)};}}
.tsh.exh{{padding:0.15em 0.5em;border-radius:4px;display:inline-block;}}
.tbox{{margin:0.6em 0;border-radius:{r.choice([0, 6, 12])}px;overflow:hidden;}}
.tbox.side{{border-inline-start:6px solid var(--bc);}}
.tbox.tab{{border:2px solid var(--bc);}}
.bxhead{{padding:0.2em 0.6em;}}
.bxh{{font-family:{f_head};font-size:{body_px * 1.1:.1f}px;margin:0;padding:0.3em 0.6em 0;}}
.bxhead .bxh{{padding:0;}}
.bxb{{padding:0.35em 0.7em 0.5em;}}
.li{{margin:0.15em 0;}}
.tfig{{margin:0.5em 0;}} .tcap{{font-size:{body_px * 0.85:.1f}px;color:#555;text-align:center;margin-top:0.25em;}}
table.kttbl{{border-collapse:collapse;width:100%;margin:0.5em 0;font-size:{body_px * 0.92:.1f}px;}}
table.kttbl th{{background:{th[0]};color:#fff;padding:0.25em 0.5em;text-align:start;}}
table.kttbl td{{border-bottom:1px solid #ccc;padding:0.25em 0.5em;vertical-align:top;}}
table.kttbl td:first-child{{font-weight:700;color:{th[0]};white-space:nowrap;}}
.kt{{border-inline-start:5px solid;padding:0.2em 0.6em;margin:0.4em 0;background:#fafafa;font-weight:600;}}
.tq{{margin:0.25em 0;padding-inline-start:0.4em;}}
.wl{{background-image:linear-gradient(to bottom,transparent calc(100% - 1.3px),#8a8a8a calc(100% - 1.3px));background-size:100% {round(body_px * 1.6):.0f}px;}}
.tbleed{{width:100%;background-size:cover;background-position:center 40%;}}
.ustrip{{height:100%;display:flex;align-items:center;gap:0.8em;padding:0 {self.m0:.0f}px;}}
.ttab{{display:flex;align-items:center;gap:0.6em;border-bottom:2px solid #ddd;height:100%;}}
.ttabn{{color:#fff;font-weight:800;border-radius:50%;min-width:1.9em;height:1.9em;display:inline-flex;align-items:center;justify-content:center;}}
.trht.band{{color:#fff;font-weight:700;font-size:{body_px * 1.05:.1f}px;}}
.sbi{{margin:0.1em 0;}}
.rvsum li,.rvl{{margin:0.2em 0;}}
.tf{{display:flex;justify-content:space-between;gap:1em;margin:0.25em 0;}}
.trh{{border-bottom:2px solid;font-size:{body_px * 0.85:.1f}px;color:#555;}}
.tpn{{color:#fff;font-weight:800;font-size:{body_px:.1f}px;}}
.katex{{direction:ltr;}}
"""


def make(rng, lang, version=0):
    return TextbookPage(rng, lang, version).build()

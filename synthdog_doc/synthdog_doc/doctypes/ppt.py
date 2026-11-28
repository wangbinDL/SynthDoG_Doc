"""Slide pages (PPT2PDF): deck theme x typed slide layouts from LLM-generated decks."""
import random

from .. import imagepool as A
from .. import blocks as B
from .. import corpus as C
from ..charts import Chart
from ..doc import Doc
from ..textkit import esc, words_html

THEMES = ["office", "banner", "dark", "sidebar", "gradient", "academic", "minimal", "corporate"]
PALETTES = [("#1F4E79", "#2E75B6", "#DEEBF7"), ("#7B2C2C", "#C0504D", "#F2DCDB"), ("#1E5631", "#4E9A06", "#E2F0D9"),
            ("#3F3F3F", "#ED7D31", "#FBE5D6"), ("#203864", "#FFC000", "#FFF2CC"), ("#5B2C6F", "#8E44AD", "#EBDEF0"),
            ("#0B5563", "#00A6A6", "#D9F2F2"), ("#002060", "#C00000", "#F2F2F2"), ("#262626", "#00B0F0", "#DAEEF3")]
BULLETS = ["•", "▪", "■", "–", "➢", "✓", "◆", "○", "►"]


FIT1 = 'data-fit-lines="1" data-fit-min="0.45"'   # big KPI numbers shrink to stay inside their card


class SlidePage(Doc):
    def __init__(self, rng, lang, version=0):
        super().__init__("ppt", lang, rng, version)
        pool = C.packs(lang, "ppt")
        self.deck = rng.choice(pool) if pool else None
        self.theme = rng.choice(THEMES)
        self.pal = rng.choice(PALETTES)
        slides = (self.deck or {}).get("slides") or [{"layout": "title"}]
        # weight content slides higher than title/closing (ODB slides are mostly content pages)
        w = [0.35 if s.get("layout") in ("title", "closing", "section") else 1.0 for s in slides]
        self.si = rng.choices(range(len(slides)), weights=w)[0]
        self.slide = slides[self.si]
        self.n_slides = max(len(slides), self.si + 1) + rng.randint(0, 12)
        ctx_topics = ["education", "business", "politics", "education", "science", "technology", "people", "health",
                      "business", "industry", "science", "education"]
        self.topic = ctx_topics[int((self.deck or {}).get("_idx", 0) or 0) % len(ctx_topics)]
        self.meta.update(theme=self.theme, layout_name=self.slide.get("layout"), layout="single_column",
                         page_role=self.slide.get("layout"), deck=(self.deck or {}).get("_idx"))
        self.meta["special_issue"] = ["colorful_backgroud"] if self.theme in ("dark", "gradient", "banner",
                                                                              "sidebar") else []

    def u(self, px):  # canvas units: 1 unit = 1/100 of slide height
        return self.H * px / 100.0

    def tx(self, text, cat="text_block", cls="", style="", tag="div", extra=None):
        return B.span_text(text, self.lang, cat, cls=cls, style=style or None, tag=tag, digits=self.native_digits,
                           extra=extra)

    def build(self):
        r = self.rng
        W, H = self.W, self.H
        th, pal = self.theme, self.pal
        dark = th == "dark"
        self.fg = "#ffffff" if dark else "#222222"
        self.acc = pal[1] if not dark else pal[2]
        self.title_role = r.choice(["sans", "sans", "display", "serif"]) if th != "academic" else "serif"
        self.body_role = r.choice(["sans", "sans", "sans", "serif"])
        mx = W * r.uniform(0.05, 0.08)
        top = self.u(r.uniform(5, 9))
        parts = []
        bg = ""
        if th == "dark":
            bg = f"background:linear-gradient({r.choice([135, 180, 160])}deg,{pal[0]},#0b0b14);"
        elif th == "gradient":
            bg = f"background:linear-gradient({r.choice([120, 160, 200])}deg,#ffffff 40%,{pal[2]});"
        elif th == "corporate":
            bg = "background:#ffffff;"
        # chrome
        title_h = self.u(14)
        content_top = top + title_h + self.u(3)
        if th == "banner":
            parts.append(f'<div class="zone" style="left:0;top:0;width:{W:.1f}px;height:{top + title_h:.1f}px;'
                         f'background:{pal[0]}"></div>')
        if th == "sidebar":
            sb = W * 0.035
            side = "right:0" if self.rtl else "left:0"
            parts.append(f'<div class="zone" style="{side};top:0;width:{sb:.1f}px;height:{H:.1f}px;background:{pal[1]}"></div>')
            mx += sb
        if th in ("office", "corporate", "academic"):
            parts.append(f'<div class="zone" style="left:{mx:.1f}px;top:{top + title_h - self.u(1):.1f}px;'
                         f'width:{(W - 2 * mx) * r.uniform(0.3, 1.0):.1f}px;height:{self.u(0.6):.1f}px;'
                         f'background:{pal[1]}"></div>')
        if th == "corporate":
            parts.append(f'<div class="zone" style="left:0;top:{H - self.u(7):.1f}px;width:{W:.1f}px;'
                         f'height:{self.u(7):.1f}px;background:{pal[0]}"></div>')
        lay = self.slide.get("layout", "bullets")
        self.has_logo = r.random() < 0.35 and lay not in ("title", "section", "closing", "quote")
        self.title_color = "#ffffff" if th in ("banner", "dark") else (pal[0] if r.random() < 0.7 else "#222")
        cw = W - 2 * mx
        ch = H - content_top - self.u(10)
        fn = getattr(self, f"l_{lay}", self.l_bullets)
        parts += fn(mx, top, cw, title_h, content_top, ch)
        # footer
        org = (self.deck or {}).get("organization", "")
        fcol = "#ffffff" if th in ("dark", "corporate") else "#7f7f7f"
        if lay not in ("title",) and r.random() < 0.85:
            pn = self.num(self.si + 1) if r.random() < 0.7 else self.iso(f"{self.num(self.si + 1)} / {self.num(self.n_slides)}")
            fy = H - self.u(6.2)
            parts.append(B.zone(W - mx - self.u(12), fy, self.u(12), self.u(5),
                                self.tx(pn, "page_number", cls="pn", style=f"color:{fcol};text-align:end")))
            if org and r.random() < 0.7:
                parts.append(B.zone(mx, fy, cw * 0.6, self.u(5),
                                    self.tx(org, "footer", cls="ft", style=f"color:{fcol}")))
        if self.has_logo:
            parts.append(self.logo(W - mx - self.u(9) if not self.rtl else mx, self.u(2), org))
        return self.spec("".join(parts), self.css(), page_style=bg)

    def logo(self, x, y, org):
        mark = B.logo_mark(org, self.fonts.script, self.rng)
        return (f'<div class="zone" style="left:{x:.1f}px;top:{y:.1f}px;width:{self.u(9):.1f}px;height:{self.u(9):.1f}px">'
                f'<div class="logo" data-cat="figure" data-bid="{B.bid("lg")}" style="background:{self.pal[1]}">'
                f'{mark}</div></div>')

    def title(self, x, y, w, h, text, size=None, center=False):
        size = size or self.u(self.rng.uniform(6.2, 8.0))
        if getattr(self, "has_logo", False) and not center:
            w -= self.u(11)
            if self.rtl:
                x += self.u(11)
        st = f"font-size:{size:.1f}px;color:{self.title_color};text-align:{'center' if center else 'start'};"
        return B.zone(x, y, w, h, B.heading(text, self.lang, level=1, cls="st", kwn=False, style=st, fit_lines="2"),
                      style="display:flex;align-items:flex-end;" if not center else "display:flex;align-items:center;justify-content:center;")

    def bullets_html(self, items, size, marker=None, sub_size=None):
        r = self.rng
        marker = marker or r.choice(BULLETS)
        out = []
        for it in items:
            if isinstance(it, dict):
                txt, subs = it.get("text", ""), it.get("sub") or []
            else:
                txt, subs = str(it), []
            out.append(f'<div class="bl" data-removable="1"><span class="bm nogt" style="color:{self.acc}">'
                       f'{esc(marker)}</span>{self.tx(txt, cls="bt", style=f"font-size:{size:.1f}px")}</div>')
            for sb in subs[:2]:
                out.append(f'<div class="bl sub" data-removable="1"><span class="bm nogt">–</span>'
                           f'{self.tx(sb, cls="bt", style=f"font-size:{(sub_size or size * 0.85):.1f}px")}</div>')
        return "".join(out)

    # ------------------------------------------------------------- layouts
    def l_title(self, mx, top, cw, th, ct, ch):
        d = self.deck or {}
        r = self.rng
        H = self.H
        photos = list(d.get("_photos") or [])
        if photos and self.version >= 2 and r.random() < 0.45:
            ph = photos[0]
            self.title_color = "#ffffff"
            out = [f'<div class="zone" style="left:0;top:0;width:{self.W:.1f}px;height:{H:.1f}px">'
                   f'<div class="pimg" data-cat="figure" data-bid="{B.bid("f")}" style="border-radius:0;'
                   f'background-image:url(\'file://{esc(ph["path"])}\')"></div></div>',
                   f'<div class="zone" style="left:0;top:{H * 0.52:.1f}px;width:{self.W:.1f}px;height:{H * 0.48:.1f}px;'
                   f'background:linear-gradient(to bottom,rgba(0,0,0,0),rgba(0,0,0,0.78))"></div>',
                   self.title(mx, H * 0.6, cw, self.u(20), d.get("deck_title", ""), size=self.u(r.uniform(7, 8.8)))]
            meta = " · ".join(x for x in [d.get("presenter", ""), d.get("organization", ""), d.get("date", "")] if x)
            out.append(B.zone(mx, H * 0.84, cw, self.u(8), self.tx(meta, cls="sub", style=f"font-size:{self.u(2.8):.1f}px;"
                                                                    "color:#eee")))
            return out
        y = H * r.uniform(0.28, 0.38)
        out = [self.title(mx, y, cw, self.u(22), d.get("deck_title", ""), size=self.u(r.uniform(7.5, 9.5)),
                          center=r.random() < 0.6)]
        sub = d.get("subtitle", "")
        if sub:
            out.append(B.zone(mx, y + self.u(24), cw, self.u(10),
                              self.tx(sub, cls="sub", style=f"font-size:{self.u(3.8):.1f}px;text-align:center")))
        meta = " · ".join(x for x in [d.get("presenter", ""), d.get("organization", ""), d.get("date", "")] if x)
        out.append(B.zone(mx, H * 0.75, cw, self.u(8),
                          self.tx(meta, cls="sub", style=f"font-size:{self.u(2.8):.1f}px;text-align:center")))
        return out

    def l_section(self, mx, top, cw, th, ct, ch):
        s = self.slide
        out = [self.title(mx, self.H * 0.35, cw, self.u(18), s.get("title", ""), size=self.u(8), center=True)]
        if s.get("subtitle"):
            out.append(B.zone(mx, self.H * 0.55, cw, self.u(10),
                              self.tx(s["subtitle"], cls="sub", style=f"font-size:{self.u(3.6):.1f}px;text-align:center")))
        return out

    def l_closing(self, mx, top, cw, th, ct, ch):
        s = self.slide
        out = [self.title(mx, self.H * 0.33, cw, self.u(18), s.get("title", C.L(self.lang, "Thank you", grp="ppt")),
                          size=self.u(9), center=True)]
        if s.get("contact"):
            out.append(B.zone(mx, self.H * 0.56, cw, self.u(10),
                              self.tx(s["contact"], cls="sub", style=f"font-size:{self.u(3.2):.1f}px;text-align:center")))
        return out

    def l_agenda(self, mx, top, cw, th, ct, ch):
        s = self.slide
        items = s.get("items") or []
        out = [self.title(mx, top, cw, th, s.get("title", C.L(self.lang, "Agenda", grp="ppt")))]
        rows = []
        for i, it in enumerate(items, 1):
            rows.append(f'<div class="ag" data-removable="1"><span class="agn" style="background:{self.acc}">'
                        f'{self.tx(self.num(f"{i:02d}"), cls="agnum")}</span>'
                        f'{self.tx(it, cls="bt", style=f"font-size:{self.u(4.2 if self.version < 4 else min(6.0, 4.2 + max(0, 6 - len(items)) * 0.45)):.1f}px")}</div>')
        out.append(f'<div class="zone" data-fitbox="0.75" style="left:{mx + cw * 0.05:.1f}px;top:{ct:.1f}px;'
                   f'width:{cw * 0.9:.1f}px;height:{ch:.1f}px;display:flex;flex-direction:column;'
                   f'justify-content:space-evenly;">{"".join(rows)}</div>')
        return out

    def l_bullets(self, mx, top, cw, th, ct, ch):
        s, r = self.slide, self.rng
        out = [self.title(mx, top, cw, th, s.get("title", ""))]
        size = self.u(r.uniform(3.7, 4.8))
        html = self.bullets_html(s.get("bullets") or [], size)
        w = cw if r.random() < 0.65 else cw * 0.58
        tx_x = mx if (not self.rtl or w >= cw) else mx + cw - w
        grow = "1.85\" data-fill=\"0.78" if self.version >= 4 else "1.45\" data-fill=\"0.68"
        out.append(f'<div class="zone" data-fitbox="0.7" data-grow="{grow}" style="left:{tx_x:.1f}px;'
                   f'top:{ct:.1f}px;width:{w:.1f}px;height:{ch:.1f}px">{html}</div>')
        if w < cw:
            photos = list((self.deck or {}).get("_photos") or [])
            ph = photos[0] if photos else A.pick(r, "photo", topic=self.topic, editorial=True)
            if ph:
                x2 = mx + w + cw * 0.04
                out.append(B.zone(x2 if not self.rtl else mx, ct + ch * 0.05, cw - w - cw * 0.04, ch * 0.8,
                                  f'<div class="pimg" data-cat="figure" data-bid="{B.bid("f")}" '
                                  f'style="background-image:url(\'file://{esc(ph["path"])}\')"></div>'))
        return out

    def l_two_column(self, mx, top, cw, th, ct, ch):
        s, r = self.slide, self.rng
        out = [self.title(mx, top, cw, th, s.get("title", ""))]
        size = self.u(r.uniform(3.4, 4.2))
        gap = cw * 0.06
        w = (cw - gap) / 2
        for k, (t, items) in enumerate([(s.get("left_title", ""), s.get("left") or []),
                                         (s.get("right_title", ""), s.get("right") or [])]):
            x = mx + k * (w + gap)
            if self.rtl:
                x = mx + (1 - k) * (w + gap)
            card = r.random() < 0.5
            head = B.heading(t, self.lang, level=2, cls="ct", kwn=False,
                             style=f"font-size:{size * 1.12:.1f}px;color:{'#fff' if card else self.acc}")
            body = self.bullets_html(items, size)
            if card:
                html = (f'<div class="card"><div class="cardh" style="background:{self.pal[1]}">{head}</div>'
                        f'<div class="cardb">{body}</div></div>')
            else:
                html = head + body
            grow = ' data-grow="1.7" data-fill="0.75"' if self.version >= 4 else ""
            out.append(f'<div class="zone" data-fitbox="0.7"{grow} style="left:{x:.1f}px;top:{ct:.1f}px;width:{w:.1f}px;'
                       f'height:{ch:.1f}px">{html}</div>')
        return out

    def l_chart(self, mx, top, cw, th, ct, ch):
        s, r = self.slide, self.rng
        out = [self.title(mx, top, cw, th, s.get("title", ""))]
        cats = [str(c) for c in (s.get("categories") or ["A", "B", "C"])][:6]
        series = []
        for sr in (s.get("series") or [])[:3]:
            vals = [float(v) if isinstance(v, (int, float)) else 1.0 for v in (sr.get("values") or [])][:len(cats)]
            vals += [1.0] * (len(cats) - len(vals))
            series.append({"name": str(sr.get("name", "")), "values": vals})
        if not series:
            series = [{"name": "", "values": [3, 5, 4][:len(cats)]}]
        take = s.get("takeaway", "")
        chart_w = cw * (0.62 if take else 0.9)
        chart_h = ch * 0.9
        fill = "#ffffff" if self.theme == "dark" else self.fg
        c = Chart(chart_w, chart_h, self.fonts.stack("sans"), self.lang, rtl=self.rtl, digits_native=self.native_digits,
                  palette=r.choice(["office", "excel2", "pastel"]), fs=self.u(2.4), ink=fill, grid=True)
        kind = s.get("chart", "bar")
        if kind == "pie":
            svg = c.pie(cats, [abs(v) + 0.1 for v in series[0]["values"]])
        else:
            svg = c.xy(cats, series, kind="line" if kind == "line" else "bar")
        cx = mx if not self.rtl else mx + cw - chart_w
        out.append(B.zone(cx, ct, chart_w, chart_h,
                          f'<div data-cat="figure" data-bid="{B.bid("f")}">{svg}</div>'))
        if take:
            tx = mx + chart_w + cw * 0.04 if not self.rtl else mx
            out.append(f'<div class="zone" data-fitbox="0.7" style="left:{tx:.1f}px;top:{ct + ch * 0.15:.1f}px;'
                       f'width:{cw - chart_w - cw * 0.04:.1f}px;height:{ch * 0.7:.1f}px">'
                       f'<div class="takeaway" style="border-color:{self.acc}">'
                       f'{self.tx(take, cls="bt", style=f"font-size:{self.u(3.4):.1f}px")}</div></div>')
        return out

    def l_table(self, mx, top, cw, th, ct, ch):
        s, r = self.slide, self.rng
        out = [self.title(mx, top, cw, th, s.get("title", ""))]
        header = [str(x) for x in (s.get("header") or [])][:5]
        rows = [[self.num(str(c)) for c in row][:len(header) or 5] for row in (s.get("rows") or [])][:6]
        tb = B.table(header, rows, self.lang, cls="stbl", cap_first=False,
                     note=s.get("note") or None)
        out.append(f'<div class="zone" data-fitbox="0.65" style="left:{mx:.1f}px;top:{ct:.1f}px;width:{cw:.1f}px;'
                   f'height:{ch:.1f}px;--hb:{self.pal[1]};--rb:{self.pal[2]}">{tb}</div>')
        return out

    def l_process(self, mx, top, cw, th, ct, ch):
        s, r = self.slide, self.rng
        out = [self.title(mx, top, cw, th, s.get("title", ""))]
        steps = (s.get("steps") or [])[:5]
        n = max(1, len(steps))
        gap = cw * 0.025
        w = (cw - gap * (n - 1)) / n
        shape = r.choice(["chev", "box", "circle", "box"])      # one SmartArt shape per slide
        if shape == "circle" and max((len(st.get("label", "") if isinstance(st, dict) else str(st)) for st in steps),
                                     default=0) > 12:
            shape = "box"
        numbered = r.random() < 0.5
        y0 = ct + ch * r.uniform(0.18, 0.3)
        if self.version >= 3:
            # one row of steps, vertically centred in the content area (no empty lower half)
            cells = []
            for i, st in enumerate(steps):
                lab = st.get("label", "") if isinstance(st, dict) else str(st)
                desc = st.get("desc", "") if isinstance(st, dict) else ""
                col = self.pal[0] if (i % 2 == 0 or r.random() < 0.3) else self.pal[1]
                num = (f'<div class="stepn" style="color:{self.pal[1]}">{self.tx(self.num(i + 1), cls="stepnum")}</div>'
                       if numbered else "")
                lab_html = self.tx(lab, "title", cls="stl", style=f"font-size:{self.u(3.4):.1f}px", extra='data-sub="3"')
                desc_html = self.tx(desc, cls="bt", style=f"font-size:{self.u(2.8):.1f}px")
                cells.append(f'<div class="pcell" style="width:{w:.1f}px">{num}'
                             f'<div class="step {shape}{" rtl" if self.rtl else ""}" style="background:{col}">'
                             f'{lab_html}</div><div class="stepd">{desc_html}</div></div>')
            out.append(f'<div class="zone prow" style="left:{mx:.1f}px;top:{ct:.1f}px;width:{cw:.1f}px;height:{ch:.1f}px">'
                       f'<div class="prow-in" style="gap:{gap:.1f}px">{"".join(cells)}</div></div>')
            return out
        for i, st in enumerate(steps):
            k = (n - 1 - i) if self.rtl else i
            x = mx + k * (w + gap)
            lab = st.get("label", "") if isinstance(st, dict) else str(st)
            desc = st.get("desc", "") if isinstance(st, dict) else ""
            col = self.pal[0] if (i % 2 == 0 or r.random() < 0.3) else self.pal[1]
            num = (f'<div class="stepn" style="color:{self.pal[1]}">{self.tx(self.num(i + 1), cls="stepnum")}</div>'
                   if numbered else "")
            lab_html = self.tx(lab, "title", cls="stl", style=f"font-size:{self.u(3.4):.1f}px", extra='data-sub="3"')
            desc_html = self.tx(desc, cls="bt", style=f"font-size:{self.u(2.8):.1f}px")
            html = (f'{num}<div class="step {shape}{" rtl" if self.rtl else ""}" style="background:{col}">'
                    f'{lab_html}</div><div class="stepd">{desc_html}</div>')
            out.append(f'<div class="zone" data-fitbox="0.65" style="left:{x:.1f}px;top:{y0:.1f}px;'
                       f'width:{w:.1f}px;height:{ch * 0.62:.1f}px">{html}</div>')
        return out

    def l_kpi(self, mx, top, cw, th, ct, ch):
        s, r = self.slide, self.rng
        out = [self.title(mx, top, cw, th, s.get("title", ""))]
        kpis = (s.get("kpis") or [])[:4]
        n = max(1, len(kpis))
        gap = cw * 0.04
        w = (cw - gap * (n - 1)) / n
        if self.version >= 3:
            # KPI tiles (filled cards or ruled figures), centred vertically in the content area
            tiles = r.random() < 0.55
            bgc = r.choice(["#f2f4f7", "#eef6f3", "#f7f2ec", self.pal[0] + "14"])
            cells = []
            for kp in kpis:
                style = f"background:{bgc};padding:2.2em 0.8em;border-radius:{r.choice([0, 6, 14])}px;" if tiles else \
                    f"border-top:{self.u(0.8):.1f}px solid {self.pal[1]};padding-top:0.6em;"
                cells.append(f'<div class="kpi" style="width:{w:.1f}px;{style}">'
                             f'{self.tx(self.num(str(kp.get("value", ""))), cls="kv", style=f"font-size:{self.u(10.5 if self.version >= 4 else 8):.1f}px;color:{self.pal[1]}", extra=FIT1)}'
                             f'{self.tx(kp.get("label", ""), cls="kl", style=f"font-size:{self.u(3):.1f}px")}</div>')
            out.append(f'<div class="zone prow" style="left:{mx:.1f}px;top:{ct:.1f}px;width:{cw:.1f}px;height:{ch:.1f}px">'
                       f'<div class="prow-in" style="gap:{gap:.1f}px">{"".join(cells)}</div></div>')
            return out
        for i, kp in enumerate(kpis):
            k = (n - 1 - i) if self.rtl else i
            x = mx + k * (w + gap)
            html = (f'<div class="kpi" style="border-top:{self.u(0.8):.1f}px solid {self.pal[1]}">'
                    f'{self.tx(self.num(str(kp.get("value", ""))), cls="kv", style=f"font-size:{self.u(8):.1f}px;color:{self.pal[1]}")}'
                    f'{self.tx(kp.get("label", ""), cls="kl", style=f"font-size:{self.u(3):.1f}px")}</div>')
            out.append(f'<div class="zone" data-fitbox="0.6" style="left:{x:.1f}px;top:{ct + ch * 0.2:.1f}px;'
                       f'width:{w:.1f}px;height:{ch * 0.6:.1f}px">{html}</div>')
        return out

    def l_quote(self, mx, top, cw, th, ct, ch):
        s = self.slide
        q = self.L.quotes
        qs = self.u(5.2) if self.version < 4 else self.u(max(5.2, min(8.0, 260 / max(20, len(s.get("quote", ""))) * 2.2)))
        html = (f'<div class="quote">{self.tx(q[0] + s.get("quote", "") + q[1], cls="qt", style=f"font-size:{qs:.1f}px")}'
                f'{self.tx("— " + s.get("author", ""), cls="qa", style=f"font-size:{self.u(3.2):.1f}px")}</div>')
        return [f'<div class="zone" data-fitbox="0.6" style="left:{mx + cw * 0.08:.1f}px;top:{self.H * 0.22:.1f}px;'
                f'width:{cw * 0.84:.1f}px;height:{self.H * 0.55:.1f}px;display:flex;align-items:center">{html}</div>']

    def l_image_text(self, mx, top, cw, th, ct, ch):
        s, r = self.slide, self.rng
        out = [self.title(mx, top, cw, th, s.get("title", ""))]
        photos = list((self.deck or {}).get("_photos") or [])
        ph = r.choice(photos) if photos else A.pick(r, "photo", topic=self.topic, editorial=True)
        iw = cw * r.uniform(0.45, 0.55)
        ix = mx if (r.random() < 0.5) != self.rtl else mx + cw - iw
        g = B.bid("g")
        if ph:
            out.append(B.zone(ix, ct, iw, ch * 0.82,
                              f'<div class="pimg" data-cat="figure" data-bid="{B.bid("f")}" data-group="{g}" '
                              f'style="background-image:url(\'file://{esc(ph["path"])}\')"></div>'))
            cap = (ph.get("caption") if photos else None) or s.get("caption")
            if cap:
                out.append(B.zone(ix, ct + ch * 0.84, iw, ch * 0.14,
                                  self.tx(cap, "figure_caption", cls="cap", extra=f'data-group="{g}"',
                                          style=f"font-size:{self.u(2.4):.1f}px")))
        tx = mx + iw + cw * 0.05 if ix == mx else mx
        out.append(f'<div class="zone" data-fitbox="0.7" style="left:{tx:.1f}px;top:{ct:.1f}px;width:{cw - iw - cw * 0.05:.1f}px;'
                   f'height:{ch:.1f}px">{self.tx(s.get("text", ""), cls="bt", style=f"font-size:{self.u(3.6):.1f}px")}</div>')
        return out

    def l_formula(self, mx, top, cw, th, ct, ch):
        s = self.slide
        out = [self.title(mx, top, cw, th, s.get("title", ""))]
        html = "".join(B.equation(str(lx).strip().strip("$"), None) for lx in (s.get("latex") or [])[:3])
        html += self.bullets_html(s.get("bullets") or [], self.u(3.6))
        out.append(f'<div class="zone fz" data-fitbox="0.6" style="left:{mx:.1f}px;top:{ct:.1f}px;width:{cw:.1f}px;'
                   f'height:{ch:.1f}px">{html}</div>')
        return out

    def css(self):
        r = self.rng
        f_t = self.fonts.stack(self.title_role) if not self.nastaliq else self.fonts.stack("nastaliq")
        f_b = self.body_font(self.body_role)
        bw = self.bw(self.body_role)
        lh = self.lh(r.uniform(1.12, 1.3))
        return f"""
#page{{font-family:{f_b};color:{self.fg};line-height:{lh};--bw:{bw};}}
.zone{{font-size:{self.u(3.8):.1f}px;}}
.zone[data-fitbox]>*{{zoom:var(--k,1);}}
.st{{font-family:{f_t};font-weight:{r.choice([600, 700, 700, 800])};line-height:{self.lh(1.1)};margin:0;width:100%;}}
.sub{{color:{'#ddd' if self.theme == 'dark' else '#555'};}}
.bl{{display:flex;gap:0.5em;align-items:baseline;margin:0 0 {r.uniform(0.35, 0.8):.2f}em;}}
.bl.sub{{margin-inline-start:1.6em;color:{'#ddd' if self.theme == 'dark' else '#444'};}}
.bm{{flex:0 0 auto;}}
.bt{{flex:1 1 auto;}}
.ag{{display:flex;align-items:center;gap:0.8em;}}
.agn{{color:#fff;border-radius:50%;min-width:2.2em;height:2.2em;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:{self.u(3):.1f}px;}}
.card{{border-radius:{r.choice([0, 6, 12])}px;overflow:hidden;background:{'rgba(255,255,255,0.08)' if self.theme == 'dark' else self.pal[2]};height:100%;}}
.cardh{{padding:0.4em 0.7em;}} .cardb{{padding:0.6em 0.8em;}}
.ct{{margin:0 0 0.4em;font-weight:700;}}
.takeaway{{border-inline-start:6px solid;padding:0.5em 0.8em;background:{'rgba(255,255,255,0.08)' if self.theme == 'dark' else '#f5f5f5'};}}
table.stbl{{border-collapse:collapse;width:100%;font-size:{self.u(2.9):.1f}px;}}
table.stbl th{{background:var(--hb);color:#fff;padding:0.35em 0.6em;font-weight:700;}}
table.stbl td{{padding:0.3em 0.6em;border-bottom:1px solid #ccc;text-align:center;}}
table.stbl tr:nth-child(even) td{{background:var(--rb);}}
.tnote{{font-size:{self.u(2.2):.1f}px;color:#777;margin-top:0.4em;}}
.step{{color:#fff;padding:0.8em 0.5em;text-align:center;font-weight:700;display:flex;align-items:center;justify-content:center;min-height:{self.u(15):.1f}px;}}
.step.chev{{clip-path:polygon(0 0,88% 0,100% 50%,88% 100%,0 100%,12% 50%);padding:0 1.2em;}}
.step.chev.rtl{{clip-path:polygon(12% 0,100% 0,88% 50%,100% 100%,12% 100%,0 50%);}}
.stepn{{text-align:center;font-weight:800;font-size:{self.u(5):.1f}px;line-height:1.1;margin-bottom:0.15em;}}
.step.circle{{border-radius:999px;}}
.step.box{{border-radius:8px;}}
.stepd{{margin-top:0.6em;text-align:center;}}
.kpi{{text-align:center;padding-top:0.6em;}}
.prow{{display:flex;flex-direction:column;justify-content:center;}}
.prow-in{{display:flex;flex-direction:row;align-items:stretch;justify-content:center;}}
.pcell{{display:flex;flex-direction:column;justify-content:flex-start;}}
.kv{{font-weight:800;line-height:1.1;white-space:nowrap;}}
.kl{{margin-top:0.3em;color:{'#ddd' if self.theme == 'dark' else '#555'};}}
.quote{{border-inline-start:8px solid {self.acc};padding-inline-start:1em;}}
.qt{{font-style:{self.italic('serif')};line-height:{self.lh(1.3)};}}
.qa{{margin-top:0.8em;color:{'#ccc' if self.theme == 'dark' else '#666'};}}
.pimg{{width:100%;height:100%;background-size:cover;background-position:center;border-radius:{r.choice([0, 0, 6, 14])}px;}}
.logo{{width:100%;height:100%;border-radius:{r.choice(['50%', '8px', '0'])};display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-family:{self.fonts.stack('sans')};}}
.pn,.ft{{font-size:{self.u(2.3):.1f}px;}}
.cap{{color:#666;}}
.eqrow{{display:flex;justify-content:center;margin:0.6em 0;font-size:{self.u(4.2):.1f}px;}}
.katex{{direction:ltr;}}
"""


def make(rng, lang, version=0):
    return SlidePage(rng, lang, version).build()

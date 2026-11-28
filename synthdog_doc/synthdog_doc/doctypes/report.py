"""Research report pages (equity / industry research): broker header, rating sidebar, highlights, charts, financials."""
from .. import blocks as B
from .. import corpus as C
from ..charts import Chart, random_series
from ..doc import Doc
from ..geometry import IN
from ..textkit import esc, words_html

BRAND = ["#003a70", "#9b1b30", "#00594f", "#1d3c78", "#7a1f5c", "#d2691e", "#004b87", "#5a2d82", "#006341"]


class ReportPage(Doc):
    def __init__(self, rng, lang, version=0):
        super().__init__("report", lang, rng, version)
        pool = C.packs(lang, "report")
        rich = [p for p in pool if p.get("_x")]
        self.pk = rng.choice(rich or pool) if pool else {}
        self.x = self.pk.get("_x") or {}
        roles, w = ["cover", "body", "financials", "disclaimer"], [0.35, 0.35, 0.18, 0.12]
        if version >= 3:
            roles, w = roles + ["charts", "valuation"], [0.27, 0.27, 0.13, 0.11, 0.11, 0.11]
        self.role = rng.choices(roles, weights=w)[0]
        self.meta.update(page_role=self.role, layout="single_column" if self.role != "cover" else "1andmore_column")

    def chart(self, w, h, title, kind=None, spec=None):
        r = self.rng
        if spec:
            cats = [self.num(str(c)) for c in spec.get("categories") or []]
            series = []
            for sr in (spec.get("series") or [])[:3]:
                vals = [v for v in (sr.get("values") or []) if isinstance(v, (int, float))][:len(cats)]
                if len(vals) == len(cats) and cats:
                    series.append({"name": str(sr.get("name", "")), "values": vals})
            if series:
                c = Chart(w, h, self.fonts.stack("sans"), self.lang, rtl=self.rtl, digits_native=self.native_digits,
                          palette=r.choice(["office", "excel2", "gray"]), fs=self.pt(7.5), grid=True)
                return c.xy(cats, series, kind=spec.get("kind") if spec.get("kind") in ("bar", "line") else "bar",
                            legend=len(series) > 1, ylabel=spec.get("y_label", ""))
        years = [self.num(y) for y in range(2019, 2027)][: r.randint(5, 8)]
        kind = kind or r.choice(["bar", "line", "bar", "line"])
        names = [self.pk.get("company", "Co."), C.L(self.lang, "Index", grp="report")][: r.randint(1, 2)]
        series = [{"name": n, "values": v} for n, v in zip(names, random_series(r, len(years), len(names), kind))]
        c = Chart(w, h, self.fonts.stack("sans"), self.lang, rtl=self.rtl, digits_native=self.native_digits,
                  palette=r.choice(["office", "excel2", "gray"]), fs=self.pt(7.5), grid=True)
        return c.xy(years, series, kind=kind, legend=len(series) > 1)

    def fin_table(self, rows_n=None):
        r = self.rng
        x = self.x
        if x.get("fin_rows") and x.get("years"):
            yrs = [self.num(str(y)) for y in x["years"]]
            unit = x.get("unit_label", "")
            cur = x.get("currency", "")
            head = [f"{C.L(self.lang, 'Fiscal year', grp='report')} ({cur} {unit})".replace("( ", "(").strip()] + yrs
            rows = []
            for fr in x["fin_rows"][: rows_n or 10]:
                vals = fr.get("values") or []
                kind = fr.get("kind", "abs")
                cells = []
                for v in vals[:len(yrs)]:
                    if v is None or (isinstance(v, str) and v.strip().lower() in ("", "none", "null", "nan", "n/a")):
                        cells.append("–")
                    elif not isinstance(v, (int, float)):
                        cells.append(str(v))
                    elif kind == "pct":
                        cells.append(self.fnum(v, 1, pct=True))
                    elif kind in ("ratio", "per_share"):
                        cells.append(self.fnum(v, 2 if abs(v) < 100 else 1))
                    else:
                        cells.append(self.fnum(v, 0 if abs(v) >= 100 else 1))
                cells += [""] * (len(yrs) - len(cells))
                rows.append([str(fr.get("name", ""))] + cells)
            return head, rows
        items = self.pk.get("fin_rows") or ["Revenue", "EBITDA", "Net profit", "EPS", "P/E", "ROE"]
        items = items[: rows_n or r.randint(6, 10)]
        yrs = [f"{self.num(y)}{'A' if y < 2026 else 'E'}" for y in range(2022, 2028)][: r.randint(4, 6)]
        cur = self.pk.get("currency", "")
        head = [C.L(self.lang, "Fiscal year", grp="report") + (f" ({cur})" if cur and r.random() < 0.5 else "")] + yrs
        rows = []
        for it in items:
            base = r.uniform(5, 5000)
            vals = []
            for _ in yrs:
                base *= r.uniform(0.92, 1.18)
                v = f"{base:,.1f}" if base < 100 else f"{base:,.0f}"
                if r.random() < 0.15:
                    v = f"{r.uniform(-15, 35):.1f}%"
                vals.append(self.num(v))
            rows.append([it] + vals)
        return head, rows

    def build(self):
        r = self.rng
        W, H = self.W, self.H
        pk = self.pk
        brand = r.choice(BRAND)
        body_pt = r.uniform(8.6, 10.2)
        body_px = self.pt(body_pt)
        m = r.uniform(0.5, 0.75) * IN
        cw = W - 2 * m
        broker = pk.get("broker") or r.choice(C.locale(self.lang).get("brokers") or ["Securities"])
        date = self.num(C.locale(self.lang).get("date_format_example") or "27.11.2026")
        zones = []
        # header bar
        logo = (f'<div class="rlogo" data-cat="figure" data-bid="{B.bid("lg")}" style="background:{brand}">'
                f'{B.logo_mark(broker, self.fonts.script, r)}</div>')
        hdr = (f'<div class="rhdr">{logo}{B.span_text(broker, self.lang, "header", cls="rbroker")}'
               f'{B.span_text(pk.get("report_type", C.L(self.lang, "Company Report", grp="report")), self.lang, "header", cls="rtype")}</div>')
        zones.append(B.zone(m, m * 0.55, cw, body_px * 3.4, hdr))
        top = m * 0.55 + body_px * 4.0
        # footer
        foot = [B.span_text(C.L(self.lang, "Please read the disclaimer", grp="report"), self.lang, "footer", cls="rfoot"),
                B.span_text(self.num(r.randint(2, 24)), self.lang, "page_number", cls="rpn")]
        zones.append(B.zone(m, H - m * 0.8, cw, body_px * 2, f'<div class="rfrow">{"".join(foot)}</div>'))
        if self.role == "cover":
            side_w = cw * r.uniform(0.28, 0.34)
            main_w = cw - side_w - 0.25 * IN
            side_left = self.rtl if (self.version < 3 or r.random() < 0.7) else not self.rtl
            sx = m if side_left else m + main_w + 0.25 * IN
            mx = m + side_w + 0.25 * IN if side_left else m
            title = [B.span_text(f"{pk.get('company', '')} ({pk.get('ticker', '')})", self.lang, "title", cls="rcomp",
                                 extra='data-sub="2"'),
                     B.heading(pk.get("title", ""), self.lang, level=1, cls="rtitle", kwn=False, fit_lines="3",
                               style=f"color:{brand}")]
            zones.append(B.zone(mx, top, main_w, 0, "".join(title), zid="rtit", auto_h=True))
            flow = [B.heading(C.L(self.lang, "Investment highlights", grp="report"), self.lang, level=2, cls="rsh",
                              style=f"color:{brand}")]
            for hl in pk.get("highlights") or []:
                flow.append(f'<div class="rbul">' + B.para("■ " + hl, self.lang, cls="rbp", split=True) + "</div>")
            for sec in (pk.get("sections") or [])[:2]:
                flow.append(B.heading(sec.get("heading", ""), self.lang, level=2, cls="rsh", style=f"color:{brand}"))
                for p in sec.get("paragraphs") or []:
                    flow.append(B.para(p, self.lang, cls="rp", hyph=self.hyph()))
            zones.append(B.zone(mx, top, main_w, H - top - m * 1.3, "".join(flow), flow=True, cols=1, zorder=1,
                                top_from="#rtit", gap_top=body_px))
            # sidebar: rating box + company data table + chart
            rating = pk.get("rating") or C.L(self.lang, "Buy", grp="report")
            box = (f'<div class="rating" style="background:{brand}">'
                   f'{B.span_text(C.L(self.lang, "Rating", grp="report") + ": " + rating, self.lang, "text_block", cls="rrat")}'
                   f'{B.span_text(C.L(self.lang, "Target price", grp="report") + ": " + self.num(str(pk.get("target_price", ""))), self.lang, "text_block", cls="rtp")}'
                   f'</div>')
            x = self.x
            if x.get("current_price"):
                cur = x.get("currency", "")
                rows = [[C.L(self.lang, "Current price", grp="report"), f"{cur} {self.fnum(x['current_price'], 2)}".strip()],
                        [C.L(self.lang, "Target price", grp="report"), f"{cur} {self.fnum(x.get('target_price', 0), 2)}".strip()],
                        [C.L(self.lang, "Market capitalization", grp="report") + f" ({x.get('unit_label', '')})",
                         self.fnum(x.get("market_cap_mn", 0), 0)],
                        [C.L(self.lang, "52-week range", grp="report"),
                         f"{self.fnum(x.get('week52_low', 0), 2)}–{self.fnum(x.get('week52_high', 0), 2)}"],
                        [C.L(self.lang, "Shares outstanding", grp="report") + f" ({x.get('unit_label', '')})",
                         self.fnum(x.get("shares_outstanding_mn", 0), 1)],
                        [C.L(self.lang, "Free float", grp="report"), self.fnum(x.get("free_float_pct", 0), 0, pct=True)]]
            else:
                rows = [[C.L(self.lang, k, grp="report"), self.num(v)] for k, v in
                        [("Current price", str(pk.get("current_price", ""))), ("Free float", f"{r.uniform(10, 80):.0f}%")]]
            tbl = B.table([C.L(self.lang, "Company data", grp="report"), ""], rows, self.lang, cls="rdata",
                          num_align=True)
            ph = (self.x.get("price_history") or {})
            spec = ({"categories": ph.get("labels", [])[:12], "kind": "line",
                     "series": [{"name": pk.get("company", ""), "values": ph.get("values", [])[:12]}]}
                    if ph.get("values") else None)
            chart = B.figure(self.chart(side_w, side_w * 0.7, "", "line", spec=spec),
                             C.L(self.lang, "Price performance", grp="report"), self.lang, cap_first=True,
                             cls="rchart", capcls="rcap")
            src = B.span_text(f"{C.L(self.lang, 'Source', grp='report')}: {broker}", self.lang, "figure_footnote",
                              cls="rsrc")
            an = "".join(B.span_text(a, self.lang, "text_block", cls="ran") for a in (pk.get("analysts") or [])[:2])
            zones.append(B.zone(sx, top, side_w, H - top - m * 1.3,
                                f'<div class="side">{box}{tbl}{chart}{src}<div class="anbox">{an}</div></div>'))
        elif self.role == "disclaimer" and self.version >= 3 and C.packs(self.lang, "disclosures"):
            zones.append(self.disclosures(m, top, cw, H - top - m * 1.3, brand, broker))
            self.meta["layout"] = "double_column"
        elif self.role == "charts":
            zones.append(self.chart_page(m, top, cw, H - top - m * 1.3, brand, broker))
            self.meta["layout"] = "1andmore_column"
        elif self.role == "valuation":
            zones.append(self.valuation_page(m, top, cw, H - top - m * 1.3, brand, broker))
        elif self.role == "disclaimer":
            flow = [B.heading(C.L(self.lang, "Disclaimer", grp="report"), self.lang, level=2, cls="rsh", style=f"color:{brand}")]
            disc = pk.get("disclaimer") or ""
            cp = C.corpus(self.lang)
            # disclaimer pages repeat the house disclaimer blocks of several reports (same broker style)
            discs = [p.get("disclaimer") for p in C.packs(self.lang, "report") if p.get("disclaimer")]
            r.shuffle(discs)
            for d in list(dict.fromkeys([disc] + discs))[:8]:
                flow.append(B.para(d, self.lang, cls="rp small", hyph=self.hyph()))
            zones.append(B.zone(m, top, cw, H - top - m * 1.3, "".join(flow), flow=True, cols=r.choice([1, 2]), balance=True,
                                gap="0.25in", zorder=1))
            self.meta["layout"] = "double_column"
        else:
            flow = []
            secs = pk.get("sections") or []
            # short packs: start at the first section and add the highlights so the page is never near-empty
            start = r.randint(0, 1) if len(secs) > 2 else 0
            if sum(len(sec.get("paragraphs") or []) for sec in secs[start:]) < 4 and pk.get("highlights"):
                flow.append(B.heading(C.L(self.lang, "Investment highlights", grp="report"), self.lang, level=2,
                                      cls="rsh", style=f"color:{brand}"))
                for hl in pk["highlights"]:
                    flow.append(f'<div class="rbul">' + B.para("■ " + hl, self.lang, cls="rbp", split=True) + "</div>")
            for sec in secs[start:]:
                flow.append(B.heading(sec.get("heading", ""), self.lang, level=2, cls="rsh", style=f"color:{brand}"))
                for p in sec.get("paragraphs") or []:
                    flow.append(B.para(p, self.lang, cls="rp", hyph=self.hyph()))
                if r.random() < 0.6:
                    charts = self.x.get("charts") or []
                    spec = r.choice(charts) if charts else None
                    title = (spec or {}).get("title") or r.choice(pk.get("chart_titles") or ["Chart"])
                    self.fig_k = getattr(self, "fig_k", r.randint(1, 6)) + 1
                    flow.append(B.figure(self.chart(cw * 0.48, cw * 0.28, "", None, spec=spec),
                                         f"{C.L(self.lang, 'Figure', 'Fig.', grp='paper')} {self.num(self.fig_k)}: {title}",
                                         self.lang, cap_first=True, cls="rchart", capcls="rcap") +
                                B.span_text(f"{C.L(self.lang, 'Source', grp='report')}: {broker}", self.lang,
                                            "figure_footnote", cls="rsrc"))
            if self.role == "financials" or r.random() < 0.5:
                head, rows = self.fin_table()
                flow.insert(r.randint(0, min(2, len(flow))),
                            B.table(head, rows, self.lang, caption=C.L(self.lang, "Financial summary", grp="report"),
                                    cls="rfin", capcls="rcap", note=f"{C.L(self.lang, 'Source', grp='report')}: {broker}"))
            if self.role == "financials":
                head, rows = self.fin_table(8)
                flow.append(B.table(head, rows, self.lang, caption=C.L(self.lang, "Forecast", grp="report"),
                                    cls="rfin", capcls="rcap"))
            zones.append(B.zone(m, top, cw, H - top - m * 1.3, "".join(flow), flow=True,
                                cols=2 if r.random() < 0.3 else 1, gap="0.25in", zorder=1, balance=True))
        return self.spec("".join(zones), self.css(body_px, brand))

    # ------------------------------------------------------------------ v3 page types
    def disclosures(self, x, y, w, h, brand, broker):
        """One broker's disclosures: own disclaimer, rating definitions, rating distribution, analyst certification,
        regulatory sections -- all about THIS report (no stack of other companies' disclaimers)."""
        r, pk = self.rng, self.pk
        d = C.packs(self.lang, "disclosures")[0]
        analysts = [str(a).split("—")[0].split("<")[0].strip() for a in (pk.get("analysts") or [])][:1] \
            or [C.person(self.lang, r)]
        sub = lambda t: str(t).replace("{broker}", broker).replace("{analyst}", analysts[0])  # noqa: E731
        flow = [B.heading(sub(d.get("title") or C.L(self.lang, "Disclaimer", grp="report")), self.lang, level=2,
                          cls="rsh", style=f"color:{brand}")]
        if pk.get("disclaimer"):
            flow.append(B.para(pk["disclaimer"], self.lang, cls="rp small", hyph=self.hyph()))
        ratings = [rw for rw in (d.get("ratings") or []) if isinstance(rw, list) and len(rw) >= 2]
        if ratings:
            flow.append(B.table(d.get("rating_header") or ["", ""], [[sub(a), sub(b)] for a, b in ratings[:5]],
                                self.lang, cls="rfin rdef", num_align=False))
        if d.get("distribution_header") and ratings:
            # sell-side coverage is skewed to Buy/Hold; Sell ratings are rare
            prof = [(35, 60), (8, 25), (15, 35), (2, 8), (1, 6)]
            cov = [r.uniform(*prof[min(i, 4)]) for i in range(len(ratings[:5]))]
            tot = sum(cov)
            rows = [[sub(rw[0]), self.fnum(round(c / tot * 100, 1), 1, pct=True), self.fnum(r.uniform(0, 25), 1, pct=True)]
                    for rw, c in zip(ratings[:5], cov)]
            flow.append(B.table(d["distribution_header"], rows, self.lang, cls="rfin",
                                caption=sub(d.get("distribution_title", "")) or None, capcls="rcap"))
        if d.get("certification"):
            flow.append(B.heading(sub(d.get("certification_title", "")), self.lang, level=3, cls="rsh3"))
            flow.append(B.para(sub(d["certification"]), self.lang, cls="rp small", hyph=self.hyph()))
        for sec in d.get("sections") or []:
            flow.append(B.heading(sub(sec.get("heading", "")), self.lang, level=3, cls="rsh3"))
            flow.append(B.para(sub(sec.get("text", "")), self.lang, cls="rp small", hyph=self.hyph()))
        return B.zone(x, y, w, h, "".join(flow), flow=True, cols=r.choice([1, 2, 2]), balance=True,
                      gap="0.25in", zorder=1)

    def chart_page(self, x, y, w, h, brand, broker):
        """Exhibit gallery: a grid of 4 (or 6) numbered charts with titles and source lines, short commentary."""
        r, pk = self.rng, self.pk
        specs = list(self.x.get("charts") or [])
        ph = self.x.get("price_history") or {}
        if ph.get("values"):
            specs.insert(0, {"title": C.L(self.lang, "Price performance", grp="report"), "kind": "line",
                             "categories": ph.get("labels", [])[:12],
                             "series": [{"name": pk.get("company", ""), "values": ph.get("values", [])[:12]}]})
        n = 6 if (h > w * 1.35 and r.random() < 0.4) else 4
        cw2 = (w - 0.3 * IN) / 2
        chh = min(cw2 * 0.62, (h - 1.2 * IN) / (n // 2) - 0.75 * IN)
        k0 = r.randint(1, 12)
        cells = []
        titles = list(pk.get("chart_titles") or [])
        for i in range(n):
            spec = specs[i] if i < len(specs) else None
            title = (spec or {}).get("title") or (titles[i % len(titles)] if titles else f"{i + 1}")
            fig = B.figure(self.chart(cw2, chh, "", None, spec=spec),
                           f"{C.L(self.lang, 'Figure', 'Fig.', grp='paper')} {self.num(k0 + i)}: {title}", self.lang,
                           cap_first=True, cls="rchart", capcls="rcap", shrink=False)
            src = B.span_text(f"{C.L(self.lang, 'Source', grp='report')}: {broker}", self.lang, "figure_footnote",
                              cls="rsrc")
            cells.append(f'<div class="gcell">{fig}{src}</div>')
        intro = ""
        secs = pk.get("sections") or []
        if secs and secs[0].get("paragraphs"):
            intro = B.para(secs[0]["paragraphs"][0], self.lang, cls="rp", hyph=self.hyph())
        head = B.heading(C.L(self.lang, "Key charts", "Charts", grp="report"), self.lang, level=2, cls="rsh",
                         style=f"color:{brand}")
        return B.zone(x, y, w, h, f'{head}{intro}<div class="cgrid">{"".join(cells)}</div>')

    def valuation_page(self, x, y, w, h, brand, broker):
        """Peer comparison table + valuation summary + text (equity research 'Valuation' section)."""
        r, pk = self.rng, self.pk
        loc = C.locale(self.lang)
        peers = [c for c in (loc.get("companies") or []) if c != pk.get("company")]
        r.shuffle(peers)
        peers = [pk.get("company", "")] + peers[: r.randint(5, 8)]
        cur = self.x.get("currency", "") or pk.get("currency", "")
        y1, y2 = (self.x.get("years") or [2025, 2026])[-2:] if len(self.x.get("years") or []) >= 2 else (2025, 2026)
        head = [C.L(self.lang, "Company", grp="report"), f"{C.L(self.lang, 'Market capitalization', grp='report')}",
                f"P/E {self.num(str(y1))}", f"P/E {self.num(str(y2))}", f"EV/EBITDA {self.num(str(y2))}",
                "P/B", C.L(self.lang, "Dividend yield", grp="report")]
        rows, pes = [], []
        for c in peers:
            pe1 = r.uniform(7, 32)
            pes.append(pe1)
            rows.append([c, self.fnum(r.uniform(300, 90000), 0), self.fnum(pe1, 1), self.fnum(pe1 * r.uniform(0.75, 0.95), 1),
                         self.fnum(r.uniform(4, 18), 1), self.fnum(r.uniform(0.6, 5.5), 1),
                         self.fnum(r.uniform(0, 6), 1, pct=True)])
        med = sorted(pes[1:])[len(pes[1:]) // 2] if len(pes) > 1 else pes[0]
        rows.append([C.L(self.lang, "Median", grp="report"), "", self.fnum(med, 1), "", "", "", ""])
        flow = [B.heading(C.L(self.lang, "Valuation", grp="report"), self.lang, level=2, cls="rsh",
                          style=f"color:{brand}")]
        secs = pk.get("sections") or []
        if len(secs) > 1:
            for p in (secs[-1].get("paragraphs") or [])[:2]:
                flow.append(B.para(p, self.lang, cls="rp", hyph=self.hyph()))
        flow.append(B.table(head, rows, self.lang, caption=C.L(self.lang, "Peer comparison", grp="report") +
                            (f" ({cur})" if cur else ""), cls="rfin comps", capcls="rcap",
                            note=f"{C.L(self.lang, 'Source', grp='report')}: {broker}"))
        if self.x.get("target_price"):
            tp = self.x.get("target_price")
            rows2 = [[C.L(self.lang, "Target price", grp="report"), f"{cur} {self.fnum(tp, 2)}".strip()],
                     [C.L(self.lang, "Current price", grp="report"),
                      f"{cur} {self.fnum(self.x.get('current_price', tp * 0.8), 2)}".strip()],
                     ["WACC", self.fnum(r.uniform(8, 14), 1, pct=True)],
                     [C.L(self.lang, "Terminal growth", grp="report"), self.fnum(r.uniform(2, 5), 1, pct=True)]]
            flow.append(B.table([C.L(self.lang, "Valuation", grp="report"), ""], rows2, self.lang, cls="rdata vsum"))
        for p in (secs[0].get("paragraphs") or [])[1:3] if secs else []:
            flow.append(B.para(p, self.lang, cls="rp", hyph=self.hyph()))
        return B.zone(x, y, w, h, "".join(flow), flow=True, cols=1, zorder=1, balance=False)

    def css(self, body_px, brand):
        r = self.rng
        f_body = self.body_font(r.choice(["sans", "sans", "serif"]))
        f_sans = self.fonts.stack("sans")
        bw = self.bw("sans")
        lh = self.lh(r.uniform(1.3, 1.55))
        return f"""
#page{{font-family:{f_body};font-size:{body_px:.2f}px;line-height:{lh};color:#222;--bw:{bw};}}
.rhdr{{display:flex;align-items:center;gap:0.8em;border-bottom:2px solid {brand};height:100%;}}
.rlogo{{width:{body_px * 2.6:.1f}px;height:{body_px * 2.6:.1f}px;border-radius:{r.choice(['4px', '50%'])};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-family:{f_sans};}}
.rbroker{{font-family:{f_sans};font-weight:800;font-size:{body_px * 1.4:.1f}px;color:{brand};flex:1;}}
.rtype{{font-family:{f_sans};font-size:{body_px * 1.05:.1f}px;color:#555;}}
.rcomp{{font-family:{f_sans};font-weight:700;font-size:{body_px * 1.2:.1f}px;}}
.rtitle{{font-family:{f_sans};font-size:{body_px * 1.9:.1f}px;line-height:{self.lh(1.2)};margin:0.2em 0;}}
.rsh{{font-family:{f_sans};font-size:{body_px * 1.15:.1f}px;margin:0.7em 0 0.3em;border-bottom:1px solid #ccc;padding-bottom:0.1em;}}
.rp{{text-align:{'justify' if r.random() < self.typo['justify'] else 'start'};margin:0 0 0.45em;}}
.rp.small{{font-size:{body_px * 0.85:.1f}px;}}
.rbp{{margin:0 0 0.35em;}}
.side{{background:#f4f6f9;padding:0.6em;height:100%;}}
.rating{{color:#fff;padding:0.5em;margin-bottom:0.5em;}}
.rrat{{font-weight:800;font-size:{body_px * 1.3:.1f}px;}}
.rtp{{font-size:{body_px * 1.05:.1f}px;}}
table.rdata{{width:100%;border-collapse:collapse;font-size:{body_px * 0.88:.1f}px;margin-bottom:0.5em;}}
table.rdata th{{text-align:start;border-bottom:1.5px solid {brand};}}
table.rdata td{{border-bottom:0.5px solid #ccc;padding:0.15em 0.2em;}}
table.rdata td.num{{text-align:end;}}
.rchart{{margin:0.5em 0 0.2em;}}
.rcap{{font-family:{f_sans};font-weight:700;font-size:{body_px * 0.9:.1f}px;color:{brand};margin-bottom:0.2em;}}
.rsrc{{font-size:{body_px * 0.75:.1f}px;color:#777;margin-bottom:0.5em;}}
.anbox{{margin-top:0.8em;font-size:{body_px * 0.85:.1f}px;}}
table.rfin{{width:100%;border-collapse:collapse;font-size:{body_px * 0.86:.1f}px;margin:0.3em 0;}}
table.rfin th{{background:{brand};color:#fff;padding:0.25em 0.4em;font-weight:700;}}
table.rfin td{{padding:0.2em 0.4em;border-bottom:0.5px solid #ddd;}}
table.rfin td.num{{text-align:end;}}
table.rfin tr:nth-child(odd) td{{background:#f7f7f7;}}
table.rdef td:first-child{{font-weight:700;white-space:nowrap;}}
table.comps tr:last-child td{{border-top:1.2px solid #444;font-weight:700;background:#fff;}}
.rsh3{{font-family:{f_sans};font-size:{body_px * 0.95:.1f}px;font-weight:700;margin:0.6em 0 0.2em;}}
.cgrid{{display:grid;grid-template-columns:1fr 1fr;gap:0.25in 0.3in;margin-top:0.6em;}}
.gcell{{border-top:1.5px solid {brand};padding-top:0.3em;}}
table.vsum{{width:60%;margin-top:0.6em;}}
.tnote{{font-size:{body_px * 0.75:.1f}px;color:#777;}}
.rfrow{{display:flex;justify-content:space-between;border-top:0.8px solid #999;padding-top:2px;font-size:{body_px * 0.8:.1f}px;color:#666;}}
"""


def make(rng, lang, version=0):
    return ReportPage(rng, lang, version).build()

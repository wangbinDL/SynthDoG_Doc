"""Book pages: chapter openers and body pages (running heads, folios, footnotes, occasional figures)."""
from .. import imagepool as A
from .. import blocks as B
from .. import corpus as C
from ..doc import Doc
from ..geometry import IN
import re

from ..textkit import words_html

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


class BookPage(Doc):
    def __init__(self, rng, lang, version=0):
        super().__init__("book", lang, rng, version)
        roles, w = ["opener", "body", "section", "toc", "imprint", "twocol"], [0.16, 0.56, 0.16, 0.0, 0.0, 0.0]
        if version >= 2:
            w = [0.14, 0.5, 0.12, 0.1, 0.04, 0.1]
        self.role = rng.choices(roles, weights=w)[0]
        self.genre = rng.choice(["nonfiction", "nonfiction", "textbook", "literary"])
        self.meta.update(page_role=self.role, genre=self.genre, layout="single_column")

    def build_toc(self, left, mt, cw, H, mb, body_px):
        """Table of contents with dot leaders and ascending page numbers."""
        r = self.rng
        cp = C.corpus(self.lang)
        arts = [cp.wiki_article(r, 3000) for _ in range(r.randint(4, 7))]
        rows = []
        page = r.randint(1, 15)
        level2 = r.random() < 0.6
        lbl = C.L(self.lang, "Chapter", grp="book")
        if self.version >= 3:
            # one book = one subject: chapters are the sections of a single long article (coherent TOC)
            for _ in range(30):
                a = cp.wiki_article(r, 6000)
                heads = [s["heading"] for s in a["sections"] if s.get("heading")]
                if len(heads) >= 6:
                    for ci, hd in enumerate(heads[:14], 1):
                        num = self.num(ci) if r.random() < 0.8 else ROMAN[(ci - 1) % 12]
                        rows.append((1, f"{num}.", hd, page))
                        page += r.randint(9, 28)
                    arts = []
                    self.meta["toc_subject"] = a["title"]
                    break
        for ci, a in enumerate(arts, 1):
            num = self.num(ci) if r.random() < 0.7 else ROMAN[(ci - 1) % 12]
            rows.append((1, f"{lbl} {num}" if r.random() < 0.4 else f"{num}.", a["title"], page))
            page += r.randint(1, 3)
            if level2:
                for si, sec in enumerate(a["sections"][1:5], 1):
                    if sec.get("heading"):
                        rows.append((2, f"{self.num(ci)}.{self.num(si)}", sec["heading"], page))
                        page += r.randint(2, 9)
            page += r.randint(4, 18)
        items = []
        for lvl, numtxt, title, pg in rows:
            items.append(f'<div class="toc l{lvl}" data-cat="text_block" data-bid="{B.bid("toc")}">'
                         f'<span class="tn">{words_html(numtxt, self.lang)}</span>'
                         f'<span class="tt">{words_html(title, self.lang)}</span><span class="lead nogt"></span>'
                         f'<span class="tp">{words_html(self.num(pg), self.lang)}</span></div>')
        head = B.heading(C.L(self.lang, "Contents", grp="book"), self.lang, level=1, cls="toch", kwn=False)
        z = [B.zone(left, mt, cw, 0, head, zid="toch", auto_h=True),
             B.zone(left, mt, cw, H - mt - mb, "".join(items), flow=True, cols=1, top_from="#toch",
                    gap_top=body_px * 2, zorder=1)]
        return z

    def build_imprint(self, left, mt, cw, H, mb, body_px):
        """Copyright page: title/author, (c) line, rights paragraph, edition, credits, ISBN, printer (bottom-set)."""
        r = self.rng
        cp = C.corpus(self.lang)
        loc = C.locale(self.lang)
        im = (C.packs(self.lang, "imprint") or [{}])[0]
        pub = r.choice(loc.get("publishers") or ["Publisher"])
        city = r.choice(loc.get("cities") or ["City"])
        year = r.randint(1995, 2024)
        isbn = f"ISBN {r.choice(['978', '979'])}-{r.randint(0, 9)}-{r.randint(1000, 99999)}-{r.randint(100, 999)}-{r.randint(0, 9)}"
        n_ed = r.choice([1, 1, 1, 2, 3, 4])
        if n_ed == 1 or not im.get("nth_edition"):
            ed = (im.get("first_edition") or "{year}").replace("{year}", self.num(str(year)))
        else:
            ed = im["nth_edition"].replace("{n}", self.num(str(n_ed))).replace("{year}", self.num(str(year)))
        lines = [(cp.wiki_article(r)["title"], "imp imp-t"), (C.person(self.lang, r), "imp")]
        if r.random() < 0.5:
            lines = lines[::-1]
        lines += [(f"© {self.num(str(year))} {pub}", "imp"),
                  (im.get("rights") or C.L(self.lang, "Copyright notice short", grp="paper"), "imp imp-s"),
                  (ed, "imp")]
        for key, who in (("editor", C.person(self.lang, r)), ("cover_design", C.person(self.lang, r)),
                         ("typesetting", pub)):
            if im.get(key) and r.random() < 0.55:
                lines.append((f"{im[key]}: {who}", "imp"))
        lines.append((isbn, "imp"))
        countries = im.get("countries") or []
        if countries and im.get("printed_in") and r.random() < 0.7:
            lines.append((im["printed_in"].replace("{country}", r.choice(countries)), "imp"))
        lines.append((f"{pub}, {city}", "imp"))
        html = "".join(B.para(t, self.lang, cls=c, split=False) for t, c in lines)
        zw = cw * r.uniform(0.75, 1.0)
        x = left + (cw - zw) if self.rtl else left
        return [B.zone(x, 0, zw, 0, html, cls="impz", anchor_bottom=mb + H * r.uniform(0.0, 0.08))]

    def build(self):
        r = self.rng
        W, H = self.W, self.H
        cp = C.corpus(self.lang)
        art = cp.wiki_article(r, 6000)
        body_pt = r.choice([10, 10.5, 11, 11.5, 12]) if self.genre != "textbook" else r.choice([10, 10.5, 11])
        lh = self.lh(r.uniform(1.25, 1.5))
        body_px = self.pt(body_pt)
        inner = r.uniform(0.7, 1.1) * IN
        outer = r.uniform(0.6, 0.95) * IN
        recto = r.random() < 0.5
        left = inner if recto else outer
        if self.rtl:
            left = outer if recto else inner
        mt = r.uniform(0.7, 1.0) * IN
        mb = r.uniform(0.75, 1.05) * IN
        cw = W - inner - outer
        role = self.role
        zones = []
        book_title = art["title"]
        chap_no = r.randint(1, 14)
        chap_title = art["sections"][0]["heading"] or art["title"]
        folio = self.num(r.randint(9, 420))
        head_style = r.choice(["center", "outer", "none", "rule"])
        if role in ("toc", "imprint") and self.version >= 4:
            head_style = "none"      # contents / copyright pages carry no running head (it named another topic)
        if role != "opener" and head_style != "none":
            txt = book_title if not recto else chap_title
            align = "center" if head_style in ("center", "rule") else ("end" if recto else "start")
            hd = B.span_text(self.upper(txt) if r.random() < 0.3 else txt, self.lang, "header", cls="rh")
            pn = B.span_text(folio, self.lang, "page_number", cls="rhpn") if head_style == "outer" else ""
            row = (hd + pn) if recto else (pn + hd)
            zones.append(B.zone(left, mt - body_px * 2.4, cw, body_px * 1.8,
                                f'<div class="rhrow{" ruled" if head_style == "rule" else ""}" '
                                f'style="justify-content:{"space-between" if pn else align}">{row}</div>'))
        if head_style != "outer" or role == "opener":
            zones.append(B.zone(left, H - mb + body_px * 1.0, cw, body_px * 1.8,
                                B.span_text(folio, self.lang, "page_number", cls="pn"),
                                style=f"text-align:{r.choice(['center', 'center', 'end' if recto else 'start'])}"))
        flow = []
        top_from = None
        if role in ("toc", "imprint"):
            zones += (self.build_toc if role == "toc" else self.build_imprint)(left, mt, cw, H, mb, body_px)
            return self.spec("".join(zones), self.css(body_px, lh))
        if role == "opener":
            lbl = C.L(self.lang, "Chapter", grp="book")
            num = self.num(chap_no) if r.random() < 0.7 else ROMAN[(chap_no - 1) % 12]
            sink = H * r.uniform(0.18, 0.32)
            op = [B.span_text(f"{lbl} {num}", self.lang, "title", cls="chapno", extra='data-sub="1"'),
                  B.heading(chap_title, self.lang, level=1, cls="chapt", kwn=False, fit_lines="3")]
            if r.random() < 0.3:
                op.append(f'<div class="orn nogt">❧</div>')
            zones.append(B.zone(left, mt + sink * 0.4, cw, 0, "".join(op), zid="opener", auto_h=True, cls="openz"))
            top_from = "#opener"
        paras = [p for s in art["sections"] for p in s["paras"]]
        heads = [s["heading"] for s in art["sections"] if s["heading"]]
        if role != "opener":
            cut = r.randint(0, max(0, len(paras) // 3))
            paras = paras[cut:]
        first = role == "opener"
        dropcap = first and self.typo["caps"] and r.random() < 0.5
        hi = 0
        footnotes = []
        for i, ptxt in enumerate(paras):
            if i > 0 and (role == "section" and i == 1 or r.random() < (0.1 if self.genre != "literary" else 0.02)) \
                    and hi < len(heads):
                flow.append(B.heading(heads[hi], self.lang, level=2, cls="bsh"))
                hi += 1
                first = True
            if self.genre == "textbook" and r.random() < 0.08:
                ph = A.pick(r, "figure") or A.pick(r, "photo")
                if ph:
                    cap = f"{C.L(self.lang, 'Figure', 'Fig.', grp='paper')} {self.num(chap_no)}.{self.num(r.randint(1, 9))} " \
                          f"{cp.sentence(r, 30, 110, 'wiki')}"
                    flow.append(B.figure(B.img(ph["path"], f"max-width:{cw * 0.7:.0f}px;max-height:{H * 0.3:.0f}px;"
                                                        "display:block;margin:0 auto"), cap, self.lang))
            fnm = ""
            if not first and i < 4 and r.random() < 0.3 and len(footnotes) < 2:
                # footnote text taken from the same article (a later paragraph), so it is on-topic
                later = [q for q in paras[i + 1:] if 40 < len(q)]
                fn_txt = re.split(r"(?<=[.!?।۔؟])\s+", r.choice(later))[0][:220] if later else ""
                if fn_txt:
                    footnotes.append(fn_txt)
                fnm = (f'<span class="w fnm" data-fn="{len(footnotes)}">{self.num(len(footnotes))}</span>'
                       if fn_txt else "")
            cls = "bp" + (" first" if first else "") + (" dropcap" if dropcap else "") + \
                  (" cont" if (i == 0 and role != "opener") else "")
            ph = B.para(ptxt, self.lang, cls=cls, hyph=self.hyph())
            flow.append(ph[:-4] + fnm + "</p>" if fnm else ph)
            first = False
            dropcap = False
        if footnotes:
            fn = "".join(B.para(f"{self.num(k + 1)} {t}", self.lang, cls="fn", cat="page_footnote", split=False,
                                extra=f'data-fnnote="{k + 1}"') for k, t in enumerate(footnotes))
            flow.insert(0, f'<div class="fnbox" data-place="bottom" data-col="0">{fn}</div>')
        ncol = 2 if role == "twocol" else 1
        zones.append(B.zone(left, mt, cw, H - mt - mb, "".join(flow), flow=True, cols=ncol, zorder=1, top_from=top_from,
                            gap_top=body_px * 2.0, gap="0.28in",
                            rule=("0.5px solid #666" if ncol == 2 and r.random() < 0.5 else None), balance=True))
        if ncol == 2:
            self.meta["layout"] = "double_column"
        css = self.css(body_px, lh)
        return self.spec("".join(zones), css)

    def css(self, body_px, lh):
        r = self.rng
        f_body = self.body_font("serif" if r.random() < 0.95 else "sans")
        f_head = self.fonts.stack(r.choice(["serif", "serif", "display"])) if not self.nastaliq else self.fonts.stack("nastaliq")
        bw = self.bw("serif")
        ital = self.italic("serif")
        just = "justify" if r.random() < self.typo["justify"] + 0.1 else "start"
        paper = r.choice(["#ffffff", "#fffdf7", "#fbf8f0", "#ffffff"])
        return f"""
#page{{font-family:{f_body};font-size:{body_px:.2f}px;line-height:{lh};color:#161616;background:{paper};--bw:{bw};}}
.bp{{text-align:{just};text-indent:{r.choice([1.0, 1.2, 1.5, 2.0])}em;}}
.bp.first{{text-indent:0;}}
.bp.dropcap::first-letter{{float:inline-start;font-size:{r.uniform(2.8, 3.6):.2f}em;line-height:0.85;padding-inline-end:0.08em;margin-top:0.04em;}}
.bsh{{font-family:{f_head};font-size:{body_px * r.uniform(1.1, 1.3):.1f}px;font-weight:{bw};margin:1.0em 0 0.5em;text-align:{r.choice(['start', 'center'])};line-height:{self.lh(1.25)};}}
.rhrow{{display:flex;align-items:flex-end;height:100%;font-size:{body_px * 0.85:.1f}px;font-style:{ital};gap:1em;}}
.rhrow.ruled{{border-bottom:0.6px solid #444;}}
.pn,.rhpn{{font-size:{body_px * 0.9:.1f}px;}}
.openz{{text-align:{r.choice(['center', 'start', 'center'])};}}
.chapno{{font-family:{f_head};font-size:{body_px * 1.3:.1f}px;letter-spacing:{self.ls(0.15)};text-transform:none;margin-bottom:0.6em;color:#444;}}
.chapt{{font-family:{f_head};font-size:{body_px * r.uniform(1.9, 2.6):.1f}px;font-weight:{r.choice([400, bw])};line-height:{self.lh(1.2)};margin:0 0 0.4em;}}
.fnm{{vertical-align:super;font-size:0.68em;line-height:0;}}
.orn{{font-size:{body_px * 1.6:.1f}px;color:#555;}}
.fnbox{{border-top:0.6px solid #333;width:35%;padding-top:2px;margin-top:6px;}}
.fnbox .fn{{width:285%;font-size:{body_px * 0.8:.1f}px;line-height:{self.lh(1.3)};}}
.toch{{font-family:{f_head};font-size:{body_px * 2:.1f}px;font-weight:{r.choice([400, bw])};margin:0;}}
.toc{{display:flex;align-items:baseline;gap:0.4em;margin:0.35em 0;}}
.toc.l1{{font-weight:{bw};margin-top:0.7em;}}
.toc.l2{{padding-inline-start:2.2em;font-size:0.95em;}}
.toc .tt{{flex:0 1 auto;}}
.toc .lead{{flex:1 1 auto;border-bottom:{r.choice(['1.5px dotted', '1px dotted', '1px dashed'])} #444;transform:translateY(-0.25em);min-width:1.5em;}}
.toc .tp{{flex:0 0 auto;}}
.imp{{font-size:{body_px * 0.82:.1f}px;margin:0.2em 0;text-align:start;}}
.imp-t{{font-weight:700;font-size:{body_px * 0.95:.1f}px;}}
.imp-s{{font-size:{body_px * 0.74:.1f}px;line-height:{self.lh(1.3)};margin:0.5em 0;}}
.fig{{margin:0.6em 0;}} .cap{{font-size:{body_px * 0.88:.1f}px;text-align:center;margin-top:0.3em;}}
"""


def make(rng, lang, version=0):
    return BookPage(rng, lang, version).build()

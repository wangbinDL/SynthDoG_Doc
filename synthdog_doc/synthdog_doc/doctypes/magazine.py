"""Magazine pages: feature openers, multi-column body with pull quotes / photos, interview, briefs grid."""
from .. import imagepool as A
from .. import blocks as B
from .. import corpus as C
from ..doc import Doc
from ..geometry import IN
import re

from ..textkit import esc, words_html

AD_TOPIC = [  # ad category (written in the document language) -> photo topic; unmatched ads are typographic
    (r"restaur|مطعم|भोजन|रेस्त|রেস্তোর|খাবার|ресторан|kuliner|makan|caf[eé]|طعام|کھان|ریسٹورنٹ", "food"),
    (r"viaj|voyag|reise|travel|سفر|यात्रा|ভ্রমণ|тур|путеш|perjalanan|wisata|viagem", "nature"),
    (r"inmob|immob|عقار|अचल|সম্পত্তি|недвиж|properti|imóve|جائیداد|پراپرٹی|wohnung", "building"),
    (r"auto|coche|carro|voiture|سيار|गाड़ी|कार|গাড়ি|авто|mobil\b|گاڑی", "transport"),
    (r"electr|élect|elektron|إلكترون|इलेक्ट्रॉ|ইলেকট্রনি|электрон|móvil|movil|هاتف|मोबाइल|মোবাইল|мобил|seluler|celular|موبائل",
     "technology"),
    (r"clín|klinik|clinic|عياد|क्लिनिक|ক্লিনিক|клиник|کلینک|hospital|santé|salud|saúde", "health"),
]
ACC = ["#c0392b", "#16a085", "#2c3e50", "#d35400", "#8e44ad", "#1f6fb2", "#b8860b", "#e4007f", "#00897b"]


class MagazinePage(Doc):
    def __init__(self, rng, lang, version=0):
        super().__init__("magazine", lang, rng, version)
        roles = ["opener", "body", "interview", "briefs", "contents", "adpage", "photoessay"]
        w = [0.3, 0.45, 0.12, 0.13, 0.0, 0.0, 0.0] if version < 2 else (
            [0.28, 0.36, 0.1, 0.06, 0.1, 0.1, 0.0] if version < 3 else [0.24, 0.3, 0.12, 0.06, 0.09, 0.09, 0.1])
        self.role = rng.choices(roles, weights=w)[0]
        self.meta.update(page_role=self.role, layout="other_layout")

    def feature(self, fmt=None, min_photos=0):
        """Long-form feature (LLM, written natively) flattened to the story structure used by the layout."""
        pool = [f for f in C.packs(self.lang, "feature") if f.get("sections")]
        if fmt and self.version >= 3:
            pool = [f for f in pool if f.get("format") == fmt] or pool
        if min_photos and self.version >= 3:
            pool = [f for f in pool if len(f.get("_photos") or []) >= min_photos] or pool
        if not pool or self.version < 2:
            return None
        f = self.rng.choice(pool)
        body, heads = [], []
        for sec in f.get("sections") or []:
            if sec.get("heading"):
                body.append("\u0001" + sec["heading"])
            body += [str(p) for p in sec.get("paragraphs") or []]
        ph = (f.get("_photos") or [])
        return {"headline": f.get("title", ""), "deck": f.get("deck", ""), "body": body, "kicker": f.get("kicker", ""),
                "section": f.get("section", ""), "pull_quote": (f.get("pull_quotes") or [""])[0],
                "caption": (ph[0].get("caption") if ph else ""), "_photos": ph, "sidebar": f.get("sidebar"),
                "author": f.get("author", ""), "format": f.get("format", "feature"), "photo_topic": f.get("photo_topic")}

    def story(self):
        pool = C.packs(self.lang, "news")
        if not hasattr(self, "_used"):
            self._used = set()
        if pool:
            for _ in range(40):
                st = self.rng.choice(pool)
                if id(st) not in self._used:
                    self._used.add(id(st))
                    return st
        a = C.corpus(self.lang).news_article(self.rng, 3000)
        return {"headline": a["title"], "body": a["paras"], "deck": "", "caption": "", "pull_quote": "",
                "photo_topic": None, "brief": a["paras"][0][:200], "kicker": ""}

    def own_photo(self, st, k, h, box_w, cls="mphoto"):
        """k-th photo assigned to this story (caption written for that very photo) if it has enough pixels."""
        phs = [p for p in (st.get("_photos") or []) if p.get("w")]
        if k >= len(phs) or phs[k]["w"] < box_w * self.page["dpi"] / 96.0 / 2.3:
            return None, ""
        ph = phs[k]
        g = B.bid("g")
        html = (f'<div class="{cls}" data-cat="figure" data-bid="{B.bid("f")}" data-group="{g}" data-nw="{ph["w"]}" '
                f'data-nh="{ph["h"]}" style="height:{h:.1f}px;background-image:url(\'file://{esc(ph["path"])}\')"></div>')
        cap = (f'<div class="mcap" data-cat="figure_caption" data-bid="{B.bid("c")}" data-group="{g}">'
               f'{words_html(ph.get("caption", ""), self.lang)}</div>') if ph.get("caption") else ""
        return html, cap

    def photo(self, h, cls="mphoto", topic=None, box_w=None):
        ph = A.pick(self.rng, "photo", topic=topic, editorial=True)
        if box_w and self.version >= 4:
            # enough pixels for the box (no heavily upscaled, posterised thumbnails)
            need = box_w * self.page["dpi"] / 96.0 / 2.3
            cands = [A.pick(self.rng, "photo", topic=topic, editorial=True) for _ in range(12)]
            cands = [c for c in cands if c and (c.get("w") or 0) >= need]
            ph = cands[0] if cands else None
        if not ph:
            return ""
        return (f'<div class="{cls}" data-cat="figure" data-bid="{B.bid("f")}" '
                f'style="height:{h:.1f}px;background-image:url(\'file://{esc(ph["path"])}\')"></div>')

    def build(self):
        r = self.rng
        W, H = self.W, self.H
        cp = C.corpus(self.lang)
        acc = r.choice(ACC)
        body_pt = r.uniform(8.8, 10.2)
        body_px = self.pt(body_pt)
        m = r.uniform(0.45, 0.7) * IN
        cw = W - 2 * m
        ncol = r.choice([2, 3, 3]) if W < 9.5 * IN else r.choice([3, 4])
        gap = r.uniform(0.16, 0.25) * IN
        mag = r.choice(C.locale(self.lang).get("magazines") or ["Magazine"])
        month = r.choice([C.L(self.lang, x, grp="news") for x in ["January", "March", "May", "June", "September",
                                                                  "October", "November", "December"]])
        pn = self.num(r.randint(6, 120))
        zones = []
        # folio
        fol_lab = mag
        if self.version >= 3 and r.random() < 0.6:
            fol_lab = C.L(self.lang, r.choice(["Feature", "Interview", "Portrait", "Analysis", "Lifestyle",
                                               "Special report"]), grp="magazine")
            self._fol_slot = True
        fol = [B.span_text(pn, self.lang, "page_number", cls="fpn"),
               B.span_text(f"{fol_lab} · {month} {self.num(r.randint(2019, 2026))}", self.lang, "footer", cls="fmag")]
        if r.random() < 0.5:
            fol = fol[::-1]
        zones.append(B.zone(m, H - m * 0.85, cw, body_px * 1.8, f'<div class="folio">{"".join(fol)}</div>'))
        sec = C.L(self.lang, r.choice(["Cover story", "Interview", "Feature", "Analysis", "Portrait", "Travel",
                                       "Lifestyle", "Review", "Column", "Special report"]), grp="magazine")
        if self.role == "photoessay" and self.version >= 3:
            res = self.build_photoessay(m, cw, acc, body_px, zones)
            if res is not None:
                return res
        fmt = "interview" if self.role == "interview" else None
        need_ph = 1 if (self.role == "opener" and self.version >= 5) else 0
        st = (self.feature(fmt, min_photos=need_ph) if self.role in ("opener", "body", "interview") else None) or self.story()
        topic = st.get("photo_topic")
        paras = list(st.get("body") or [])
        art = {"title": st.get("headline", "")}
        if st.get("section"):
            sec = st["section"]
        top = m
        flow = []
        top_from = None
        if self.role == "opener":
            ph_h = H * (r.uniform(0.32, 0.5) if (W < H or self.version < 4) else r.uniform(0.26, 0.36))
            full = r.random() < 0.45
            own = self.own_photo(st, 0, ph_h + (m if full else 0), W if full else cw,
                                 "mphoto full" if full else "mphoto")[0] if self.version >= 4 else None
            if self.version >= 6 and not own:
                # no picture that belongs to this story: a typographic opener (big display title under a thin
                # accent rule) -- neither a random photo nor an empty colour block that reads as a missing image
                own = f'<div style="height:{body_px * 0.5:.1f}px;background:{acc};width:28%"></div>'
                ph_h = body_px * 0.5
                full = False
            elif self.version >= 5 and not own:
                own = f'<div class="mphoto" style="height:100%;background:{acc}"></div>'
                ph_h = H * 0.12
            if full:
                zones.append(f'<div class="zone" style="left:0;top:0;width:{W:.1f}px;height:{ph_h + m:.1f}px">'
                             f'{own or self.photo(ph_h + m, "mphoto full", topic, box_w=W)}</div>')
            else:
                zones.append(B.zone(m, top + body_px * 2, cw, ph_h, own or self.photo(ph_h, topic=topic, box_w=cw)))
            head = [B.span_text(self.upper(sec), self.lang, "title", cls="msec", extra='data-sub="4"',
                                style=f"color:{acc}"),
                    B.heading(art["title"] or cp.sentence(r, 30, 80), self.lang, level=1, cls="mhl", kwn=False,
                              fit_lines="3"),
                    B.span_text(st.get("deck") or cp.sentence(r, 60, 180), self.lang, "text_block", cls="mdeck"),
                    B.span_text(f"{C.L(self.lang, 'By (byline prefix)', '', grp='news')} {C.person(self.lang, r)}".strip(),
                                self.lang, "text_block", cls="mby")]
            hy = (ph_h + m + body_px) if full else (top + body_px * 3 + ph_h)
            zones.append(B.zone(m, hy, cw, 0, "".join(head), zid="mhead", auto_h=True))
            top_from = "#mhead"
        elif self.role == "body":
            zones.append(B.zone(m, top, cw, body_px * 2, B.span_text(self.upper(sec), self.lang, "header", cls="msec",
                                                                     style=f"color:{acc}")))
            top += body_px * 2.4
        elif self.role == "interview":
            head = [B.span_text(self.upper(C.L(self.lang, "Interview", grp="magazine")), self.lang, "title",
                                cls="msec", extra='data-sub="4"', style=f"color:{acc}"),
                    B.heading(art["title"] or cp.sentence(r, 30, 80), self.lang, level=1, cls="mhl", kwn=False,
                              fit_lines="2")]
            if self.version >= 5:
                if st.get("deck"):
                    head.append(B.span_text(st["deck"], self.lang, "text_block", cls="mdeck"))
                if st.get("author"):
                    head.append(B.span_text(f'{C.L(self.lang, "Interview by", grp="magazine")} {st["author"]}',
                                            self.lang, "text_block", cls="mby"))
                ph_html, ph_cap = self.own_photo(st, 0, H * 0.24, cw * 0.42)
                if ph_html:
                    head = [f'<div class="ivw"><div class="ivt">{"".join(head)}</div>'
                            f'<div class="ivp" style="width:{cw * 0.42:.0f}px">{ph_html}{ph_cap}</div></div>']
            zones.append(B.zone(m, top, cw, 0, "".join(head), zid="mhead", auto_h=True))
            top_from = "#mhead"
        if self.role == "contents":
            return self.build_contents(m, cw, mag, month, acc, body_px)
        if self.role == "adpage":
            return self.build_adpage(m, cw, acc, body_px)
        if self.role == "briefs":
            zones.append(B.zone(m, top, cw, body_px * 3, B.heading(self.upper(C.L(self.lang, "In this issue", grp="magazine")),
                                                                   self.lang, level=1, cls="mhl small", kwn=False)))
            rows, cols = r.choice([(2, 2), (3, 2), (2, 3)])
            gy = top + body_px * 3.6
            cell_w = (cw - gap * (cols - 1)) / cols
            cell_h = (H - gy - m * 1.4 - gap * (rows - 1)) / rows
            k = 0
            for i in range(rows):
                for j in range(cols):
                    sb = self.story()
                    a = {"title": sb.get("headline", ""), "paras": sb.get("body") or [""], "topic": sb.get("photo_topic")}
                    x = m + (j if not self.rtl else cols - 1 - j) * (cell_w + gap)
                    y = gy + i * (cell_h + gap)
                    hid = f"bx{k}"
                    inner = self.photo(cell_h * 0.42, topic=a["topic"], box_w=cell_w) + B.heading(a["title"][:100], self.lang, level=3, cls="bh",
                                                                    kwn=False, fit_lines="2")
                    zones.append(B.zone(x, y, cell_w, 0, inner, zid=hid, auto_h=True))
                    zones.append(B.zone(x, y, cell_w, cell_h, "".join(B.para(p, self.lang, cls="mp", hyph=self.hyph())
                                                                       for p in a["paras"][:4]),
                                        flow=True, cols=1, top_from=f"#{hid}", gap_top=4, zorder=k + 1))
                    k += 1
            return self.spec("".join(zones), self.css(body_px, acc))
        # body flow with pull quote and inline photo
        first = True
        qa = self.role == "interview" and st.get("format") == "interview" and self.version >= 3
        for i, ptxt in enumerate(paras):
            if qa and not ptxt.startswith("\u0001"):
                flow += self.qa_blocks(ptxt, acc)
                continue
            if self.role == "interview" and i % 2 == 0 and i > 0 and not qa:
                sent = re.split(r"(?<=[.!?।۔؟])\s+", ptxt)[0]
                q = sent.rstrip(".।۔!") + ("؟" if self.lang in ("ar", "ur") else "?")
                flow.append(B.para(q, self.lang, cls="mq", split=False))
            if i == 3 and st.get("pull_quote") and r.random() < 0.7:
                flow.append(f'<div class="pq" style="border-color:{acc}">' +
                            B.span_text(self.L.quotes[0] + st["pull_quote"] + self.L.quotes[1], self.lang,
                                        "text_block", cls="pqt") + "</div>")
            if i == 5 and self.version >= 4 and r.random() < 0.6:
                html, cap = self.own_photo(st, 1 if self.role == "opener" else 0, cw / ncol * 0.75, cw / ncol)
                if html:
                    flow.append(f'<div class="inph" data-shrink="1">{html}{cap}</div>')
            elif i == 5 and st.get("caption") and r.random() < 0.5:
                g = B.bid("g")
                flow.append(f'<div class="inph" data-shrink="1">{self.photo(cw / ncol * 0.75, topic=topic)}'
                            f'<div class="mcap" data-cat="figure_caption" data-bid="{B.bid("c")}" data-group="{g}">'
                            f'{words_html(st["caption"], self.lang)}</div></div>')
            if ptxt.startswith("\u0001"):
                flow.append(B.heading(ptxt[1:], self.lang, level=3, cls="msub", style=f"color:{acc}"))
                continue
            cls = "mp" + (" first" if first else "") + (" dropcap" if first and self.typo["caps"] and r.random() < 0.5 else "")
            flow.append(B.para(ptxt, self.lang, cls=cls, hyph=self.hyph()))
            first = False
            if i == 8 and st.get("sidebar") and isinstance(st["sidebar"], dict):
                sb = st["sidebar"]
                items = "".join(B.para("• " + str(x), self.lang, cls="sbi", split=False) for x in (sb.get("items") or [])[:6])
                flow.append(f'<div class="sbox" data-float="1" style="border-color:{acc}">'
                            + B.heading(sb.get("title", ""), self.lang, level=4, cls="sbt", kwn=False,
                                        style=f"color:{acc}") + items + "</div>")
        if self.version >= 3 and self.role in ("body", "interview", "opener"):
            # a short story leaves room for the next one (placed by the engine only into genuinely free space)
            nx = self.story()
            hd = B.heading(nx.get("headline", ""), self.lang, level=2, cls="msub nexth", style=f"color:{acc}")
            flow.append(hd.replace(" data-cat=", ' data-filler="1" data-cat=', 1))
            for ptxt in (nx.get("body") or [])[:6]:
                flow.append(B.para(ptxt, self.lang, cls="mp", hyph=self.hyph(), extra='data-filler="1"'))
        zones.append(B.zone(m, top, cw, H - top - m * 1.4, "".join(flow), flow=True, cols=ncol, gap=f"{gap:.1f}px",
                            rule=("0.5px solid #999" if r.random() < 0.3 else None), zorder=1, top_from=top_from,
                            gap_top=body_px * 1.2, balance=True))
        return self.spec("".join(zones), self.css(body_px, acc))

    def build_contents(self, m, cw, mag, month, acc, body_px):
        r = self.rng
        W, H = self.W, self.H
        zones = []
        head = (B.span_text(mag, self.lang, "header", cls="cmag", style=f"color:{acc}") +
                B.heading(C.L(self.lang, "In this issue", grp="magazine"), self.lang, level=1, cls="mhl small", kwn=False))
        zones.append(B.zone(m, m, cw, 0, head, zid="chead", auto_h=True))
        items = []
        page = r.randint(4, 12)
        cur_sec = None
        for k in range(r.randint(9, 14)):
            st = self.story()
            sec = C.L(self.lang, r.choice(["Cover story", "Interview", "Feature", "Analysis", "Portrait", "Travel",
                                           "Lifestyle", "Review", "Column", "Special report"]), grp="magazine")
            if sec != cur_sec and r.random() < 0.5:
                items.append(B.heading(self.upper(sec), self.lang, level=3, cls="csec", style=f"color:{acc}"))
                cur_sec = sec
            teaser = (st.get("deck") or st.get("brief") or "")[:160]
            items.append(f'<div class="centry"><div class="cpg" style="color:{acc}" data-cat="text_block" '
                         f'data-bid="{B.bid("cp")}">{words_html(self.num(page), self.lang)}</div><div class="ctx">'
                         + B.heading(st.get("headline", "")[:110], self.lang, level=4, cls="cti", kwn=False)
                         + B.para(teaser, self.lang, cls="cte", split=False) + "</div></div>")
            page += r.randint(2, 9)
        photos = [p for p in (self.story().get("_photos") or [])]
        two = r.random() < 0.6 and photos
        colw = cw * (0.58 if two else 1.0)
        x = m if not self.rtl else m + cw - colw
        zones.append(B.zone(x, m, colw, H - 2.2 * m, "".join(items), flow=True, cols=1 if two else 2,
                            gap="0.25in", top_from="#chead", gap_top=body_px, zorder=1))
        if two:
            ph = photos[0]
            px = m + colw + 0.25 * IN if not self.rtl else m
            g = B.bid("g")
            zones.append(B.zone(px, m + body_px * 6, cw - colw - 0.25 * IN, H * 0.5,
                                f'<div class="mphoto" data-cat="figure" data-bid="{B.bid("f")}" data-group="{g}" '
                                f'style="height:{H * 0.42:.1f}px;background-image:url(\'file://{esc(ph["path"])}\')"></div>'
                                f'<div class="mcap" data-cat="figure_caption" data-bid="{B.bid("c")}" data-group="{g}">'
                                f'{words_html(ph.get("caption", ""), self.lang)}</div>'))
        self.meta["page_role"] = "contents"
        return self.spec("".join(zones), self.css(body_px, acc))

    def qa_blocks(self, ptxt, acc):
        """Interview paragraph 'Q: ...? A: ...' -> question (bold, accent) and answer paragraphs, labels in bold."""
        parts = [x.strip() for x in re.split(r"\n+", ptxt) if x.strip()]
        out = []
        for part in parts:
            for seg in re.split(r"(?<=[?؟])\s+(?=\S{1,14}\s?:\s)", part):
                m = re.match(r"^(\S{1,14}(?:\s\S{1,14})?)\s?:\s+(.+)$", seg, re.S)
                lab, txt = (m.group(1), m.group(2)) if m else ("", seg)
                is_q = txt.rstrip().endswith(("?", "؟")) or (lab and lab[:1].lower() in "qpfвसппপস" and len(lab) <= 3)
                body = (words_html(lab + ": ", self.lang, extra_cls="b") if lab else "") + words_html(txt, self.lang,
                                                                                                     hyph=self.hyph())
                cls = "mq" if is_q else "ma"
                out.append(f'<p class="{cls}" data-cat="text_block" data-bid="{B.bid()}" data-split="1">{body}</p>')
        return out

    def build_photoessay(self, m, cw, acc, body_px, zones):
        """Photo essay: headline + deck, 2-3 captioned photos in an asymmetric grid, short text column."""
        r = self.rng
        W, H = self.W, self.H
        st = self.feature(min_photos=2) or {}
        photos = [p for p in (st.get("_photos") or []) if (p.get("w") or 0) >= 700][:3]
        if len(photos) < 2:
            self.role = "opener"
            self.meta["page_role"] = "opener"
            return None
        dpr = self.page["dpi"] / 96.0
        head = (B.span_text(self.upper(st.get("section") or C.L(self.lang, "Photo essay", grp="magazine")), self.lang,
                            "title", cls="msec", extra='data-sub="4"', style=f"color:{acc}")
                + B.heading(st.get("headline", ""), self.lang, level=1, cls="mhl", kwn=False, fit_lines="2")
                + B.span_text(st.get("deck", ""), self.lang, "text_block", cls="mdeck"))
        zones.append(B.zone(m, m, cw, 0, head, zid="mhead", auto_h=True))
        big_w = cw * (r.uniform(0.58, 0.66) if len(photos) == 3 else 1.0)
        cells = []
        for i, ph in enumerate(photos):
            w = big_w if i == 0 else (cw - big_w - 0.2 * IN if len(photos) == 3 else cw)
            ar = ph["h"] / ph["w"]
            hgt = min(w * ar, H * (0.42 if i == 0 else 0.2))
            g = B.bid("g")
            cells.append(f'<div class="pe{i}"><div class="mphoto" data-cat="figure" data-bid="{B.bid("f")}" '
                         f'data-group="{g}" data-nw="{ph["w"]}" data-nh="{ph["h"]}" style="height:{hgt:.1f}px;'
                         f'background-image:url(\'file://{esc(ph["path"])}\')"></div>'
                         f'<div class="mcap" data-cat="figure_caption" data-bid="{B.bid("c")}" data-group="{g}">'
                         f'{words_html(ph.get("caption", ""), self.lang)}</div></div>')
        grid = (f'<div class="pegrid" style="grid-template-columns:{big_w:.0f}px 1fr">{"".join(cells)}</div>'
                if len(photos) == 3 else f'<div class="pestack">{"".join(cells)}</div>')
        zones.append(B.zone(m, m, cw, 0, grid, zid="pegrid", auto_h=True, top_from="#mhead", gap_top=body_px))
        paras = [p for p in (st.get("body") or []) if not str(p).startswith("\u0001")][:6]
        flow = "".join(B.para(p, self.lang, cls="mp", hyph=self.hyph()) for p in paras)
        zones.append(B.zone(m, m, cw, H - 2.4 * m, flow, flow=True, cols=r.choice([2, 3]), gap="0.2in",
                            top_from="#pegrid", gap_top=body_px, zorder=1, balance=True))
        self.meta["page_role"] = "photoessay"
        return self.spec("".join(zones), self.css(body_px, acc))

    def build_adpage(self, m, cw, acc, body_px):
        r = self.rng
        W, H = self.W, self.H
        pool = C.packs(self.lang, "ads")
        if self.version >= 5 and C.packs(self.lang, "ads2"):
            pool = C.packs(self.lang, "ads2")
        ad = r.choice(pool) if pool else {}
        photo = None
        if self.version >= 3:
            kind = str(ad.get("kind", "")).lower()
            topic = next((t for pat, t in AD_TOPIC if re.search(pat, kind)), None)
            if topic and r.random() < 0.75:
                cands = [A.pick(r, "photo", topic=topic, editorial=True) for _ in range(6)]
                cands = [c for c in cands if c and c.get("topic") == topic and (c.get("w") or 0) >= 700]
                photo = cands[0] if cands else None
        else:
            photo = A.pick(r, "photo")
        bg = r.choice(["#0f1c2e", "#ffffff", "#f4efe6", "#7a1020", "#103d2c"])
        fg = "#ffffff" if bg not in ("#ffffff", "#f4efe6") else "#111"
        ph_h = H * r.uniform(0.38, 0.55)
        dets = "".join(f'<div class="add">{words_html(str(d), self.lang)}</div>' for d in (ad.get("details") or [])[:4])
        html = (f'<div class="adpage" data-cat="abandon" data-bid="{B.bid("ad")}" style="background:{bg};color:{fg}">'
                + (f'<div class="adimg" style="height:{ph_h:.1f}px;background-image:url(\'file://{esc(photo["path"])}\')"></div>'
                   if photo else "")
                + f'<div class="adtx"><div class="adb" style="color:{acc if fg == "#111" else "#ffd166"}">'
                  f'{words_html(str(ad.get("brand", "")), self.lang)}</div>'
                  f'<div class="adhl">{words_html(str(ad.get("headline", "")), self.lang)}</div>'
                  f'<div class="adtg">{words_html(str(ad.get("tagline", "")), self.lang)}</div>'
                  f'<div class="adof">{words_html(str(ad.get("offer", "")), self.lang)}</div>{dets}'
                  f'<div class="adct">{words_html(" · ".join(x for x in (self.iso(str(ad.get("phone", "")).strip()), str(ad.get("web", "")).strip()) if x), self.lang)}</div>'
                  f'</div></div>')
        self.meta["page_role"] = "advertisement"
        return self.spec(B.zone(0, 0, W, H, html), self.css(body_px, acc))

    def css(self, body_px, acc):
        r = self.rng
        f_body = self.body_font(r.choice(["serif", "serif", "sans"]))
        f_head = self.fonts.stack(r.choice(["display", "serif", "sans"])) if not self.nastaliq else self.fonts.stack("nastaliq")
        f_sans = self.fonts.stack("sans")
        bw = self.bw("serif")
        lh = self.lh(r.uniform(1.18, 1.36))
        just = "justify" if r.random() < self.typo["justify"] else "start"
        return f"""
#page{{font-family:{f_body};font-size:{body_px:.2f}px;line-height:{lh};color:#1a1a1a;--bw:{bw};}}
.mp{{text-align:{just};text-indent:{r.choice([0, 1.0, 1.2])}em;margin-bottom:{r.choice([0, 0, 0.5])}em;}}
.mp.first{{text-indent:0;}}
.mp.dropcap::first-letter{{float:inline-start;font-size:3.3em;line-height:0.85;padding-inline-end:0.06em;color:{acc};font-weight:700;}}
.msec{{font-family:{f_sans};font-weight:800;letter-spacing:{self.ls(0.12)};font-size:{body_px * 1.05:.1f}px;}}
.mhl{{font-family:{f_head};font-size:{body_px * r.uniform(3.2, 4.6):.1f}px;line-height:{self.lh(1.05)};font-weight:{r.choice([700, 800, 400])};margin:0.15em 0 0.25em;letter-spacing:{self.ls(-0.015)};}}
.mhl.small{{font-size:{body_px * 2.2:.1f}px;}}
.mdeck{{font-family:{f_head};font-size:{body_px * 1.45:.1f}px;line-height:{self.lh(1.25)};color:#444;margin-bottom:0.4em;}}
.mby{{font-family:{f_sans};font-size:{body_px * 0.9:.1f}px;font-weight:700;color:{acc};}}
.mphoto{{width:100%;background-size:cover;background-position:center;}}
.mphoto.full{{height:100%;}}
.pq{{border-top:3px solid;border-bottom:3px solid;margin:0.6em 0;padding:0.4em 0;}}
.pqt{{font-family:{f_head};font-size:{body_px * 1.7:.1f}px;line-height:{self.lh(1.2)};font-style:{self.italic('serif')};}}
.inph{{margin:0.4em 0;}} .mcap{{font-family:{f_sans};font-size:{body_px * 0.82:.1f}px;color:#555;margin-top:0.2em;}}
.mq{{font-family:{f_sans};font-weight:700;color:{acc};margin:0.5em 0 0.2em;}}
.folio{{display:flex;justify-content:space-between;font-family:{f_sans};font-size:{body_px * 0.85:.1f}px;color:#555;border-top:0.6px solid #aaa;padding-top:2px;}}
.fpn{{font-weight:800;color:#111;}}
.msub{{font-family:{f_head};font-size:{body_px * 1.25:.1f}px;font-weight:700;margin:0.8em 0 0.3em;line-height:{self.lh(1.15)};}}
.sbox{{border-top:4px solid;background:#f5f2ec;padding:0.5em 0.6em;margin:0.6em 0;}}
.sbt{{font-family:{f_sans};font-size:{body_px * 1.05:.1f}px;margin:0 0 0.3em;}}
.sbi{{font-family:{f_sans};font-size:{body_px * 0.9:.1f}px;margin:0.15em 0;}}
.cmag{{font-family:{f_head};font-weight:800;font-size:{body_px * 1.4:.1f}px;letter-spacing:{self.ls(0.04)};}}
.csec{{font-family:{f_sans};font-weight:800;font-size:{body_px:.1f}px;margin:0.9em 0 0.2em;letter-spacing:{self.ls(0.08)};}}
.centry{{display:flex;gap:0.7em;margin:0.45em 0;align-items:flex-start;}}
.cpg{{font-family:{f_head};font-weight:800;font-size:{body_px * 2.0:.1f}px;line-height:1;min-width:1.6em;}}
.cti{{font-family:{f_head};font-size:{body_px * 1.15:.1f}px;font-weight:700;margin:0 0 0.15em;line-height:{self.lh(1.15)};}}
.cte{{font-size:{body_px * 0.9:.1f}px;color:#444;}}
.adpage{{width:100%;height:100%;display:flex;flex-direction:column;}}
.adimg{{width:100%;background-size:cover;background-position:center;}}
.adtx{{padding:6% 8%;flex:1;display:flex;flex-direction:column;justify-content:center;gap:0.4em;font-family:{f_sans};}}
.adb{{font-weight:800;font-size:{body_px * 2.0:.1f}px;letter-spacing:{self.ls(0.05)};}}
.adhl{{font-family:{f_head};font-weight:800;font-size:{body_px * 4.0:.1f}px;line-height:{self.lh(1.05)};}}
.adtg{{font-size:{body_px * 1.6:.1f}px;}}
.adof{{font-size:{body_px * 2.0:.1f}px;font-weight:700;}}
.add{{font-size:{body_px * 1.0:.1f}px;}}
.adct{{font-size:{body_px * 1.2:.1f}px;margin-top:0.6em;}}
.bh{{font-family:{f_head};font-size:{body_px * 1.4:.1f}px;font-weight:700;line-height:{self.lh(1.15)};margin:0.3em 0 0.2em;}}
.ma{{margin:0 0 0.45em;text-align:{just};}}
.ivw{{display:flex;gap:0.25in;align-items:flex-start;}} .ivt{{flex:1;}}
.nexth{{border-top:2px solid #222;padding-top:0.35em;margin-top:1em;font-size:{body_px * 1.6:.1f}px;}}
.pegrid{{display:grid;gap:0.2in;}} .pegrid .pe0{{grid-row:span 2;}}
.pestack>div{{margin-bottom:0.15in;}}
"""


def make(rng, lang, version=0):
    return MagazinePage(rng, lang, version).build()

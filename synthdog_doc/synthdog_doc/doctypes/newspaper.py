"""Newspaper pages: masthead / folio, modular grid (recursive guillotine split), article modules, briefs, ads."""
import datetime as _dt
import random
import re

from .. import imagepool as A
from .. import blocks as B
from .. import corpus as C
from ..doc import Doc
from ..geometry import IN, PT
from ..textkit import _TO_LATIN, esc, words_html

ACCENTS = ["#b0121b", "#0b3d91", "#c8102e", "#1a1a1a", "#00529b", "#8b0000", "#006a4e", "#d35400"]
# average glyph advance in em per script (rough; used only to match story length to module size)
DATE_SLOT = "QQPAGEDATEQQ"
CHAR_EM = {"latin": 0.47, "cyrillic": 0.52, "devanagari": 0.5, "bengali": 0.52, "arabic": 0.4}


def story_len(st):
    return sum(len(p) for p in st.get("body") or [])


def _date(s):
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def story_year(st):
    """Year the story is about: latest year mentioned in its text, not later than its crawl date."""
    if "_year" in st:
        return st["_year"]
    d = _date(st.get("date"))
    txt = "".join(_TO_LATIN.get(c, c) for c in " ".join(st.get("body") or [])[:5000])
    ys = [int(y) for y in re.findall(r"(?<!\d)(19[6-9]\d|20[0-2]\d)(?!\d)", txt)]
    lim = d.year if d else 2025
    ys = [y for y in ys if y <= lim]
    y = max(ys) if ys else (d.year if d else None)
    if not d and y is not None and y < 2005:
        y = None          # undated story whose latest mentioned year is historical: no usable dating signal
    st["_year"] = y
    return st["_year"]


def fit_photo(ph, w, want_h, dpr, max_up=2.6, min_vis=0.55):
    """Height for a background-size:cover photo box of width w (CSS px) close to want_h such that the photo is
    cropped to at least `min_vis` of its height/width and upscaled at most `max_up` x; None if impossible."""
    nw, nh = (ph or {}).get("w") or 0, (ph or {}).get("h") or 0
    if not nw or not nh:
        return want_h
    ar = nh / nw
    lo, hi = w * ar * min_vis, w * ar / min_vis      # crop limits (vertical / horizontal)
    hgt = min(max(want_h, lo), hi)
    up = max(w / nw, hgt / nh) * dpr
    if up > max_up:
        return None
    return hgt


class Module:
    def __init__(self, c0, c1, y0, y1):
        self.c0, self.c1, self.y0, self.y1 = c0, c1, y0, y1

    @property
    def span(self):
        return self.c1 - self.c0


def partition(rng, c0, c1, y0, y1, depth, min_h, ncols, out, front=False):
    span, h = c1 - c0, y1 - y0
    can_v = span >= 2
    can_h = h >= 2 * min_h
    p_leaf = 0.0 if depth == 0 else min(0.8, 0.02 + 0.16 * depth + (0.3 if span <= 2 and h < 2.5 * min_h else 0))
    if (not can_v and not can_h) or rng.random() < p_leaf:
        out.append(Module(c0, c1, y0, y1))
        return
    if depth == 0:
        # top band (lead story area) vs rest
        t = rng.uniform(0.38, 0.55) if front else rng.uniform(0.3, 0.6)
        ym = y0 + h * t
        top_lead = rng.randint(max(2, ncols - 3), ncols)
        if top_lead < ncols:
            if rng.random() < 0.5:
                out.append(Module(c0, c0 + top_lead, y0, ym))
                partition(rng, c0 + top_lead, c1, y0, ym, depth + 2, min_h, ncols, out)
            else:
                partition(rng, c0, c1 - top_lead, y0, ym, depth + 2, min_h, ncols, out)
                out.append(Module(c1 - top_lead, c1, y0, ym))
        else:
            out.append(Module(c0, c1, y0, ym))
        partition(rng, c0, c1, ym, y1, depth + 1, min_h, ncols, out)
        return
    vertical = can_v and (not can_h or rng.random() < (0.55 if span >= 3 else 0.35))
    if vertical:
        k = rng.randint(1, span - 1)
        partition(rng, c0, c0 + k, y0, y1, depth + 1, min_h, ncols, out)
        partition(rng, c0 + k, c1, y0, y1, depth + 1, min_h, ncols, out)
    else:
        ym = y0 + h * rng.uniform(0.35, 0.65)
        partition(rng, c0, c1, y0, ym, depth + 1, min_h, ncols, out)
        partition(rng, c0, c1, ym, y1, depth + 1, min_h, ncols, out)


class NewspaperPage(Doc):
    def __init__(self, rng, lang, version=0):
        super().__init__("newspaper", lang, rng, version)
        self.front = rng.random() < 0.3
        self.used = set()
        self.year = None
        self.page_date = None
        self._dated = False
        self.story_dates = []
        self.story_years = []
        cs = list(self.L.countries[:3]) or [""]
        self.country = rng.choices(cs, weights=[0.7, 0.2, 0.1][:len(cs)])[0]
        self.ad_brands = set()
        self.lead = self.next_story(longest_of=10)   # fixes the page date / year
        self.meta.update(page_role="front" if self.front else "inside")

    def style(self):
        r = self.rng
        s = {}
        self.ncols = {"Broadsheet": r.choice([6, 6, 7]), "Broadsheet2": r.choice([6, 6, 5]),
                      "Berliner": r.choice([5, 6, 6]), "Tabloid": r.choice([5, 5, 4])}.get(self.page["paper"], 5)
        s["body_pt"] = r.uniform(8.2, 9.6)
        s["lh"] = r.uniform(1.1, 1.22)
        s["gutter"] = r.uniform(0.13, 0.2) * IN
        s["margin"] = r.uniform(0.35, 0.6) * IN
        s["rules"] = r.random() < 0.55
        s["hrules"] = r.random() < 0.8
        s["accent"] = r.choice(ACCENTS)
        s["head_role"] = r.choice(["display", "serif", "display", "sans"])
        s["head_weight"] = r.choice([700, 700, 800, 600])
        s["kicker"] = r.random() < 0.55
        s["justify"] = "justify" if r.random() < (self.typo["justify"] + 0.1) else "start"
        s["indent"] = r.choice([0.8, 1.0, 1.2, 0.0])
        s["dropcap"] = self.typo["caps"] and r.random() < 0.35
        s["gray_photos"] = r.random() < 0.45
        s["boxed_p"] = r.uniform(0.0, 0.2)
        return s

    # ----------------------------------------------------------------- pieces
    def masthead(self, x, y, w):
        r, s = self.rng, self.s
        name = r.choice(C.locale(self.lang).get("newspapers") or ["Daily News"])
        date = DATE_SLOT          # filled in by build() once every story on the page is known
        self._weekday = False
        price = f"{C.L(self.lang, 'Price', grp='news')}: {self.num(r.choice(['2', '1.50', '25', '10', '3', '100', '15']))}"
        issue = f"{C.L(self.lang, 'Year', grp='news')} {self.num(r.randint(12, 140))} · {C.L(self.lang, 'Issue', grp='news')} {self.num(r.randint(1000, 40000))}"
        name_px = self.pt(r.uniform(44, 78)) * (0.85 if len(name) > 18 else 1.0)
        fam = self.fonts.stack("display") if not self.nastaliq else self.fonts.stack("nastaliq")
        top_line = B.span_text(f"{issue}", self.lang, "header", cls="mh-meta")
        nm = (f'<div class="mh-name" data-cat="title" data-sub="1" data-bid="{B.bid("h")}" data-fit-lines="1" '
              f'style="font-family:{esc(fam)};font-size:{name_px:.1f}px;">{words_html(name, self.lang)}</div>')
        bar = (f'<div class="mh-bar">{B.span_text(date, self.lang, "header", cls="mh-date")}'
               f'{B.span_text(price, self.lang, "header", cls="mh-price")}</div>')
        teasers = ""
        if r.random() < 0.6:
            heads = [self.next_story().get("headline", "") for _ in range(3)]
            items = "".join(f'<div class="teaser">{B.span_text(h, self.lang, "text_block", cls="teaser-t")}</div>'
                            for h in heads)
            teasers = f'<div class="teasers">{items}</div>'
        html = f'<div class="mh">{top_line}{nm}{bar}{teasers}</div>'
        return B.zone(x, y, w, 0, html, zid="mast", auto_h=True, zorder=-5)

    def folio(self, x, y, w):
        r = self.rng
        name = r.choice(C.locale(self.lang).get("newspapers") or ["Daily News"])
        sec = C.L(self.lang, self.lead.get("section") or "National", grp="news")
        date = DATE_SLOT
        self._weekday = r.random() < 0.5
        pn = self.num(r.randint(2, 32))
        items = [B.span_text(pn, self.lang, "page_number", cls="fo-pn"),
                 B.span_text(sec, self.lang, "header", cls="fo-sec"),
                 B.span_text(f"{name} · {date}", self.lang, "header", cls="fo-date")]
        if r.random() < 0.5:
            items = items[::-1]
        html = f'<div class="folio">{"".join(items)}</div>'
        return B.zone(x, y, w, 0, html, zid="mast", auto_h=True, zorder=-5)

    def next_story(self, min_chars=None, longest_of=None):
        """Coherent article package (LLM-edited headline/deck/caption over verbatim national-web body).

        Stories on one page come from the same year as the page date (taken from the lead story's crawl date).
        min_chars: prefer a story long enough to fill its module (editors cut stories to fit, they never leave
        three empty columns); longest_of: take the longest of n random candidates.
        """
        pool = C.packs(self.lang, "news")
        if pool and self.version >= 5:
            return self._next_story_v5(pool, min_chars, longest_of)
        if pool:
            if not self._dated:
                self._dated = True
                cands = [self.rng.choice(pool) for _ in range(longest_of or 1)]
                st = max(cands, key=story_len)
                self.year = str(st.get("date") or "")[:4] or None
                self.page_date = st.get("date") or (f"{self.rng.randint(2016, 2024)}-{self.rng.randint(1, 12):02d}-"
                                                    f"{self.rng.randint(1, 28):02d}")
                self.used.add(id(st))
                self._note_date(st)
                return st
            d0 = _date(self.page_date)
            close = [p for p in pool if id(p) not in self.used and d0 and _date(p.get("date"))
                     and abs((_date(p.get("date")) - d0).days) <= 45]
            same = [p for p in pool if str(p.get("date") or "")[:4] == self.year and id(p) not in self.used]
            if len(close) >= 3:
                same = close
            near = [p for p in pool if id(p) not in self.used and str(p.get("date") or "")[:4]
                    and self.year and abs(int(str(p.get("date"))[:4]) - int(self.year)) <= 1]
            cands = same or near or [p for p in pool if id(p) not in self.used] or pool
            if min_chars:
                # same-year stories first, then +-1 year, then anything unused
                for group in (same, near, [p for p in pool if id(p) not in self.used]):
                    long_ = [p for p in group if story_len(p) >= min_chars]
                    if long_:
                        cands = long_
                        break
                else:
                    cands = sorted(cands, key=story_len)[-3:]
            elif longest_of:
                cands = [max((self.rng.choice(cands) for _ in range(longest_of)), key=story_len)]
            st = self.rng.choice(cands)
            self.used.add(id(st))
            self._note_date(st)
            return st
        a = C.corpus(self.lang).news_article(self.rng)
        return {"headline": a["title"], "body": a["paras"], "deck": "", "caption": "", "section": "",
                "kicker": "", "photo_topic": None, "brief": a["paras"][0][:200]}

    def _next_story_v5(self, pool, min_chars, longest_of):
        unused = [p for p in pool if id(p) not in self.used]
        if not self._dated:
            self._dated = True
            cands = [self.rng.choice(pool) for _ in range(longest_of or 1)]
            with_ph = [c for c in cands if c.get("_photos")]
            if with_ph and self.rng.random() < 0.85:
                cands = with_ph      # the lead story is the one with a (relevant) picture
            dated = [c for c in cands if story_year(c)]
            st = max(dated or cands, key=story_len)
            self.year = story_year(st) or self.rng.randint(2016, 2023)
            d = _date(st.get("date"))
            if d and d.year == self.year:
                self.issue = d + _dt.timedelta(days=self.rng.choice([0, 1, 1]))
            else:   # crawled years later: date the issue inside the year the story is about
                self.issue = _dt.date(self.year or 2020, self.rng.randint(1, 12), self.rng.randint(1, 28))
            self.used.add(id(st))
            return st
        same = [p for p in unused if story_year(p) == self.year]
        sec = (self.lead or {}).get("section") if getattr(self, "lead", None) else None
        if sec and not self.front:
            # inside pages are section pages: stories of the folio's section first
            same_sec = [p for p in same if p.get("section") == sec]
            if same_sec and self.rng.random() < 0.8:
                same = same_sec
        near = [p for p in unused if story_year(p) and self.year and 0 < self.year - story_year(p) <= 1]
        groups = [g for g in (same, near) if g] or [unused or pool]
        cands = groups[0]
        if min_chars:
            for g in groups:
                long_ = [p for p in g if story_len(p) >= min_chars]
                if long_:
                    cands = long_
                    break
            else:
                cands = sorted(cands, key=story_len)[-3:]
        elif longest_of:
            cands = [max((self.rng.choice(cands) for _ in range(longest_of)), key=story_len)]
        st = self.rng.choice(cands)
        self.used.add(id(st))
        return st

    def _note_date(self, st):
        d = _date(st.get("date"))
        if d:
            self.story_dates.append(d)
        # years the story itself talks about (crawl dates can be older than the events reported)
        txt = " ".join(st.get("body") or [])[:4000]
        txt = "".join(_TO_LATIN.get(c, c) for c in txt)
        ys = [int(y) for y in re.findall(r"(?<!\d)(19[5-9]\d|20[0-2]\d)(?!\d)", txt) if int(y) <= 2025]
        if ys:
            self.story_years.append(max(ys))

    def final_date(self):
        """Issue date: the day after the newest story on the page (a page cannot report events after its date)."""
        if self.version >= 5 and getattr(self, "issue", None):
            return self.issue.isoformat()
        ds = [d for d in self.story_dates if d]
        if not ds:
            return self.page_date or "2023-05-17"
        d = max(ds) + _dt.timedelta(days=self.rng.choice([0, 1, 1]))
        y = max(self.story_years or [0])
        if y > d.year:   # a story reports events of a later year than its crawl date: the issue cannot be older
            d = _dt.date(y, self.rng.randint(max(1, 6 if y == 2025 else 1), 12), self.rng.randint(1, 28))
        return d.isoformat()

    def article(self, m, x, y, w, h, rank, zorder, first_row=False, no_split=False):
        """Return list of zone HTML strings for one article module (one story, everything on-topic)."""
        r, s = self.rng, self.s
        span = m.span
        body_px = self.pt(s["body_pt"])
        head_est = self.pt(30 if rank == 0 else 20) * 2.4 + body_px * 1.3 * (3 if rank == 0 else 1.5)
        cap = self.capacity(w, max(h - head_est, h * 0.4), span)
        st = self.lead if rank == 0 else self.next_story(min_chars=cap * r.uniform(0.7, 0.95))
        paras = list(st.get("body") or [])
        fill_ratio = story_len(st) / max(cap, 1.0)   # < 1: the story alone would underfill the module
        # Editors size modules to stories: a story far too short for its module keeps only the part it can fill
        # and the rest of the module becomes another story (below it, or beside it in a wide module).
        rest = None
        gap_v = s["body_pt"] * PT * 1.1
        if fill_ratio < 0.62 and not no_split:
            keep = max(0.45, min(0.85, fill_ratio * 1.2))
            if span >= 4 and r.random() < 0.5:
                k = max(2, min(span - 1, round(span * keep)))
                wk = k * (w - (span - 1) * s["gutter"]) / span + (k - 1) * s["gutter"]
                if (span - k) >= 1:
                    rx = x + wk + s["gutter"] if not self.rtl else x
                    if self.rtl:
                        x = x + w - wk
                    rest = (Module(0, span - k, 0, 1), rx, y, w - wk - s["gutter"], h)
                    w, span, m = wk, k, Module(0, k, 0, 1)
            elif h * (1 - keep) - gap_v >= 2.2 * IN and h * keep >= 2.4 * IN:
                h_new = h * keep
                rest = (Module(0, span, 0, 1), x, y + h_new + gap_v * 0.5, w, h - h_new - gap_v * 0.5)
                h = h_new - gap_v * 0.5
            if rest:
                head_est = self.pt(30 if rank == 0 else 20) * 2.4 + body_px * 1.3 * (3 if rank == 0 else 1.5)
                cap = self.capacity(w, max(h - head_est, h * 0.4), span)
                fill_ratio = story_len(st) / max(cap, 1.0)
        head = st.get("headline") or (paras[0][:80] if paras else "")
        hid = f"ah{zorder}"
        lead = rank == 0
        hp = {0: r.uniform(30, 44), 1: r.uniform(22, 30), 2: r.uniform(17, 23)}.get(min(rank, 2))
        hp *= (1.0 if span >= 3 else (0.82 if span == 2 else 0.66))
        if span == 1:
            hp = min(hp, 18)
        head_px = self.pt(hp)
        parts = []
        if s["kicker"] and st.get("kicker") and r.random() < 0.6:
            parts.append(B.span_text(self.upper(st["kicker"]), self.lang, "title", cls="kicker",
                                     extra='data-sub="4" data-opt="1"'))
        parts.append(B.heading(head, self.lang, level=2 if lead else 3, cls="hl", kwn=False,
                               style=f"font-size:{head_px:.1f}px", fit_lines="3" if span >= 2 else "4"))
        if st.get("subhead") and lead and r.random() < 0.5:
            parts.append(B.span_text(st["subhead"], self.lang, "title", cls="subhl", extra='data-sub="3"'))
        if st.get("deck") and (lead or (span >= 2 and r.random() < 0.45)):
            parts.append(B.span_text(st["deck"], self.lang, "text_block", cls="deck", extra='data-opt="4"'))
        if r.random() < 0.65:
            by = f"{C.L(self.lang, 'By (byline prefix)', '', grp='news')} {C.person(self.lang, r)}".strip()
            if st.get("dateline") and r.random() < 0.6:
                by += f" | {st['dateline']}"
            parts.append(B.span_text(by, self.lang, "text_block", cls="byline", extra='data-opt="3"'))
        photos = list(st.get("_photos") or [])
        dpr = self.page["dpi"] / 96.0
        maxh = h * (0.66 if lead else 0.56)          # head (title/deck/photo) leaves room for body text
        photo_top = bool(photos) and (lead or (span >= 2 and r.random() < 0.55)) and h > 3.0 * IN
        if photo_top:
            ph, ph_h = None, None
            for cand in list(photos):
                ar = (cand["h"] / cand["w"]) if cand.get("w") else 0.66
                want = min(h * (0.42 if lead else 0.3), w * min(0.72 if lead else 0.55, max(0.42, ar)))
                if fill_ratio < 0.9:
                    # short story: a bigger picture takes the space the text cannot fill
                    want = max(want, min((h - head_est) * (1.0 - fill_ratio) * 0.9, h * (0.58 if lead else 0.5),
                                         w * 0.9))
                want = min(want, maxh - head_est)
                hh = fit_photo(cand, w, want, dpr) if want > 1.1 * IN else None
                if hh and hh <= maxh - head_est * 0.8:
                    ph, ph_h = cand, hh
                    photos.remove(cand)
                    break
            if ph:
                g = B.bid("g")
                img = (f'<div class="photo" data-cat="figure" data-bid="{B.bid("f")}" data-group="{g}" '
                       f'data-nw="{ph["w"]}" data-nh="{ph["h"]}" '
                       f'style="height:{ph_h:.1f}px;background-image:url(\'file://{esc(ph["path"])}\')"></div>')
                cap = ph.get("caption") or ""
                credit = f" ({C.L(self.lang, 'Photo', grp='news')}: {C.person(self.lang, r).split()[-1]})" \
                    if r.random() < 0.4 else ""
                capdiv = (f'<div class="pcap" data-cat="figure_caption" data-bid="{B.bid("c")}" data-group="{g}">'
                          f'{words_html(cap + credit, self.lang)}</div>') if cap else ""
                parts.append(f'<div class="photowrap" data-opt="2">{img}{capdiv}</div>')
        boxed = r.random() < s["boxed_p"]
        cls = "art" + (" boxed" if boxed else "") + (" toprule" if s["hrules"] else "")
        zones = [B.zone(x, y, w, 0, "".join(parts), cls=cls + " ahead", zid=hid, auto_h=True, zorder=zorder,
                        top_from="#mast" if first_row else None, gap_top=body_px * 0.8)
                 .replace('class="zone', f'data-maxh="{maxh:.0f}" class="zone', 1)]
        flow = []
        first = True
        inline_photo = bool(photos) and h > 2.6 * IN and r.random() < 0.35
        if inline_photo:
            colw = (w - (span - 1) * s["gutter"]) / span
            ph = photos.pop(0)
            ih = fit_photo(ph, colw, min(h * 0.33, colw * 0.75), dpr) if ph else None
            if ph and ih:
                g = B.bid("g")
                img = (f'<div class="photo" data-cat="figure" data-bid="{B.bid("f")}" data-group="{g}" '
                       f'data-nw="{ph["w"]}" data-nh="{ph["h"]}" style="height:{ih:.1f}px;'
                       f'background-image:url(\'file://{esc(ph["path"])}\')"></div>')
                capdiv = (f'<div class="pcap" data-cat="figure_caption" data-bid="{B.bid("c")}" data-group="{g}">'
                          f'{words_html(ph.get("caption") or "", self.lang)}</div>') if ph.get("caption") else ""
                flow.append(f'<div class="photowrap" data-place="top" data-col="{r.randint(0, span - 1)}">'
                            f'{img}{capdiv}</div>')
        pq = st.get("pull_quote")
        for i, ptxt in enumerate(paras):
            if i == 2 and pq and span >= 2 and r.random() < 0.35:
                flow.append(f'<div class="npq">' + B.span_text(self.L.quotes[0] + pq + self.L.quotes[1], self.lang,
                                                              "text_block", cls="npqt") + "</div>")
            cls = "np" + (" first" if first else "") + (" dropcap" if first and s["dropcap"] and lead else "")
            flow.append(B.para(ptxt, self.lang, cls=cls, hyph=self.hyph()))
            first = False
        # filler briefs: placed by the engine only into space the story leaves free (never cause overflow)
        for _ in range(3 if fill_ratio < 1.2 else 1):
            fs = self.next_story()
            hd = B.heading(fs.get("headline", "")[:100], self.lang, level=4, cls="bh fill-h")
            flow.append(hd.replace(" data-cat=", ' data-filler="1" data-cat=', 1))
            flow.append(B.para(fs.get("brief") or (fs.get("body") or [""])[0][:300], self.lang, cls="np first",
                               split=False, hyph=self.hyph(), extra='data-filler="1"'))
        gap = s["gutter"]
        bz = B.zone(x, y, w, h, "".join(flow), flow=True, cols=span, gap=f"{gap:.1f}px",
                    rule=("0.6px solid #777" if s["rules"] else None), zorder=zorder + 0.5,
                    top_from=f"#{hid}", gap_top=body_px * 0.35, cls="artbody" + (" boxed" if boxed else ""), minhead=1)
        if r.random() < 0.7:
            # stories that do not fit jump to an inside page (the engine adds this line only on overflow)
            jump = f"{C.L(self.lang, 'Continued on page', grp='news')} {self.num(r.randint(2, 24))}"
            bz = bz.replace('class="zone flow', f'data-jump="{esc(words_html(jump, self.lang))}" class="zone flow', 1)
        zones.append(bz)
        if rest:
            rm, rx, ry, rw, rh = rest
            zones += self.article(rm, rx, ry, rw, rh, max(rank, 1) + 1, zorder + 2,
                                  first_row=first_row and abs(ry - y) < 1, no_split=True)
        return zones

    def capacity(self, w, h, span):
        """Rough number of body characters a text area of w x h px with `span` columns holds."""
        s = self.s
        body_px = self.pt(s["body_pt"])
        lh_px = body_px * self.lh(s["lh"])
        colw = (w - (span - 1) * s["gutter"]) / max(span, 1)
        cpl = colw / (body_px * CHAR_EM.get(self.L.script, 0.5))
        return span * (h / lh_px) * cpl

    def ad(self, x, y, w, h, zorder):
        r = self.rng
        pool = C.packs(self.lang, "ads")
        if self.version >= 5:
            # ads of the paper's own country (currency, phone format, addresses), no repeats on a page
            ads2 = [a for a in C.packs(self.lang, "ads2") if a.get("country") == self.country
                    and a.get("brand") not in self.ad_brands]
            pool = ads2 or pool
        ad = r.choice(pool) if pool else {"brand": "Company", "headline": "", "tagline": "", "offer": "",
                                          "details": [], "phone": "", "web": ""}
        self.ad_brands.add(ad.get("brand"))
        bg = r.choice(["#fff", "#fff7d6", "#eef5ff", "#111", "#b0121b", "#0b3d91"])
        fg = "#fff" if bg in ("#111", "#b0121b", "#0b3d91") else "#111"
        acc = "#ffd400" if fg == "#fff" else r.choice(ACCENTS)
        lines = "".join(f'<div class="ad-d">{words_html(str(d), self.lang)}</div>' for d in (ad.get("details") or [])[:3])
        html = (f'<div class="ad" data-cat="abandon" data-fitbox="0.5" data-bid="{B.bid("ad")}" '
                f'style="background:{bg};color:{fg}">'
                f'<div class="ad-co" style="color:{acc}">{words_html(str(ad.get("brand", "")), self.lang)}</div>'
                f'<div class="ad-h">{words_html(str(ad.get("headline", "")), self.lang)}</div>'
                f'<div class="ad-l">{words_html(str(ad.get("tagline", "")), self.lang)}</div>'
                f'<div class="ad-o">{words_html(str(ad.get("offer", "")), self.lang)}</div>{lines}'
                f'<div class="ad-ph">{words_html(self.iso(str(ad.get("phone", ""))), self.lang)}</div>'
                f'<div class="ad-w">{words_html(str(ad.get("web", "")), self.lang)}</div></div>')
        return B.zone(x, y, w, h, html, zorder=zorder, cls="adz", style="overflow:hidden")

    def briefs(self, x, y, w, h, zorder, first_row=False):
        r = self.rng
        cp = C.corpus(self.lang)
        title = C.L(self.lang, r.choice(["Inside", "Today", "In brief", "World", "Local"]), grp="news")
        items = []
        for _ in range(9):
            st = self.next_story()
            items.append(B.heading(st.get("headline", "")[:90], self.lang, level=4, cls="bh"))
            items.append(B.para(st.get("brief") or (st.get("body") or [""])[0], self.lang, cls="np first",
                                hyph=self.hyph()))
        hid = f"bh{zorder}"
        z1 = B.zone(x, y, w, 0, B.heading(self.upper(title), self.lang, level=3, cls="brief-title", kwn=False),
                    zid=hid, auto_h=True, zorder=zorder, cls="art toprule",
                    top_from="#mast" if first_row else None, gap_top=8)
        z2 = B.zone(x, y, w, h, "".join(items), flow=True, cols=1, zorder=zorder + 0.5, top_from=f"#{hid}",
                    gap_top=4, minhead=1)
        return [z1, z2]

    # ----------------------------------------------------------------- page
    def build(self):
        r = self.rng
        self.s = s = self.style()
        W, H = self.W, self.H
        m = s["margin"]
        cw = W - 2 * m
        colw = (cw - s["gutter"] * (self.ncols - 1)) / self.ncols
        zones = []
        zones.append(self.masthead(m, m, cw) if self.front else self.folio(m, m * 0.8, cw))
        # body region: estimate masthead height to plan modules (engine re-anchors exact top)
        top = m + ((2.1 if self.front else 0.33) * IN)
        bottom = H - m
        # real pages carry many stories: resample the guillotine split until the module count is in range
        lo, hi = (5, 11) if self.page["paper"] != "Tabloid" else (4, 8)
        best = None
        for _ in range(40):
            mods = []
            partition(r, 0, self.ncols, top, bottom, 0, 1.35 * IN, self.ncols, mods, front=self.front)
            areas = sorted(((q.c1 - q.c0) * (q.y1 - q.y0) for q in mods), reverse=True)
            tot = sum(areas)
            ok = lo <= len(mods) <= hi and (len(areas) < 2 or areas[1] / tot <= 0.3)
            if ok:
                best = mods
                break
            if best is None or abs(len(mods) - (lo + hi) / 2) < abs(len(best) - (lo + hi) / 2):
                best = mods
        mods = best
        # reading order of modules: top-to-bottom, then by x (mirrored for RTL)
        mods.sort(key=lambda q: (round(q.y0, 1), (-q.c0 if self.rtl else q.c0)))
        rank_order = sorted(range(len(mods)), key=lambda i: -(mods[i].span * (mods[i].y1 - mods[i].y0)))
        rank = {i: k for k, i in enumerate(rank_order)}
        gap_v = s["body_pt"] * PT * 1.1
        n_ads = 0
        for i, md in enumerate(mods):
            c0 = (self.ncols - md.c1) if self.rtl else md.c0
            x = m + c0 * (colw + s["gutter"])
            w = md.span * colw + (md.span - 1) * s["gutter"]
            y = md.y0 + (gap_v * 0.5 if md.y0 > top + 1 else 0)
            h = md.y1 - y - gap_v * 0.5
            zo = 10 + i * 10   # room for sub-modules created by article() splits (zorder + 2, + 4, ...)
            area_frac = (w * h) / (cw * (bottom - top))
            fr = md.y0 <= top + 1
            if md.span == 1 and h > 5 * IN and r.random() < 0.4:
                zones += self.briefs(x, y, w, h, zo, first_row=fr)
            elif (area_frac < 0.12 and md.span <= max(2, self.ncols // 2) and n_ads < 2 and r.random() < 0.35
                  and not fr):
                n_ads += 1
                zones.append(self.ad(x, y, w, h, zo))
            else:
                zones += self.article(md, x, y, w, h, rank[i], zo, first_row=fr)
        body = "".join(zones)
        # issue date = newest story on the page (+0/1 day); written into masthead / folio now
        iso = self.final_date()
        self.meta["issue_date"] = iso
        date_html = words_html(self.num(C.date_text(self.lang, iso, with_weekday=self._weekday)), self.lang)
        body = re.sub(r'<span class="w">' + DATE_SLOT + r'( ?)</span>', lambda mm: date_html + mm.group(1), body)
        return self.spec(body, self.css())

    def css(self):
        s = self.s
        body_px = self.pt(s["body_pt"])
        f_body = self.body_font("serif")
        f_head = self.fonts.stack(s["head_role"]) if not self.nastaliq else self.fonts.stack("nastaliq")
        f_sans = self.fonts.stack("sans")
        bw = self.bw("serif")
        lh = self.lh(s["lh"])
        acc = s["accent"]
        gray = "filter:grayscale(1) contrast(1.05);" if s["gray_photos"] else ""
        return f"""
#page{{font-family:{f_body};font-size:{body_px:.2f}px;line-height:{lh};color:#151515;--bw:{bw};}}
.np{{text-align:{s['justify']};text-indent:{s['indent']}em;}}
.np.first{{text-indent:0;}}
.np.dropcap::first-letter{{float:inline-start;font-size:3.1em;line-height:0.85;padding-inline-end:0.06em;margin-top:0.05em;font-weight:700;}}
.hl{{font-family:{f_head};font-weight:{s['head_weight']};line-height:{self.lh(1.06)};margin:0.1em 0 0.25em;letter-spacing:{self.ls(-0.01)};}}
.kicker{{font-family:{f_sans};font-weight:700;font-size:{body_px * 0.95:.1f}px;color:{acc};letter-spacing:{self.ls(0.04)};margin-bottom:0.15em;}}
.deck{{font-family:{f_head};font-size:{body_px * 1.35:.1f}px;line-height:{self.lh(1.2)};margin-bottom:0.35em;color:#333;}}
.byline{{font-family:{f_sans};font-size:{body_px * 0.85:.1f}px;font-weight:600;margin-bottom:0.35em;color:#444;}}
.photo{{width:100%;background-size:cover;background-position:center 32%;{gray}}}
.photowrap{{margin:0.1em 0 0.4em;}}
.pcap{{font-family:{f_sans};font-size:{body_px * 0.82:.1f}px;line-height:{self.lh(1.18)};color:#333;margin-top:0.25em;}}
.subhl{{font-family:{f_head};font-weight:600;font-size:{body_px * 1.6:.1f}px;line-height:{self.lh(1.15)};margin:0 0 0.25em;}}
.npq{{border-top:2px solid {acc};border-bottom:2px solid {acc};margin:0.4em 0;padding:0.3em 0;}}
.npqt{{font-family:{f_head};font-size:{body_px * 1.45:.1f}px;line-height:{self.lh(1.2)};font-style:{self.italic('serif')};}}
.jump{{font-family:{f_sans};font-size:{body_px * 0.85:.1f}px;font-style:{self.italic('sans')};text-align:end;margin-top:0.2em;}}
.xhead{{font-family:{f_head};font-weight:700;font-size:{body_px * 1.1:.1f}px;margin:0.5em 0 0.2em;line-height:{self.lh(1.15)};}}
.art.toprule{{border-top:{'2px' if self.rng.random() < 0.5 else '1px'} solid #222;padding-top:0.3em;}}
.art.boxed,.artbody.boxed{{background:{self.rng.choice(['#f3efe6', '#eef3f8', '#f7f1f1'])};}}
.mh{{text-align:center;border-bottom:3px double #111;padding-bottom:0.3em;}}
.mh-name{{font-weight:800;line-height:1.05;color:{acc if self.rng.random() < 0.4 else '#111'};margin:0.1em 0;}}
.mh-meta{{font-family:{f_sans};font-size:{body_px * 0.9:.1f}px;color:#333;}}
.mh-bar{{display:flex;justify-content:space-between;border-top:1px solid #111;border-bottom:1px solid #111;padding:0.15em 0.2em;font-family:{f_sans};font-size:{body_px:.1f}px;}}
.teasers{{display:flex;gap:1em;margin-top:0.3em;}}
.teaser{{flex:1;border-inline-start:3px solid {acc};padding-inline-start:0.4em;text-align:start;font-family:{f_head};font-weight:700;font-size:{body_px * 1.05:.1f}px;line-height:{self.lh(1.15)};}}
.folio{{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #111;padding-bottom:0.15em;font-family:{f_sans};font-size:{body_px * 1.0:.1f}px;}}
.fo-sec{{font-weight:800;color:{acc};font-size:1.3em;}}
.ad{{border:2px solid #111;height:100%;padding:0.6em;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;font-family:{f_sans};}}
.ad-co{{font-size:calc(var(--k,1) * {body_px * 2.2:.1f}px);font-weight:800;line-height:1.1;}}
.ad-l{{font-size:calc(var(--k,1) * {body_px * 1.2:.1f}px);margin:0.3em 0;}}
.ad-h{{font-size:calc(var(--k,1) * {body_px * 1.7:.1f}px);font-weight:800;line-height:1.1;}}
.ad-o{{font-size:calc(var(--k,1) * {body_px * 1.4:.1f}px);font-weight:700;margin:0.3em 0;}}
.ad-d{{font-size:calc(var(--k,1) * {body_px * 0.9:.1f}px);}}
.ad-w{{font-size:calc(var(--k,1) * {body_px * 0.9:.1f}px);margin-top:0.2em;}}
.ad-ph{{font-size:calc(var(--k,1) * {body_px * 1.4:.1f}px);font-weight:700;}}
.brief-title{{font-family:{f_sans};font-weight:800;font-size:{body_px * 1.15:.1f}px;color:{acc};}}
.bh{{font-family:{f_head};font-weight:700;font-size:{body_px * 1.02:.1f}px;margin:0.4em 0 0.1em;line-height:{self.lh(1.12)};}}
.fill-h{{border-top:1px solid #888;padding-top:0.3em;margin-top:0.7em;}}
.katex{{direction:ltr;}}
"""


def make(rng, lang, version=0):
    return NewspaperPage(rng, lang, version).build()

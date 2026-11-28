"""Programmatic SVG charts with localized labels (bar / grouped bar / line / scatter / pie / area / hbar)."""
import math

from .textkit import esc, to_native_digits

PALETTES = {
    "office": ["#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5", "#70AD47"],
    "mpl": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"],
    "gray": ["#222222", "#777777", "#AAAAAA", "#444444", "#999999", "#CCCCCC"],
    "excel2": ["#2E75B6", "#C55A11", "#548235", "#7030A0", "#BF9000", "#1F4E79"],
    "pastel": ["#5470C6", "#91CC75", "#FAC858", "#EE6666", "#73C0DE", "#3BA272"],
    "news": ["#B22222", "#1F3A5F", "#D4A017", "#5B7065", "#8E5572", "#2F4858"],
}


def _fmt(v, digits_native, lang, dec_sep="."):
    if isinstance(v, float) and not v.is_integer():
        s = f"{v:.2f}".rstrip("0") if abs(v * 10 - round(v * 10)) > 1e-6 else f"{v:.1f}"
    else:
        s = f"{int(round(v))}"
    if dec_sep != ".":
        s = s.replace(".", dec_sep)
    return to_native_digits(s, lang) if digits_native else s


def nice_ticks(lo, hi, n=5):
    if hi <= lo:
        hi = lo + 1
    span = hi - lo
    step = 10 ** math.floor(math.log10(span / n))
    for m in (1, 2, 2.5, 5, 10):
        if span / (step * m) <= n:
            step *= m
            break
    start = math.floor(lo / step) * step
    ticks = []
    t = start
    while t <= hi + step * 0.5:
        ticks.append(round(t, 10))
        t += step
    return ticks


class Chart:
    def __init__(self, w, h, font, lang, rtl=False, digits_native=False, palette="office", fs=11, ink="#222",
                 grid=True, dec_sep=".", frame=False, bg="none"):
        self.w, self.h, self.font, self.lang, self.rtl = w, h, font, lang, rtl
        self.dn, self.pal, self.fs, self.ink, self.grid = digits_native, PALETTES.get(palette, palette), fs, ink, grid
        self.dec = dec_sep
        self.frame = frame
        self.bg = bg

    def _text(self, x, y, s, anchor="middle", size=None, weight=400, rot=0, fill=None, baseline="middle"):
        size = size or self.fs
        tr = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot else ""
        d = ' direction="rtl"' if self.rtl else ""
        return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size:.1f}" font-weight="{weight}" '
                f'text-anchor="{anchor}" dominant-baseline="{baseline}" fill="{fill or self.ink}"{tr}{d}>'
                f'{esc(s)}</text>')

    def _svg(self, inner):
        bgr = f'<rect width="{self.w}" height="{self.h}" fill="{self.bg}"/>' if self.bg != "none" else ""
        fr = (f'<rect x="0.5" y="0.5" width="{self.w - 1}" height="{self.h - 1}" fill="none" stroke="#999" '
              f'stroke-width="0.8"/>') if self.frame else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w:.0f}" height="{self.h:.0f}" '
                f'viewBox="0 0 {self.w:.0f} {self.h:.0f}" style="font-family:{esc(self.font)};display:block;'
                f'max-width:100%;height:auto">{bgr}{inner}{fr}</svg>')

    def _legend(self, names, x0, y, kind="rect"):
        out, x = [], x0
        for i, n in enumerate(names):
            c = self.pal[i % len(self.pal)]
            if kind == "rect":
                out.append(f'<rect x="{x:.1f}" y="{y - 4:.1f}" width="9" height="9" fill="{c}"/>')
            else:
                out.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + 14:.1f}" y2="{y:.1f}" stroke="{c}" '
                           f'stroke-width="2"/>')
            out.append(self._text(x + 16, y + 0.5, n, anchor="start", size=self.fs * 0.9))
            x += 26 + len(n) * self.fs * 0.55
        return "".join(out)

    def xy(self, cats, series, kind="bar", xlabel="", ylabel="", title=None, legend=True, stacked=False,
           horizontal=False):
        w, h, fs = self.w, self.h, self.fs
        top = fs * (2.4 if title else 1.0) + (fs * 1.4 if legend and len(series) > 1 else 0)
        # y tick labels decide the axis margin (native digits and decimals are wide: never clip the first digit)
        _vals = [v for s in series for v in s["values"]]
        if stacked:
            _vals = [sum(s["values"][i] for s in series) for i in range(len(cats))]
        _lo = min(0, min(_vals)) if kind in ("bar", "area") else min(_vals)
        _hi = max(_vals)
        if kind in ("line", "scatter") and _lo > 0:
            _lo = _lo - (_hi - _lo) * 0.15
        _labs = [_fmt(t, self.dn, self.lang, self.dec) for t in nice_ticks(_lo, _hi * 1.05 if _hi > 0 else _hi)]
        lab_w = max(len(x) for x in _labs) * fs * 0.85 * 0.62
        left = max(fs * 3.0, lab_w + fs * 0.9) + (fs * 1.3 if ylabel else 0)
        maxlen = max((len(str(c)) for c in cats), default=1)
        n_c = max(1, len(cats))
        per0 = (w - left - fs * 1.5) / n_c
        need_h = maxlen * fs * 0.85 * 0.55 + fs * 0.4
        self._kstep = 1
        if need_h <= per0:
            self._rot = 0
        elif n_c >= 7 and math.ceil(need_h / per0) <= 3:
            self._rot, self._kstep = 0, math.ceil(need_h / per0)       # time axis: label every k-th period
        else:
            self._rot = -45
            self._kstep = max(1 if n_c < 10 else 2, math.ceil(fs * 1.25 / per0))
        extra = (maxlen * fs * 0.85 * 0.55 * 0.71) if self._rot else 0
        if self._rot and extra > h * 0.3:
            # long category names: truncate (spreadsheet-style ellipsis) instead of squeezing the plot area
            keep = max(4, int(h * 0.3 / (fs * 0.85 * 0.55 * 0.71)))
            cats = [c if len(str(c)) <= keep else str(c)[:keep - 1] + "…" for c in cats]
            maxlen = keep
            extra = h * 0.3
        bottom = fs * (3.4 if xlabel else 2.2) + extra
        right = fs * 1.0
        if self.rtl:
            left, right = right + fs * 0.5, left
        pw, ph = w - left - right, h - top - bottom
        vals = [v for s in series for v in s["values"]]
        if stacked:
            vals = [sum(s["values"][i] for s in series) for i in range(len(cats))]
        lo = min(0, min(vals)) if kind in ("bar", "area") else min(vals)
        hi = max(vals)
        if kind in ("line", "scatter") and lo > 0:
            lo = lo - (hi - lo) * 0.15
        ticks = nice_ticks(lo, hi * 1.05 if hi > 0 else hi)
        lo, hi = ticks[0], ticks[-1]
        out = []
        if title:
            out.append(self._text(w / 2, fs * 1.1, title, size=fs * 1.15, weight=700))
        if legend and len(series) > 1:
            out.append(self._legend([s["name"] for s in series], left, top - fs * 0.9,
                                    "rect" if kind == "bar" else "line"))

        def X(i, n):  # category center
            frac = (i + 0.5) / n
            if self.rtl:
                frac = 1 - frac
            return left + frac * pw

        def Y(v):
            return top + ph - (v - lo) / (hi - lo) * ph
        axis_x = left + pw if self.rtl else left
        for t in ticks:
            y = Y(t)
            if self.grid:
                out.append(f'<line x1="{left:.1f}" y1="{y:.1f}" x2="{left + pw:.1f}" y2="{y:.1f}" stroke="#d9d9d9" '
                           f'stroke-width="0.7"/>')
            tx = axis_x + (fs * 0.4 if self.rtl else -fs * 0.4)
            out.append(self._text(tx, y, _fmt(t, self.dn, self.lang, self.dec), anchor="start" if self.rtl else "end",
                                  size=fs * 0.85))
        out.append(f'<line x1="{left:.1f}" y1="{top + ph:.1f}" x2="{left + pw:.1f}" y2="{top + ph:.1f}" '
                   f'stroke="{self.ink}" stroke-width="0.9"/>')
        out.append(f'<line x1="{axis_x:.1f}" y1="{top:.1f}" x2="{axis_x:.1f}" y2="{top + ph:.1f}" stroke="{self.ink}" '
                   f'stroke-width="0.9"/>')
        n = len(cats)
        # thin out category labels that would collide (every k-th label, like spreadsheet charts do)
        k_step = self._kstep
        for i, c in enumerate(cats):
            if i % k_step:
                continue
            if self._rot:
                out.append(self._text(X(i, n), top + ph + fs * 0.8, c, size=fs * 0.8, rot=self._rot,
                                      anchor="start" if self.rtl else "end", baseline="hanging"))
            else:
                out.append(self._text(X(i, n), top + ph + fs * 0.9, c, size=fs * 0.85))
        if kind == "bar":
            k = len(series)
            gw = pw / n * 0.72
            for si, s in enumerate(series):
                col = self.pal[si % len(self.pal)]
                for i, v in enumerate(s["values"]):
                    if stacked:
                        base = sum(series[j]["values"][i] for j in range(si))
                        x = X(i, n) - gw / 2
                        y0, y1 = Y(base + v), Y(base)
                        out.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{gw:.1f}" height="{max(0, y1 - y0):.1f}" '
                                   f'fill="{col}"/>')
                    else:
                        bw = gw / k
                        off = (si - (k - 1) / 2) * bw * (-1 if self.rtl else 1)
                        x = X(i, n) + off - bw / 2
                        y0, y1 = Y(max(v, 0)), Y(min(v, 0))
                        out.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{bw * 0.92:.1f}" '
                                   f'height="{max(0.5, y1 - y0):.1f}" fill="{col}"/>')
        else:
            for si, s in enumerate(series):
                col = self.pal[si % len(self.pal)]
                pts = [(X(i, n), Y(v)) for i, v in enumerate(s["values"])]
                if kind == "area":
                    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                    out.append(f'<polygon points="{pts[0][0]:.1f},{Y(lo):.1f} {poly} {pts[-1][0]:.1f},{Y(lo):.1f}" '
                               f'fill="{col}" fill-opacity="0.35" stroke="{col}"/>')
                elif kind == "line":
                    d = " ".join(f"{'M' if j == 0 else 'L'}{x:.1f},{y:.1f}" for j, (x, y) in enumerate(pts))
                    out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.8"/>')
                for x, y in pts:
                    if kind == "scatter":
                        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{col}"/>')
                    elif kind == "line":
                        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="{col}"/>')
        if xlabel:
            out.append(self._text(left + pw / 2, h - fs * 0.8, xlabel, size=fs * 0.95))
        if ylabel:
            yx = w - fs * 0.9 if self.rtl else fs * 0.9
            yl = str(ylabel)
            cap = max(6, int(ph / (fs * 0.95 * 0.55)))        # the rotated axis title must fit the plot height
            if len(yl) > cap:
                yl = yl[:cap - 1] + "…"
            out.append(self._text(yx, top + ph / 2, yl, size=fs * 0.95, rot=-90))
        return self._svg("".join(out))

    def pie(self, cats, values, title=None, donut=False):
        w, h, fs = self.w, self.h, self.fs
        out = []
        top = fs * 2.2 if title else fs * 0.5
        if title:
            out.append(self._text(w / 2, fs * 1.1, title, size=fs * 1.15, weight=700))
        r = min(w * 0.32, (h - top) * 0.42)
        cx = w * (0.62 if self.rtl else 0.36)
        cy = top + (h - top) / 2
        tot = sum(values) or 1
        a0 = -math.pi / 2
        for i, v in enumerate(values):
            a1 = a0 + 2 * math.pi * v / tot
            large = 1 if a1 - a0 > math.pi else 0
            x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
            x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
            col = self.pal[i % len(self.pal)]
            out.append(f'<path d="M{cx:.1f},{cy:.1f} L{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 {large} 1 {x1:.1f},{y1:.1f} Z" '
                       f'fill="{col}" stroke="#fff" stroke-width="1"/>')
            am = (a0 + a1) / 2
            pct = _fmt(100 * v / tot, self.dn, self.lang, self.dec) + "%"
            out.append(self._text(cx + r * 0.66 * math.cos(am), cy + r * 0.66 * math.sin(am), pct,
                                  size=fs * 0.85, fill="#fff", weight=700))
            a0 = a1
        if donut:
            out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.5:.1f}" fill="#fff"/>')
        lx = w * (0.08 if self.rtl else 0.72)
        for i, c in enumerate(cats):
            y = cy - len(cats) * fs * 0.8 + i * fs * 1.6
            col = self.pal[i % len(self.pal)]
            out.append(f'<rect x="{lx:.1f}" y="{y - 5:.1f}" width="10" height="10" fill="{col}"/>')
            out.append(self._text(lx + 14, y, c, anchor="start", size=fs * 0.9))
        return self._svg("".join(out))


def random_series(rng, n_cat, n_series, kind="bar", scale=None):
    scale = scale or rng.choice([1, 10, 50, 100, 1000])
    out = []
    for _ in range(n_series):
        base = rng.uniform(0.3, 1.0) * scale
        trend = rng.uniform(-0.15, 0.25) * scale
        vals = []
        for i in range(n_cat):
            v = base + trend * i / max(1, n_cat - 1) * n_cat * 0.3 + rng.gauss(0, 0.12 * scale)
            v = max(0.02 * scale, v) if kind != "line" else v
            vals.append(round(v, 1 if scale < 20 else 0))
        out.append(vals)
    return out

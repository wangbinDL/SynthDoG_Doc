"""Small SVG diagrams for exams/textbooks: geometry figures, function graphs, number lines (labels localized)."""
import math
import random

from .textkit import esc, to_native_digits

AR_LETTERS = ["أ", "ب", "ج", "د", "هـ", "و"]


def _svg(w, h, inner, font):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}" '
            f'style="font-family:{esc(font)};display:block;max-width:100%;height:auto">{inner}</svg>')


def geometry(rng: random.Random, w, font, lang, fs=14):
    h = w * rng.uniform(0.7, 0.95)
    labels = AR_LETTERS if (lang == "ar" and rng.random() < 0.5) else list("ABCDEFGH")
    kind = rng.choice(["triangle", "triangle", "circle", "quad", "right"])
    out = []
    m = fs * 1.8

    def lab(x, y, t, dx=0, dy=0):
        return (f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" font-size="{fs}" text-anchor="middle" '
                f'dominant-baseline="middle">{esc(t)}</text>')
    if kind in ("triangle", "right"):
        A = (rng.uniform(m, w * 0.45), h - m)
        B = (w - m, h - m)
        C = (A[0] if kind == "right" else rng.uniform(w * 0.3, w * 0.7), m)
        pts = [A, B, C]
        out.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" stroke="#111" '
                   f'stroke-width="1.6"/>')
        out += [lab(A[0], A[1], labels[0], -fs * 0.8, fs * 0.6), lab(B[0], B[1], labels[1], fs * 0.8, fs * 0.6),
                lab(C[0], C[1], labels[2], 0, -fs * 0.8)]
        if kind == "right":
            s = fs * 0.9
            out.append(f'<polyline points="{A[0]:.1f},{A[1] - s:.1f} {A[0] + s:.1f},{A[1] - s:.1f} {A[0] + s:.1f},{A[1]:.1f}" '
                       f'fill="none" stroke="#111" stroke-width="1"/>')
        if rng.random() < 0.7:
            d = to_native_digits(str(rng.randint(3, 15)), lang) + rng.choice([" cm", "", " m"])
            out.append(lab((A[0] + B[0]) / 2, A[1], d, 0, fs * 0.9))
        if rng.random() < 0.5:
            D = ((A[0] + B[0]) / 2, A[1])
            out.append(f'<line x1="{C[0]:.1f}" y1="{C[1]:.1f}" x2="{D[0]:.1f}" y2="{D[1]:.1f}" stroke="#111" '
                       f'stroke-dasharray="4 3"/>')
            out.append(lab(D[0], D[1], labels[3], fs * 0.7, -fs * 0.7))
    elif kind == "circle":
        cx, cy, r = w / 2, h / 2, min(w, h) / 2 - m
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" stroke="#111" stroke-width="1.6"/>')
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.5" fill="#111"/>')
        out.append(lab(cx, cy, "O", fs * 0.6, fs * 0.6))
        angs = sorted(rng.uniform(0, 2 * math.pi) for _ in range(3))
        P = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angs]
        out.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in P)}" fill="none" stroke="#111"/>')
        for i, (x, y) in enumerate(P):
            out.append(lab(x, y, labels[i], (x - cx) / r * fs * 0.9, (y - cy) / r * fs * 0.9))
    else:
        pts = [(m, h - m), (w - m * 1.5, h - m), (w - m, m * 1.4), (m * 1.6, m)]
        out.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" stroke="#111" '
                   f'stroke-width="1.6"/>')
        out.append(f'<line x1="{pts[0][0]:.1f}" y1="{pts[0][1]:.1f}" x2="{pts[2][0]:.1f}" y2="{pts[2][1]:.1f}" '
                   f'stroke="#111" stroke-dasharray="4 3"/>')
        offs = [(-1, 1), (1, 1), (1, -1), (-1, -1)]
        for i, ((x, y), (ox, oy)) in enumerate(zip(pts, offs)):
            out.append(lab(x, y, labels[i], ox * fs * 0.8, oy * fs * 0.7))
    return _svg(w, h, "".join(out), font)


def graph(rng: random.Random, w, font, lang, fs=12):
    h = w * rng.uniform(0.62, 0.85)
    m = fs * 1.6
    ox, oy = rng.uniform(w * 0.25, w * 0.45), rng.uniform(h * 0.45, h * 0.7)
    out = [f'<line x1="{m:.1f}" y1="{oy:.1f}" x2="{w - m * 0.5:.1f}" y2="{oy:.1f}" stroke="#111" stroke-width="1.2" '
           f'marker-end="url(#ar)"/>',
           f'<line x1="{ox:.1f}" y1="{h - m:.1f}" x2="{ox:.1f}" y2="{m * 0.5:.1f}" stroke="#111" stroke-width="1.2" '
           f'marker-end="url(#ar)"/>',
           '<defs><marker id="ar" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
           '<path d="M0,0 L6,3 L0,6 z" fill="#111"/></marker></defs>']
    out.append(f'<text x="{w - m * 0.6:.1f}" y="{oy + fs:.1f}" font-size="{fs}" font-style="italic">x</text>')
    out.append(f'<text x="{ox + fs * 0.4:.1f}" y="{m * 0.8:.1f}" font-size="{fs}" font-style="italic">y</text>')
    out.append(f'<text x="{ox - fs * 0.8:.1f}" y="{oy + fs:.1f}" font-size="{fs}">O</text>')
    unit = w / 12
    for k in range(-4, 8):
        x = ox + k * unit
        if m < x < w - m and k != 0:
            out.append(f'<line x1="{x:.1f}" y1="{oy - 3:.1f}" x2="{x:.1f}" y2="{oy + 3:.1f}" stroke="#111"/>')
            if k % 2 == 0:
                out.append(f'<text x="{x:.1f}" y="{oy + fs * 1.2:.1f}" font-size="{fs * 0.85}" text-anchor="middle">'
                           f'{to_native_digits(str(k), lang)}</text>')
    kind = rng.choice(["parabola", "line", "sine", "cubic"])
    a = rng.uniform(0.3, 1.2)
    pts = []
    for i in range(121):
        x = m + (w - 2 * m) * i / 120
        t = (x - ox) / unit
        if kind == "parabola":
            v = a * (t - rng.uniform(-0.01, 0.01) - 1.5) ** 2 - 2
        elif kind == "line":
            v = a * t - 1
        elif kind == "sine":
            v = 2 * math.sin(t * 0.9)
        else:
            v = 0.08 * (t - 1) * (t + 2) * (t - 4)
        y = oy - v * unit
        if m * 0.5 < y < h - m * 0.5:
            pts.append((x, y))
    if len(pts) > 2:
        d = " ".join(f"{'M' if j == 0 else 'L'}{x:.1f},{y:.1f}" for j, (x, y) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="#111" stroke-width="1.8"/>')
    return _svg(w, h, "".join(out), font)


def figure_for(kind, rng, w, font, lang, fs=13):
    if kind in ("graph", "circuit"):
        return graph(rng, w, font, lang, fs)
    return geometry(rng, w, font, lang, fs)

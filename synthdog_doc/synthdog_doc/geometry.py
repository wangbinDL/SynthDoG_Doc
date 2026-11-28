"""Physical page geometry: paper sizes, orientation and rasterisation DPI per document type.

Distributions follow OmniDocBench page statistics (analysis/odb_stats.json): e.g. academic pages are
mostly Letter/A4 at ~200 dpi, slides 4:3 (70%) / 16:9 at 2000 px width, newspapers ~2750 px wide.
"""
PAPERS = {  # width, height in inches (portrait)
    "A4": (8.27, 11.69), "Letter": (8.5, 11.0), "B5": (6.93, 9.84), "B5J": (7.17, 10.12), "A5": (5.83, 8.27),
    "Legal": (8.5, 14.0), "A3": (11.69, 16.54), "B4": (9.84, 13.9), "Tabloid": (11.0, 17.0),
    "Berliner": (12.4, 18.5), "Broadsheet": (15.0, 22.75), "Broadsheet2": (13.5, 21.5), "Royal": (6.14, 9.21),
    "Trade": (6.0, 9.0), "Crown": (7.44, 9.69),
}
SLIDES = {"4:3": (10.0, 7.5), "16:9": (13.333, 7.5), "16:10": (10.0, 6.25)}

# doc_type -> list of (weight, paper, orientation)
PAPER_MIX = {
    "paper_single": [(0.55, "Letter", "p"), (0.38, "A4", "p"), (0.07, "B5", "p")],
    "paper_double": [(0.62, "Letter", "p"), (0.34, "A4", "p"), (0.04, "B5J", "p")],
    "book": [(0.35, "A4", "p"), (0.2, "Letter", "p"), (0.15, "B5", "p"), (0.12, "Royal", "p"), (0.1, "Crown", "p"),
             (0.08, "A5", "p")],
    "exam": [(0.42, "A4", "p"), (0.33, "Letter", "p"), (0.12, "A3", "l"), (0.08, "B4", "l"), (0.05, "B5", "p")],
    "magazine": [(0.5, "Letter", "p"), (0.38, "A4", "p"), (0.07, "B5", "p"), (0.05, "Letter", "l")],
    "newspaper": [(0.35, "Berliner", "p"), (0.3, "Broadsheet", "p"), (0.2, "Tabloid", "p"),
                  (0.15, "Broadsheet2", "p")],
    "textbook": [(0.62, "A4", "p"), (0.16, "Letter", "p"), (0.1, "B5", "p"), (0.07, "A4", "l"), (0.05, "Crown", "p")],
    "report": [(0.93, "A4", "p"), (0.07, "Letter", "p")],
}
PPT_MIX = [(0.68, "4:3"), (0.29, "16:9"), (0.03, "16:10")]


def _choice(rng, items):
    r = rng.random() * sum(w for w, *_ in items)
    for it in items:
        r -= it[0]
        if r <= 0:
            return it[1:]
    return items[-1][1:]


def sample_page(rng, doc_type):
    """Return dict(paper, w_in, h_in, dpi, orientation)."""
    if doc_type == "ppt":
        (ratio,) = _choice(rng, PPT_MIX)
        w, h = SLIDES[ratio]
        target_w = rng.choice([2000, 2000, 2000, 1920, 1600, 2400])
        return {"paper": f"slide{ratio}", "w_in": w, "h_in": h, "dpi": target_w / w, "orientation": "l"}
    paper, orient = _choice(rng, PAPER_MIX[doc_type])
    w, h = PAPERS[paper]
    if orient == "l":
        w, h = h, w
    if doc_type == "newspaper":
        target_w = rng.uniform(2300, 3300)
        dpi = target_w / w
    elif doc_type == "book":
        dpi = rng.choices([200, 180, 150, 120, 96], weights=[0.6, 0.12, 0.14, 0.08, 0.06])[0]
    elif doc_type == "exam" and orient == "l":
        dpi = rng.choice([150, 160, 180, 200])
    elif doc_type in ("magazine", "textbook"):
        dpi = rng.choices([200, 180, 150, 240], weights=[0.6, 0.15, 0.15, 0.1])[0]
    else:
        dpi = rng.choices([200, 190, 180, 150, 220], weights=[0.6, 0.12, 0.1, 0.1, 0.08])[0]
    return {"paper": paper, "w_in": w, "h_in": h, "dpi": float(dpi), "orientation": orient}


PT = 96.0 / 72.0   # CSS px per point
MM = 96.0 / 25.4   # CSS px per mm
IN = 96.0

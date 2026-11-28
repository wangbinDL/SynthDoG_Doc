"""Ground-truth export: raw in-page GT -> ODB-compatible JSON, page markdown, line-level OCR, overlays."""
import json
import re

import numpy as np
from PIL import Image, ImageDraw

FURNITURE = {"header", "footer", "page_number", "abandon"}
CAT_COLORS = {
    "title": (220, 40, 40), "text_block": (40, 90, 220), "figure": (30, 160, 60), "figure_caption": (120, 200, 60),
    "table": (230, 160, 20), "table_caption": (240, 200, 60), "equation_isolated": (160, 60, 200),
    "equation_caption": (200, 120, 230), "header": (120, 120, 120), "footer": (120, 120, 120),
    "page_number": (90, 90, 90), "page_footnote": (0, 170, 170), "reference": (0, 120, 160),
    "abandon": (150, 150, 150), "code_txt": (200, 80, 0), "table_footnote": (200, 170, 90),
    "figure_footnote": (90, 170, 90),
}


def rect_poly(b):
    x0, y0, x1, y1 = b
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)


def order_blocks(blocks):
    """Reading order: body by (zone order, column, DOM); page furniture after body (header first)."""
    def key(b):
        furn = b["cat"] in FURNITURE
        head = b["cat"] == "header"
        return (0 if head else (2 if furn else 1), b.get("zorder", 0), b.get("col", 0), b.get("dom", 0))
    return sorted(blocks, key=key)


def build(gt, scale, H_polys=None):
    """Return ordered blocks with pixel polygons (4x2) and line polygons before degradation."""
    blocks = order_blocks(gt["blocks"])
    out = []
    for i, b in enumerate(blocks):
        poly = rect_poly([v * scale for v in b["box"]])
        lines = []
        for ln in b.get("lines") or []:
            lines.append({"poly": rect_poly([v * scale for v in ln["box"]]), "text": ln["text"]})
        out.append({**b, "order": i, "poly": poly, "lines_px": lines})
    return out


def collect_polys(blocks):
    polys, index = [], []
    for bi, b in enumerate(blocks):
        polys.append(b["poly"]); index.append((bi, -1))
        for li, ln in enumerate(b["lines_px"]):
            polys.append(ln["poly"]); index.append((bi, li))
    return polys, index


def scatter_polys(blocks, polys, index):
    for p, (bi, li) in zip(polys, index):
        if li < 0:
            blocks[bi]["poly"] = p
        else:
            blocks[bi]["lines_px"][li]["poly"] = p


def flat(p):
    return [round(float(v), 2) for v in np.asarray(p).reshape(-1)]


def to_odb(blocks, page_info, extra=None):
    dets = []
    for i, b in enumerate(blocks):
        d = {"category_type": b["cat"], "poly": flat(b["poly"]), "ignore": False, "order": i,
             "anno_id": f"box_id_{i}", "attribute": {}}
        if b["cat"] == "equation_isolated":
            d["latex"] = b.get("text", "")
        elif b["cat"] == "table":
            d["html"] = b.get("html", "")
        elif b["cat"] != "figure":
            d["text"] = b.get("text", "")
        if b.get("lines_px"):
            d["line_with_spans"] = [{"poly": flat(ln["poly"]), "text": ln["text"]} for ln in b["lines_px"]]
        if b.get("cont_of"):
            d["attribute"]["continued_from"] = b["cont_of"]
        dets.append(d)
    rel = []
    # caption relations (figure/table -> nearest caption in the same group)
    by_group = {}
    for i, b in enumerate(blocks):
        if b.get("group"):
            by_group.setdefault(b["group"], []).append(i)
    for g, idx in by_group.items():
        objs = [i for i in idx if blocks[i]["cat"] in ("figure", "table", "equation_isolated")]
        caps = [i for i in idx if blocks[i]["cat"] in ("figure_caption", "table_caption", "equation_caption",
                                                        "table_footnote", "figure_footnote")]
        for o in objs:
            for c in caps:
                rel.append({"source_anno_id": f"box_id_{c}", "target_anno_id": f"box_id_{o}",
                            "relation_type": "parent_son"})
    # paragraphs split across columns / pages: OmniDocBench "truncated" relations, merged by the scorer
    bid2idx = {b.get("bid"): i for i, b in enumerate(blocks) if b.get("bid")}
    for i, b in enumerate(blocks):
        j = bid2idx.get(b.get("cont_of"))
        if j is not None and j != i:
            rel.append({"source_anno_id": f"box_id_{j}", "target_anno_id": f"box_id_{i}",
                        "relation_type": "truncated"})
    return {"layout_dets": dets, "page_info": page_info, "extra": {"relation": rel, **(extra or {})}}


def to_markdown(blocks):
    out = []
    for b in blocks:
        c, t = b["cat"], (b.get("text") or "").strip()
        if c in FURNITURE:
            continue
        if c == "title":
            lvl = b.get("sub") or "2"
            out.append("#" * int(lvl) + " " + t.replace("\n", " "))
        elif c == "equation_isolated":
            out.append(t)
        elif c == "table":
            out.append(b.get("html", ""))
        elif c == "figure":
            out.append("![figure]()")
        else:
            out.append(t)
    md = "\n\n".join(x for x in out if x)
    return re.sub(r"\n{3,}", "\n\n", md)


def overlay(img, blocks, lines=False):
    im = Image.fromarray(img).convert("RGB")
    dr = ImageDraw.Draw(im, "RGBA")
    w = max(2, im.width // 700)
    for b in blocks:
        col = CAT_COLORS.get(b["cat"], (255, 0, 255))
        p = [tuple(map(float, xy)) for xy in np.asarray(b["poly"]).reshape(-1, 2)]
        dr.polygon(p, outline=col + (255,), fill=col + (28,), width=w)
        if lines:
            for ln in b["lines_px"]:
                q = [tuple(map(float, xy)) for xy in np.asarray(ln["poly"]).reshape(-1, 2)]
                dr.polygon(q, outline=col + (150,), width=1)
        x0, y0 = p[0]
        dr.rectangle([x0, max(0, y0 - 14 * w / 2), x0 + 9 * w * 2.2, y0], fill=col + (220,))
        dr.text((x0 + 2, max(0, y0 - 14 * w / 2)), str(b["order"]), fill=(255, 255, 255, 255))
    return im


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)

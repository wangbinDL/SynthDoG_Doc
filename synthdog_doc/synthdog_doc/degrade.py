"""Imaging-condition simulation (SynthDoG-style post degradation) with exact geometry tracking.

Three capture branches, sampled per document type:
  digital : born-digital PDF/screen render (resampling + JPEG only)
  scan    : print-and-scan / photocopy (paper texture, tone curve, blur, noise, tiny rotation, bleed-through)
  photo   : phone capture (perspective warp, background, illumination gradient, shadow, blur, colour cast)
Every geometric transform is a homography H applied to the image and to all ground-truth polygons.
"""
import io
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SYNTHDOG_RES = Path(__file__).resolve().parents[2] / "synthdog" / "resources"
PAPER_DIR = SYNTHDOG_RES / "paper"
BG_DIR = SYNTHDOG_RES / "background"

_paper_cache = {}
_GHOSTS = {}   # per language: small pool of other rendered pages used as verso for bleed-through
_CUR = {"lang": None, "doc_type": None}


def remember_page(img, keep=6, lang=None):
    """Keep a downscaled copy of a clean render to serve as the verso of later pages (same language only)."""
    h, w = img.shape[:2]
    s = 900.0 / max(h, w)
    pool = _GHOSTS.setdefault(lang, [])
    pool.append(cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA))
    if len(pool) > keep:
        pool.pop(0)


def _papers():
    if "p" not in _paper_cache:
        _paper_cache["p"] = [cv2.imread(str(p))[:, :, ::-1] for p in sorted(PAPER_DIR.glob("*.jpg"))]
        _paper_cache["b"] = [cv2.imread(str(p))[:, :, ::-1] for p in sorted(BG_DIR.glob("*.jp*g"))]
    return _paper_cache["p"], _paper_cache["b"]


def _tile_resize(tex, h, w, rng):
    th, tw = tex.shape[:2]
    scale = rng.uniform(0.8, 1.6) * max(h / th, w / tw)
    t = cv2.resize(tex, (max(w, int(tw * scale)), max(h, int(th * scale))), interpolation=cv2.INTER_LINEAR)
    y = rng.randint(0, t.shape[0] - h)
    x = rng.randint(0, t.shape[1] - w)
    return t[y:y + h, x:x + w]


def procedural_paper(h, w, rng):
    """Fine paper grain: low-amplitude multi-scale noise around a slightly tinted white (float32 HxWx3)."""
    npr = np.random.default_rng(rng.randint(0, 2**31))
    base = np.array([rng.uniform(244, 255), rng.uniform(241, 253), rng.uniform(232, 250)], np.float32)
    # real scanned paper is nearly uniform: faint mottling (no grey clouds) plus fine fibre noise
    small = npr.normal(0, 1, (max(2, h // 48), max(2, w // 48))).astype(np.float32)
    low = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC) * rng.uniform(0.5, 1.6)
    fine = npr.normal(0, rng.uniform(0.8, 2.2), (h, w)).astype(np.float32)
    tex = base[None, None, :] + (low + fine)[..., None]
    return np.clip(tex, 200, 255)


def procedural_background(h, w, rng):
    npr = np.random.default_rng(rng.randint(0, 2**31))
    palette = [(120, 90, 60), (150, 120, 85), (95, 95, 100), (60, 60, 62), (180, 170, 150), (40, 50, 70),
               (200, 200, 195), (110, 75, 50)]
    c = np.array(rng.choice(palette), np.float32) * rng.uniform(0.85, 1.15)
    small = npr.normal(0, 1, (max(2, h // 32), max(2, w // 32))).astype(np.float32)
    low = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC) * rng.uniform(4, 12)
    if rng.random() < 0.5:  # wood-like streaks
        yy = np.arange(h, dtype=np.float32)[:, None]
        streak = np.sin(yy / rng.uniform(6, 20) + low[:, :1] * 0.2) * rng.uniform(3, 8)
        low = low + streak
    bg = c[None, None, :] + low[..., None] + npr.normal(0, 2.0, (h, w, 1)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    vig = 1 - 0.25 * (((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) * 2)
    return np.clip(bg * vig[..., None], 0, 255)


def apply_h(polys, H):
    out = []
    for p in polys:
        a = np.asarray(p, dtype=np.float32).reshape(-1, 1, 2)
        out.append(cv2.perspectiveTransform(a, H).reshape(-1, 2))
    return out


def _jpeg(img, q):
    ok, buf = cv2.imencode(".jpg", img[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, int(q)])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)[:, :, ::-1]


def _resample(img, rng, lo=0.6, hi=0.95):
    h, w = img.shape[:2]
    s = rng.uniform(lo, hi)
    small = cv2.resize(img, (max(8, int(w * s)), max(8, int(h * s))), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def degrade(img, polys, branch, rng: random.Random, strength=1.0):
    """img: HxWx3 uint8 RGB. Returns (img, polys, params)."""
    h, w = img.shape[:2]
    H = np.eye(3, dtype=np.float64)
    params = {"branch": branch}
    out = img.astype(np.float32)

    if branch == "digital":
        if rng.random() < 0.5:
            out = _resample(out.astype(np.uint8), rng, 0.7, 0.95).astype(np.float32)
            params["resample"] = True
        q = rng.randint(72, 95)
        res = _jpeg(np.clip(out, 0, 255).astype(np.uint8), q)
        params["jpeg"] = q
        return res, polys, params

    papers, bgs = _papers()
    if branch == "scan":
        # paper: mostly a fine procedural grain + slight tint; strongly crumpled textures are rare and faint
        if rng.random() < 0.85:
            out = out * (procedural_paper(h, w, rng) / 255.0)
            params["paper"] = "grain"
        elif rng.random() < 0.5:
            tex = _tile_resize(rng.choice(papers), h, w, rng).astype(np.float32)
            tex = 255 - (255 - tex) * rng.uniform(0.08, 0.22) * strength
            out = out * (tex / 255.0)
            params["paper"] = "texture"
        # bleed-through: faint mirrored ghost of a *different* page (the verso)
        ghosts = _GHOSTS.get(_CUR["lang"]) or []
        if ghosts and rng.random() < 0.3 * strength:
            g = rng.choice(ghosts)
            ghost = cv2.resize(g, (w, h), interpolation=cv2.INTER_LINEAR)
            ghost = cv2.GaussianBlur(cv2.flip(ghost, 1), (0, 0), 3.5).astype(np.float32)
            a = rng.uniform(0.015, 0.045)
            out = out * (1 - a) + np.minimum(out, ghost) * a
            params["bleed"] = round(a, 3)
        # tone curve (toner density) + grayscale photocopy
        if rng.random() < (0.15 if _CUR["doc_type"] in ("textbook", "magazine", "ppt") else 0.45):
            g = out.mean(axis=2, keepdims=True)
            out = np.repeat(g, 3, axis=2)
            params["gray"] = True
        gamma = rng.uniform(0.8, 1.25)
        out = 255.0 * np.power(np.clip(out / 255.0, 0, 1), gamma)
        params["gamma"] = round(gamma, 3)
        if rng.random() < 0.12 * strength:
            # hard photocopy: contrast stretch
            lo, hi = rng.uniform(20, 60), rng.uniform(190, 235)
            out = np.clip((out - lo) * 255.0 / (hi - lo), 0, 255)
            params["copy_contrast"] = True
        # tiny rotation / scale (scanner skew)
        ang = rng.uniform(-0.8, 0.8) * strength
        sc = rng.uniform(0.985, 1.0)
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, sc)
        A = np.vstack([M, [0, 0, 1]])
        out = cv2.warpAffine(out, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        H = A @ H
        params["rot"] = round(ang, 3)
        # optical blur + sensor noise + specks
        sig = rng.uniform(0.2, 0.75) * strength
        if sig > 0.25:
            out = cv2.GaussianBlur(out, (0, 0), sig)
        params["blur"] = round(sig, 3)
        nz = rng.uniform(1.5, 5.0) * strength
        out = out + np.random.default_rng(rng.randint(0, 2**31)).normal(0, nz, out.shape)
        params["noise"] = round(nz, 2)
        if rng.random() < 0.4:
            nspeck = int(rng.uniform(20, 200) * (h * w) / 4e6)
            npr = np.random.default_rng(rng.randint(0, 2**31))
            ys = npr.integers(0, h, nspeck)
            xs = npr.integers(0, w, nspeck)
            for y, x in zip(ys, xs):
                r = int(npr.integers(1, 3))
                cv2.circle(out, (int(x), int(y)), r, (float(npr.uniform(40, 120)),) * 3, -1)
            params["specks"] = int(nspeck)
        q = rng.randint(65, 92)
        res = _jpeg(np.clip(out, 0, 255).astype(np.uint8), q)
        params["jpeg"] = q
        return res, apply_h(polys, H), params

    # ---- photo branch (procedural desk/table background, no recognisable stock photos)
    bg = procedural_background(h, w, rng)
    m = rng.uniform(0.015, 0.05) * strength
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    inset = rng.uniform(0.01, 0.04)
    dst = []
    for (x, y) in src:
        cx = x + (w * inset if x == 0 else -w * inset) + rng.uniform(-m, m) * w
        cy = y + (h * inset if y == 0 else -h * inset) + rng.uniform(-m, m) * h
        dst.append([cx, cy])
    dst = np.float32(dst)
    P = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(out, P, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(0, 0, 0))
    mask = cv2.warpPerspective(np.ones((h, w), np.float32), P, (w, h), flags=cv2.INTER_LINEAR)
    out = warped * mask[..., None] + bg * (1 - mask[..., None])
    H = P @ H
    params["perspective"] = round(m, 4)
    # illumination gradient + soft shadow
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = rng.uniform(0, 2 * np.pi)
    grad = (np.cos(ang) * (xx / w - 0.5) + np.sin(ang) * (yy / h - 0.5))
    illum = 1.0 + grad * rng.uniform(0.15, 0.45) * strength
    out = out * illum[..., None]
    if rng.random() < 0.5:
        sh = np.zeros((h, w), np.float32)
        pts = np.int32([[rng.uniform(-0.2, 1.2) * w, rng.uniform(-0.2, 1.2) * h] for _ in range(4)])
        cv2.fillConvexPoly(sh, cv2.convexHull(pts), 1.0)
        sh = cv2.GaussianBlur(sh, (0, 0), max(h, w) * 0.03)
        out = out * (1 - sh[..., None] * rng.uniform(0.15, 0.4))
        params["shadow"] = True
    # colour cast
    cast = np.array([rng.uniform(0.92, 1.06), rng.uniform(0.95, 1.03), rng.uniform(0.85, 1.02)], np.float32)
    out = out * cast
    sig = rng.uniform(0.4, 1.2) * strength
    out = cv2.GaussianBlur(out, (0, 0), sig)
    params["blur"] = round(sig, 3)
    nz = rng.uniform(2.0, 6.0)
    out = out + np.random.default_rng(rng.randint(0, 2**31)).normal(0, nz, out.shape)
    q = rng.randint(70, 92)
    res = _jpeg(np.clip(out, 0, 255).astype(np.uint8), q)
    params["jpeg"] = q
    return res, apply_h(polys, H), params


BRANCH_MIX = {  # (digital, scan, photo) per document type
    "ppt": (0.95, 0.0, 0.05),
    "report": (0.85, 0.13, 0.02),
    "paper_single": (0.65, 0.30, 0.05),
    "paper_double": (0.65, 0.30, 0.05),
    "book": (0.45, 0.47, 0.08),
    "magazine": (0.60, 0.30, 0.10),
    "textbook": (0.45, 0.40, 0.15),
    "exam": (0.30, 0.50, 0.20),
    "newspaper": (0.40, 0.45, 0.15),
}


def pick_branch(doc_type, rng):
    d, s, p = BRANCH_MIX.get(doc_type, (0.6, 0.3, 0.1))
    r = rng.random()
    return "digital" if r < d else ("scan" if r < d + s else "photo")


def png_to_rgb(png_bytes):
    return np.array(Image.open(io.BytesIO(png_bytes)).convert("RGB"))

"""Image asset pools (photos / illustrations / diagrams) prepared from internal L1 crops, with topic tags.

Pools live under SDD_ASSET_DIR/<kind>/index.jsonl (rows: path, w, h, topic, subject, ok). Topic tags come from
scripts/tag_photos.py; untagged rows are still usable. If no pool exists, SynthDoG's own background photos are
used (this is what the v0 baseline does).
"""
import json
import os
import random
from functools import lru_cache
from pathlib import Path

ASSET_DIR = Path(os.environ.get("SDD_ASSET_DIR", "/data/synthdog-doc/assets"))
SYNTHDOG_BG = Path(__file__).resolve().parents[2] / "synthdog" / "resources" / "background"

# content topic -> acceptable photo topics (first = best)
TOPIC_COMPAT = {
    "politics": ["politics", "people", "crowd", "building", "city"],
    "sports": ["sports", "crowd", "people"],
    "business": ["business", "industry", "people", "city", "building", "technology"],
    "economy": ["business", "industry", "city", "people", "agriculture"],
    "industry": ["industry", "technology", "business", "transport"],
    "health": ["health", "science", "people"],
    "science": ["science", "technology", "nature", "health"],
    "technology": ["technology", "science", "industry", "business"],
    "nature": ["nature", "agriculture", "weather"],
    "city": ["city", "building", "transport", "crowd"],
    "building": ["building", "city", "culture"],
    "transport": ["transport", "city", "industry"],
    "food": ["food", "agriculture", "people"],
    "education": ["education", "people", "building", "culture"],
    "culture": ["culture", "people", "building", "religion", "crowd"],
    "agriculture": ["agriculture", "nature", "food", "people"],
    "weather": ["weather", "nature", "city"],
    "military": ["military", "politics", "people"],
    "religion": ["religion", "culture", "building", "crowd"],
    "people": ["people", "crowd", "politics", "culture"],
    "crowd": ["crowd", "people", "politics", "sports"],
}
SECTION_TOPIC = {"National": "politics", "International": "politics", "World": "politics", "Politics": "politics",
                 "Economy": "economy", "Business": "business", "Sports": "sports", "Culture": "culture",
                 "Science": "science", "Health": "health", "Technology": "technology", "Education": "education",
                 "Local": "city", "Opinion": "people", "Entertainment": "culture"}


@lru_cache(maxsize=16)
def pool(kind):
    idx = ASSET_DIR / kind / "index.jsonl"
    rows = []
    if idx.exists():
        for line in idx.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if d.get("ok") is False:
                continue
            if Path(d["path"]).exists():
                rows.append(d)
    if not rows and kind in ("photo", "any"):
        rows = [{"path": str(p), "w": 0, "h": 0, "src": "synthdog_bg"} for p in sorted(SYNTHDOG_BG.glob("*.jp*g"))]
    return rows


@lru_cache(maxsize=64)
def _by_topic(kind):
    by = {}
    for d in pool(kind):
        by.setdefault(d.get("topic") or "untagged", []).append(d)
    return by


NON_EDITORIAL = __import__("re").compile(
    r"dataset|simulat|microscop|annotated|bounding box|detection|heatmap|segmentation|x-ray|\bmri\b|ct scan|"
    r"schematic|infographic|scale bar|measurement|electrode|comparison of|cartoon|facial action|landmark|illustrat|"
    r"drawing|painting|comic|sketch|poster|caption|signboard|\btext\b|lettering|handwrit", __import__("re").I)


def pick(rng: random.Random, kind="photo", min_ar=None, max_ar=None, topic=None, kinds=None, editorial=False):
    """Pick an image; with `topic`, prefer compatible tagged photos (falls back to any photo of the pool).
    editorial=True: only real photographs without embedded text / drawings (covers, news, ads)."""
    kinds = kinds or ([kind, "photo_gray"] if kind == "photo" else [kind])
    cands = []
    if topic:
        for t in TOPIC_COMPAT.get(topic, [topic]):
            for k in kinds:
                cands += _by_topic(k).get(t, [])
            if len(cands) >= 3:
                break
    if not cands:
        for k in kinds:
            cands += pool(k)
    if editorial:
        cands = [c for c in cands if c.get("subject") and not NON_EDITORIAL.search(c["subject"])
                 and not c.get("overlay") and c.get("text") in (None, "none", "little")] or cands
    if not cands:
        return None
    for _ in range(20):
        d = rng.choice(cands)
        if d.get("w") and d.get("h") and (min_ar or max_ar):
            ar = d["h"] / d["w"]
            if (min_ar and ar < min_ar) or (max_ar and ar > max_ar):
                continue
        return d
    return rng.choice(cands)

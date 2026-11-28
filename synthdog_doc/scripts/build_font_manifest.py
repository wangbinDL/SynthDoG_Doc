"""Scan a google/fonts sparse checkout and build a font manifest with script coverage.

Usage: python3 scripts/build_font_manifest.py <fonts_root> <out_json>
"""
import json
import re
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

# Characters a font must cover to be usable for a script (lower bar: core letters + digits/punct).
SCRIPT_PROBES = {
    "latin": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
    "latin_ext": "áéíóúñçãõâêôàèùäöüßœÁÉÍÓÚÑÇÃÕÂÊÔÀÈÙÄÖÜ¿¡«»„“”–—",
    "cyrillic": "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "devanagari": "अआइईउऊएऐओऔकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसहािीुूेैोौंःँ्।०१२३४५६७८९",
    "bengali": "অআইঈউঊএঐওঔকখগঘচছজঝটঠডঢণতথদধনপফবভমযরলশষসহািীুূেৈোৌংঃঁ্।০১২৩৪৫৬৭৮৯",
    "arabic": "ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأإةىً٠١٢٣٤٥٦٧٨٩،؛؟",
    "urdu": "ٹڈڑںھہیےۓ۰۱۲۳۴۵۶۷۸۹",
    # phase 2 scripts
    "persian": "پچژگکی۰۱۲۳۴۵۶۷۸۹",
    "hans": "这个们国说对时会还来过为发经动应样么问题实现说话钱铁门风飞马鸟鱼龙书车长东乐爱",
    "hant": "這個們國說對時會還來過為發經動應樣麼問題實現說話錢鐵門風飛馬鳥魚龍書車長東樂愛",
    "japanese": "あいうえおかきくけこさしすせそたちつてとなにぬねのアイウエオカキクケコサシスセソ日本語漢字々ー・「」。、",
    "hangul": "가나다라마바사아자차카타파하한국어대한민국서울학교선생님감사합니다",
    "thai": "กขคงจฉชซญดตถทธนบปผพฟภมยรลวศษสหอฮะาำิีึืุู่้๊๋็์ๆฯ๐๑๒๓๔๕๖๗๘๙",
    "vietnamese": "ăâđêôơưĂÂĐÊÔƠƯạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ",
    "turkish": "ğĞışŞİçÇöÖüÜ",
    "polish": "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ",
    "greek": "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψωάέήίόύώ",
    "hebrew": "אבגדהוזחטיכלמנסעפצקרשתךםןףץ",
}


def coverage(cmap, chars):
    return sum(1 for c in chars if ord(c) in cmap) / len(chars)


def meta_category(meta_path):
    if not meta_path.exists():
        return None
    txt = meta_path.read_text(encoding="utf-8", errors="ignore")
    cats = re.findall(r'category:\s*"([A-Z_]+)"', txt)
    return cats[0] if cats else None


def main(root, out):
    root = Path(root)
    rows = []
    for ttf in sorted(list(root.glob("*/*/*.ttf")) + list(root.glob("*/*/*.otf"))):
        try:
            f = TTFont(str(ttf), lazy=True)
        except Exception as e:  # noqa: BLE001
            print("skip", ttf, e)
            continue
        cmap = f.getBestCmap() or {}
        name = f["name"]
        fam = name.getDebugName(16) or name.getDebugName(1)
        sub = name.getDebugName(17) or name.getDebugName(2)
        os2 = f["OS/2"] if "OS/2" in f else None
        axes = {a.axisTag: [a.minValue, a.maxValue] for a in f["fvar"].axes} if "fvar" in f else {}
        italic = bool(os2 and (os2.fsSelection & 1)) or "italic" in ttf.name.lower()
        cov = {s: round(coverage(cmap, p), 3) for s, p in SCRIPT_PROBES.items()}
        rows.append({
            "path": str(ttf.resolve()),
            "dir": ttf.parent.name,
            "family": fam,
            "style": sub,
            "weight": os2.usWeightClass if os2 else 400,
            "italic": italic,
            "axes": axes,
            "category": meta_category(ttf.parent / "METADATA.pb"),
            "coverage": cov,
            "has_gsub": "GSUB" in f,
            "has_gpos": "GPOS" in f,
        })
    Path(out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} fonts -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

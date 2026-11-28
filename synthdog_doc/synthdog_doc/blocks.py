"""HTML block emitters shared by all document templates (each emits annotated, tokenised markup)."""
import itertools

from .textkit import esc, sanitize_latex, words_html

_ids = itertools.count()


def bid(prefix="b"):
    return f"{prefix}{next(_ids)}"


def attrs(**kw):
    out = []
    for k, v in kw.items():
        if v is None or v is False:
            continue
        k = k.rstrip("_").replace("_", "-")
        out.append(f'{k}="{esc(v)}"' if v is not True else k)
    return " ".join(out)


def para(text, lang, cls="", cat="text_block", split=True, hyph=False, digits=False, tag="p", style=None,
         extra=None, group=None, zorder=None):
    a = attrs(class_=cls or None, data_cat=cat, data_bid=bid(), data_split="1" if split else None,
              style=style, data_group=group, data_zorder=zorder)
    if extra:
        a += " " + extra
    return f"<{tag} {a}>{words_html(text, lang, hyph=hyph, digits=digits)}</{tag}>"


def heading(text, lang, level=2, cls="", cat="title", tag=None, kwn=True, style=None, fit_lines=None,
            digits=False, zorder=None):
    tag = tag or f"h{min(6, max(1, level))}"
    a = attrs(class_=cls or None, data_cat=cat, data_sub=str(level), data_bid=bid("h"),
              data_kwn="1" if kwn else None, style=style, data_fit_lines=fit_lines, data_zorder=zorder)
    return f"<{tag} {a}>{words_html(text, lang, digits=digits)}</{tag}>"


def span_text(text, lang, cat, cls="", style=None, tag="div", digits=False, zorder=None, extra=None):
    a = attrs(class_=cls or None, data_cat=cat, data_bid=bid("t"), style=style, data_zorder=zorder)
    if extra:
        a += " " + extra
    return f"<{tag} {a}>{words_html(text, lang, digits=digits)}</{tag}>"


def equation(latex, number=None, cls="eqrow", numcls="eqno", lang=None, digits=False):
    g = bid("g")
    eq = f'<div class="eq" data-cat="equation_isolated" data-bid="{bid("e")}" data-latex="{esc(sanitize_latex(latex))}" ' \
         f'data-display="1" data-group="{g}"></div>'
    num = ""
    if number:
        num = f'<div class="{numcls}" data-cat="equation_caption" data-bid="{bid("n")}" data-group="{g}">' \
              f'{words_html(number, lang, digits=digits)}</div>'
    return f'<div class="{cls}">{eq}{num}</div>'


def figure(inner, caption=None, lang=None, cls="fig", capcls="cap", cap_first=False, style=None, shrink=True,
           place=None, col=None, digits=False, capcat="figure_caption"):
    g = bid("g")
    img = f'<div class="figimg" data-cat="figure" data-bid="{bid("f")}" data-group="{g}">{inner}</div>'
    cap = ""
    if caption:
        cap = f'<div class="{capcls}" data-cat="{capcat}" data-bid="{bid("c")}" data-group="{g}">' \
              f'{words_html(caption, lang, digits=digits)}</div>'
    body = cap + img if cap_first else img + cap
    a = attrs(class_=cls, style=style, data_shrink="1" if shrink else None, data_place=place,
              data_col=None if col is None else str(col), data_float="1" if place is None else None)
    return f"<div {a}>{body}</div>"


def table(header, rows, lang, caption=None, cls="tbl", capcls="cap", cap_first=True, note=None, digits=False,
          style=None, place=None, col=None, num_align=True, header_rows=1, spans=None):
    g = bid("g")

    def cell(tag, v, extra=""):
        s = str(v)
        isnum = num_align and any(ch.isdigit() for ch in s) and len(s) < 18
        c = ' class="num"' if isnum else ""
        return f"<{tag}{c}{extra}>{words_html(s, lang, digits=digits)}</{tag}>"
    trs = []
    if header:
        if isinstance(header[0], (list, tuple)):
            for hr in header:
                trs.append("<tr>" + "".join(cell("th", h) for h in hr) + "</tr>")
        else:
            trs.append("<tr>" + "".join(cell("th", h) for h in header) + "</tr>")
    for r in rows:
        trs.append("<tr>" + "".join(cell("td", v) for v in r) + "</tr>")
    tbl = f'<table class="{cls}" data-cat="table" data-bid="{bid("T")}" data-group="{g}">' + "".join(trs) + "</table>"
    cap = ""
    if caption:
        cap = f'<div class="{capcls}" data-cat="table_caption" data-bid="{bid("c")}" data-group="{g}">' \
              f'{words_html(caption, lang, digits=digits)}</div>'
    nt = ""
    if note:
        nt = f'<div class="tnote" data-cat="table_footnote" data-bid="{bid("c")}" data-group="{g}">' \
             f'{words_html(note, lang, digits=digits)}</div>'
    body = (cap + tbl if cap_first else tbl + cap) + nt
    a = attrs(class_="tblwrap", style=style, data_place=place, data_col=None if col is None else str(col),
              data_float="1" if (place is None and caption) else None)
    return f"<div {a}>{body}</div>"


def zone(x, y, w, h, inner, cls="", flow=False, cols=1, gap="1em", rule=None, zorder=0, style="", minhead=2,
         zid=None, top_from=None, bottom_from=None, gap_top=0, gap_bottom=0, auto_h=False, anchor_bottom=None,
         balance=False):
    """Absolutely positioned region. auto_h: height from content; anchor_bottom: px distance from page bottom.
    balance: multi-column flows that end early spread their text evenly over the columns."""
    c = "zone" + (" flow" if flow else "") + (" " + cls if cls else "")
    if anchor_bottom is not None:
        st = f"left:{x:.2f}px;bottom:{anchor_bottom:.2f}px;width:{w:.2f}px;{style}"
    elif auto_h:
        st = f"left:{x:.2f}px;top:{y:.2f}px;width:{w:.2f}px;{style}"
    else:
        st = f"left:{x:.2f}px;top:{y:.2f}px;width:{w:.2f}px;height:{h:.2f}px;{style}"
    extra = attrs(id=zid, data_top_from=top_from, data_bottom_from=bottom_from,
                  data_gap_top=str(gap_top) if top_from else None,
                  data_gap_bottom=str(gap_bottom) if bottom_from else None)
    if flow:
        if balance:
            extra += ' data-balance="1"'
        return (f'<div class="{c}" style="{st}" {extra} data-cols="{cols}" data-gap="{gap}" '
                f'data-rule="{esc(rule or "0")}" data-zorder="{zorder}" data-minhead="{minhead}">'
                f'<div class="src">{inner}</div></div>')
    return f'<div class="{c}" style="{st}" {extra} data-zorder="{zorder}">{inner}</div>'


MARKS = [
    '<svg viewBox="0 0 40 40" width="70%" height="70%"><circle cx="20" cy="20" r="15" fill="none" stroke="#fff" stroke-width="5"/><circle cx="20" cy="20" r="5" fill="#fff"/></svg>',
    '<svg viewBox="0 0 40 40" width="70%" height="70%"><path d="M6 32 L20 8 L34 32 Z" fill="none" stroke="#fff" stroke-width="5"/></svg>',
    '<svg viewBox="0 0 40 40" width="70%" height="70%"><rect x="7" y="7" width="12" height="12" fill="#fff"/><rect x="21" y="21" width="12" height="12" fill="#fff"/><rect x="21" y="7" width="12" height="12" fill="none" stroke="#fff" stroke-width="3"/></svg>',
    '<svg viewBox="0 0 40 40" width="70%" height="70%"><path d="M8 28 Q20 2 32 28" fill="none" stroke="#fff" stroke-width="5"/><path d="M8 34 H32" stroke="#fff" stroke-width="4"/></svg>',
]


def logo_mark(name, script, rng):
    """Logo content: initials for Latin / Cyrillic names, otherwise an abstract mark (initial letters of Indic or
    Arabic-script words without their vowel signs are not how such logos are written)."""
    if script in ("latin", "cyrillic"):
        return f'<span>{esc("".join(w[0] for w in (name or "ORG").split()[:3]).upper()[:3])}</span>'
    return rng.choice(MARKS)


def img(path, style="width:100%;height:auto;display:block;"):
    return f'<img src="file://{esc(path)}" style="{style}">'

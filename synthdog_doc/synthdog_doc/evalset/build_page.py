"""Portal page for the real-document multilingual eval set (task 3, branch feat/real-evalset).

  python3 -m synthdog_doc.evalset.build_page --pages /data/synthdog-doc/evalset/pages --portal /data/synthdog-doc/portal

Reads the eval-set manifest, verification verdicts, annotation agreement and (when present) benchmark results
(/data/synthdog-doc/bench/runs/real1591/report.json), writes <portal>/evalset.html and sample overlays under
<portal>/p2/evalset/. Same look as the other phase-2 pages (light theme by default, UTF-8 declared first).
"""
import argparse
import collections
import html
import json
import re
from pathlib import Path

TYPES = ["ppt", "exam", "paper_single", "paper_double", "newspaper", "magazine", "book", "textbook", "report"]
TYPE_ZH = {"ppt": "PPT", "exam": "试卷", "paper_single": "单栏论文", "paper_double": "双栏论文", "newspaper": "报纸",
           "magazine": "杂志", "book": "书籍", "textbook": "教材", "report": "研报"}
LANG_ZH = {"hi": "印地文", "es": "西班牙文", "ar": "阿拉伯文", "fr": "法文", "bn": "孟加拉文", "pt": "葡萄牙文", "id": "印尼文",
           "ur": "乌尔都文", "ru": "俄文", "de": "德文", "en": "英文", "zh-Hans": "简体中文", "zh-Hant": "繁体中文",
           "ja": "日文", "ko": "韩文", "vi": "越南文", "th": "泰文", "tr": "土耳其文", "fa": "波斯文", "it": "意大利文",
           "pl": "波兰文", "nl": "荷兰文"}
OPEN_DOMAIN = re.compile(r"(\.gov(\.[a-z]{2})?|\.gob\.[a-z]{2}|\.gouv\.[a-z]{2}|\.go\.(jp|kr|th|id)|\.gov\.[a-z]{2}|"
                         r"\.edu(\.[a-z]{2})?|\.ac\.[a-z]{2}|\.europa\.eu|\.un\.org|\.int|\.nic\.in)$")
CAT_COLOR = {"title": (198, 40, 40), "text_block": (30, 90, 200), "figure": (20, 140, 70), "figure_caption": (20, 140, 70),
             "table": (220, 120, 0), "table_caption": (220, 120, 0), "equation_isolated": (140, 60, 200),
             "header": (110, 110, 110), "footer": (110, 110, 110), "page_number": (110, 110, 110),
             "page_footnote": (0, 150, 160), "reference": (90, 60, 30)}


def e(x):
    return html.escape(str(x if x is not None else "—"))


def overlay(img_path, gt, out, w=640):
    from PIL import Image, ImageDraw  # noqa: PLC0415
    im = Image.open(img_path).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    for b in gt["layout_dets"]:
        x0, y0, x1, y1 = b["poly"][0], b["poly"][1], b["poly"][4], b["poly"][5]
        c = CAT_COLOR.get(b["category_type"], (60, 60, 60))
        d.rectangle([x0, y0, x1, y1], outline=c + (255,), width=max(2, im.width // 500), fill=c + (28,))
        if b.get("order") is not None:
            d.text((x0 + 3, y0 + 2), str(b["order"]), fill=c + (255,))
    im.thumbnail((w, w * 2))
    im.save(out, quality=82)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="/data/synthdog-doc/evalset/pages")
    ap.add_argument("--portal", default="/data/synthdog-doc/portal")
    ap.add_argument("--bench", default="/data/synthdog-doc/bench/runs/real1591/report.json")
    ap.add_argument("--synthetic", default="/data/synthdog-doc/bench/runs/bench1980/report.json")
    ap.add_argument("--release", default="/data/synthdog-doc/evalset/release/v1")
    a = ap.parse_args()
    root, portal = Path(a.pages), Path(a.portal)
    man = [json.loads(x) for x in (root / "manifest.jsonl").read_text().splitlines() if x.strip()]
    docs = {(m["lang"], m["doc_type"], m["doc_id"]) for m in man}
    cell_docs = collections.Counter((l, t) for l, t, _ in docs)
    cell_pages = collections.Counter((m["lang"], m["doc_type"]) for m in man)
    langs = sorted({m["lang"] for m in man}, key=lambda l: list(LANG_ZH).index(l) if l in LANG_ZH else 99)
    # coverage matrix
    rows = []
    for lg in langs:
        cells = []
        for t in TYPES:
            nd, npg = cell_docs[(lg, t)], cell_pages[(lg, t)]
            cls = "best" if nd >= 5 else ("" if nd >= 3 else "weak")
            cells.append(f'<td class="n"><span class="{cls}">{nd} / {npg}</span></td>' if nd else '<td class="n weak">N/A</td>')
        rows.append(f"<tr><td><b>{e(LANG_ZH.get(lg, lg))}</b> {e(lg)}</td>{''.join(cells)}"
                    f"<td class='n'>{sum(cell_pages[(lg, t)] for t in TYPES)}</td></tr>")
    cov = (f'<div class="scroll"><table class="t"><thead><tr><th>语言</th>'
           + "".join(f"<th>{TYPE_ZH[t]}</th>" for t in TYPES) + "<th>页数</th></tr></thead><tbody>"
           + "".join(rows) + "</tbody></table></div>")
    full = sum(1 for k, v in cell_docs.items() if v >= 5)
    open_dom = sum(1 for _, _, d in docs if False)
    doms = {}
    for m in man:
        doms[(m["lang"], m["doc_type"], m["doc_id"])] = m["domain"]
    n_open = sum(1 for dom in doms.values() if OPEN_DOMAIN.search(dom or ""))
    born = sum(1 for m in man if m.get("born_digital"))
    # annotation agreement
    agree = [json.loads(x) for x in (root / "agreement.jsonl").read_text().splitlines()] if (root / "agreement.jsonl").exists() else []
    if agree:
        ca = [x["cat_agree"] for x in agree if x.get("cat_agree") is not None]
        oa = [x["order_agree"] for x in agree if x.get("order_agree") is not None]
        ts = collections.Counter()
        for x in agree:
            ts.update(x.get("text_source") or {})
        three = sum(1 for x in agree if len(x.get("annotators", [])) == 3)
        ann_html = (f"<div class='kpis'><div class='kpi'><b>{len(agree)}</b>已出标注页</div>"
                    f"<div class='kpi'><b>{three}</b>三方齐全的页</div>"
                    f"<div class='kpi'><b>{sum(ca) / len(ca):.2f}</b>区域类别平均一致率</div>"
                    f"<div class='kpi'><b>{sum(oa) / len(oa):.2f}</b>阅读顺序两两一致率</div>"
                    f"<div class='kpi'><b>{ts['text_layer'] / max(1, sum(ts.values()) - ts['missed_added']) * 100:.0f}%</b>文本块直接取自 PDF 文字层</div>"
                    f"<div class='kpi'><b>{ts['missed_added']}</b>处漏框文字经 ≥2 人报告后补入</div></div>"
                    "<p class='note'>一致率要打折看：区域和初始顺序都由检测器提出，标注者倾向于接受（锚定效应），所以一致率偏高；"
                    "它说明三人没有大的分歧，不能单独证明真值正确。自评偏差见下方“留一法”。</p>")
    else:
        ann_html = "<p class='note'>标注进行中。</p>"
    # samples
    samp = []
    (portal / "p2" / "evalset").mkdir(parents=True, exist_ok=True)
    picked = set()
    for m in man:
        key = (m["lang"], m["doc_type"])
        g = root / "gt" / f"{m['page_id']}.json"
        if key in picked or not g.exists() or len(samp) >= 36:
            continue
        if m["lang"] not in ("ar", "ja", "zh-Hant", "hi", "th", "ko", "fa", "ru", "de", "en", "vi", "bn"):
            continue
        picked.add(key)
        out = portal / "p2" / "evalset" / f"{m['page_id']}.jpg"
        if not out.exists():
            overlay(root / "images" / m["lang"] / f"{m['page_id']}.jpg", json.loads(g.read_text()), out)
        samp.append((f"p2/evalset/{m['page_id']}.jpg", f"{LANG_ZH.get(m['lang'], m['lang'])} · {TYPE_ZH[m['doc_type']]}"))
    samp_html = "".join(f'<figure><img src="{p}" loading="lazy" alt=""><figcaption>{e(c)}</figcaption></figure>' for p, c in samp)
    # benchmark on the real set
    bench_html = "<p class='note'>真实集上的 7 个模型评测在标注完成后打分。</p>"
    bp = Path(a.bench)
    if bp.exists():
        rep = json.loads(bp.read_text())
        M = rep["models"]
        rows = []
        best = max(m["overall"] for n, m in M.items() if n != "gt-oracle" and m.get("overall") is not None)
        for n, m in M.items():
            if n == "gt-oracle":
                continue
            loo = m.get("overall_loo")
            rows.append(f"<tr><td><b>{e(m['display'])}</b></td>"
                        f"<td class='n'><span class='{'best' if m['overall'] == best else ''}'>{m['overall']:.2f}</span></td>"
                        f"<td class='n'>{f'{loo:.2f}' if loo is not None else '—'}</td>"
                        f"<td class='n'>{m['text_edit']:.3f}</td><td class='n'>{(m['formula_cdm'] or 0) * 100:.1f}</td>"
                        f"<td class='n'>{(m['table_teds'] or 0) * 100:.1f}</td><td class='n'>{m['reading_order_edit']:.3f}</td></tr>")
        bench_html = ('<div class="scroll"><table class="t"><thead><tr><th>模型</th><th>综合分 ↑</th><th>留一法综合分</th>'
                      '<th>文本编辑距离 ↓</th><th>公式 CDM ↑</th><th>表格 TEDS ↑</th><th>阅读顺序 ↓</th></tr></thead><tbody>'
                      + "".join(rows) + "</tbody></table></div>")
        if "gt-oracle" in M:
            bench_html += f"<p class='note'>标注自检（拿真值当答案）综合分 {M['gt-oracle']['overall']:.2f}。</p>"
        # leave-one-out: every model scored on both reduced GTs; the subject's own shift vs the others' shift
        var_names = sorted({v for m in M.values() for v in (m.get("variants") or {})})
        if var_names:
            vz = {"noastra": "去掉 GPT-6-Astra 的标注", "noopus": "去掉 Claude Opus 5.5 的标注"}
            lrows = []
            for n, m in M.items():
                if n == "gt-oracle" or not m.get("variants"):
                    continue
                cells = []
                for v in var_names:
                    o = (m["variants"].get(v) or {}).get("overall")
                    cells.append(f"<td class='n'>{o - m['overall']:+.2f}</td>" if o is not None else "<td class='n'>—</td>")
                lrows.append(f"<tr><td><b>{e(m['display'])}</b></td>{''.join(cells)}</tr>")
            bench_html += ("<h3 style='margin-top:14px'>留一法：换一种真值，分数变化多少</h3>"
                           "<p>同一批预测，分别对“三人共识真值”和“去掉某位标注者后、只用另外两人重建的真值”打分。如果某个模型给自己出题占了便宜，"
                           "去掉它自己那一票时它的分数会比别的模型掉得更多。</p>"
                           '<div class="scroll"><table class="t"><thead><tr><th>模型</th>'
                           + "".join(f"<th>{e(vz.get(v, v))}（分差）</th>" for v in var_names)
                           + "</tr></thead><tbody>" + "".join(lrows) + "</tbody></table></div>")
        syn = Path(a.synthetic)
        if syn.exists():
            S = json.loads(syn.read_text())["models"]
            common = [n for n in M if n in S and n != "gt-oracle"]
            if len(common) >= 3:
                def rk(d):
                    o = sorted(common, key=lambda k: -d[k])
                    return {k: i for i, k in enumerate(o)}
                ra, rb = rk({n: S[n]["overall"] for n in common}), rk({n: M[n]["overall"] for n in common})
                k = len(common)
                rho = 1 - 6 * sum((ra[x] - rb[x]) ** 2 for x in common) / (k * (k * k - 1))
                conc = sum(1 for i in range(k) for j in range(i + 1, k)
                           if (ra[common[i]] - ra[common[j]]) * (rb[common[i]] - rb[common[j]]) > 0)
                tau = (2 * conc - k * (k - 1) / 2) / (k * (k - 1) / 2)
                order_s = " > ".join(S[n]["display"] for n in sorted(common, key=lambda n: -S[n]["overall"]))
                order_r = " > ".join(M[n]["display"] for n in sorted(common, key=lambda n: -M[n]["overall"]))
                bench_html += (f"<h3 style='margin-top:14px'>与合成集的排名是否一致</h3><p>Spearman ρ = <b>{rho:.2f}</b>，"
                               f"Kendall τ = <b>{tau:.2f}</b>（{k} 个模型）。</p><p class='note'>合成集（22 语 1980 页）：{e(order_s)}<br>"
                               f"真实集：{e(order_r)}</p>")
        langs_r = sorted({kk.split(": ")[1] for m in M.values() for kk in m["buckets"] if kk.startswith("sdd_lang: ")},
                         key=lambda l: list(LANG_ZH).index(l) if l in LANG_ZH else 99)
        lr = []
        for n, m in M.items():
            cells = []
            for lg in langs_r:
                b = m["buckets"].get(f"sdd_lang: {lg}") or {}
                v, star = b.get("overall"), ""
                if v is None:            # no formulas / tables on this language's pages: mean of available components
                    comps = [x for x in ((1 - b["text_edit"]) * 100 if b.get("text_edit") is not None else None,
                                         b["formula_cdm"] * 100 if b.get("formula_cdm") is not None else None,
                                         b["table_teds"] * 100 if b.get("table_teds") is not None else None) if x is not None]
                    v, star = (sum(comps) / len(comps), "*") if comps else (None, "")
                cells.append(f"<td class='n'><span class='{'weak' if v is not None and v < 80 else ''}'>{v:.1f}{star}</span></td>"
                             if v is not None else "<td class='n'>—</td>")
            lr.append(f"<tr><td><b>{e(m['display'])}</b></td>{''.join(cells)}</tr>")
        bench_html += ("<h3 style='margin-top:14px'>分语言</h3><div class='scroll'><table class='t'><thead><tr><th>模型</th>"
                       + "".join(f"<th>{e(LANG_ZH.get(l, l))}</th>" for l in langs_r) + "</tr></thead><tbody>" + "".join(lr)
                       + "</tbody></table></div><p class='note'>带 * 的格：该语种的页面里没有独立公式（或没有表格），三项综合分算不出来，取可用项的平均。红色 = 低于 80。</p>")
    # release package
    rel_html = "<p class='note'>发布包在标注完成后生成。</p>"
    rm = Path(a.release) / "manifest.jsonl"
    if rm.exists():
        rman = [json.loads(x) for x in rm.read_text().splitlines() if x.strip()]
        tiers = collections.Counter(x["tier"] for x in rman)
        rel_html = (f"<div class='kpis'><div class='kpi'><b>{len(rman)}</b>发布页</div><div class='kpi'><b>{tiers.get('A', 0)}</b>A 层（含页面图像）</div>"
                    f"<div class='kpi'><b>{tiers.get('B', 0)}</b>B 层（指针 + 渲染脚本）</div></div>"
                    "<p>发布包：<code>omnidocbench_gt.json</code>（真值）、<code>manifest.jsonl</code>（原始网址、WARC 位置、页码、DPI、PDF 哈希、许可层）、"
                    "<code>images/</code>（A 层图像）、<code>render_pages.py</code>（从原始 PDF 重建任意页，抽测与发布图像逐像素一致）、"
                    "<code>annotations/</code>（三位标注者原始答案，可做留一法）、英文数据卡 README。</p>")
    style = (portal / "index.html").read_text(encoding="utf-8")
    style = style[style.index("<style>"):style.index("</style>") + len("</style>")]
    nav = "".join(f'<a href="{f}"{" class=\"on\"" if f == "evalset.html" else ""}>{t}</a>' for f, t in
                  [("p2.html", "第二阶段总览"), ("languages.html", "语言扩展"), ("datapool.html", "数据池"),
                   ("train.html", "训练数据"), ("benchmark.html", "模型评测"), ("evalset.html", "真实评测集"),
                   ("production.html", "批量生产")])
    body = f"""
<section><h1>真实多语种文档评测集</h1>
<p class="sub">合成数据好不好，最终要在真实文档上检验。这里从 CommonCrawl 抓到的真实 PDF 里，为 22 个语种 × 9 类版面各找 5 份文档、每份抽 2 页，用三个最强模型构建 OmniDocBench 格式的标注，目标是一个可以开源发布的评测集。</p>
<div class="kpis"><div class="kpi"><b>{len(man)}</b>评测页</div><div class="kpi"><b>{len(docs)}</b>份真实 PDF</div>
<div class="kpi"><b>{len(langs)}</b>个语种</div><div class="kpi"><b>{full}</b> / {len(langs) * 9} 格凑满 5 份文档</div>
<div class="kpi"><b>{born / max(1, len(man)) * 100:.0f}%</b>原生 PDF（有文字层）</div></div></section>
<section><h2>怎么做的（通俗版）</h2>
<div class="grid g3">
<div class="card"><h3>1. 找文档</h3><p>从 FinePDFs 每语种随机抽约 4000 份候选 PDF，先让 GPT-6.1-Sol 只看开头文字分出“PPT / 试卷 / 论文 / 报纸 / 杂志 / 书籍 / 教材 / 研报 / 其他”，每格挑最像的 15~40 份去下载。</p></div>
<div class="card"><h3>2. 取原件、看一眼</h3><p>CommonCrawl 对公司出口限流，改由数采平台按原始网址下载（约四成网址仍有效）；每份 PDF 拼一张 4 页缩略图让模型确认类型、栏数、语种和清晰度，单栏 / 双栏论文由此区分。</p></div>
<div class="card"><h3>3. 抽页、标注</h3><p>每格最多 5 份文档、每份随机 2 页（书籍 / 教材 / 研报 / 杂志跳过封面）。框来自版面检测模型 PP-DocLayoutV3 与 PDF 文字层，三个模型只负责改类别、确认或转写文字、写公式 LaTeX 与表格 HTML、排阅读顺序。</p></div></div></section>
<section><h2>设计要点（给评审看）</h2>
<div class="grid g2"><div class="card"><h3>为什么框不让大模型画</h3><p>大模型给的坐标不准。框取自检测模型 + 文字层，大模型只在带编号的框上做“合并 / 拆分 / 改类 / 排序”（set-of-mark），几何精度由检测与文字层保证。</p></div>
<div class="card"><h3>文本以文字层为准</h3><p>原生 PDF 的文字层就是排版用的原文；三位标注者里有 2 位确认无误才采用，否则（扫描件、编码错乱的天城 / 阿拉伯字体等）取三位转写的中位版本。</p></div>
<div class="card"><h3>自评偏差怎么控制</h3><p>被评测的 7 个模型里也有 GPT-6-Astra 和 Opus 5.5。对策：Gemini-4-Argon（不在被测名单）作为标注者之一；文本主要来自文字层；三方独立作答、互不可见；保留每位标注者的原始答案，可在评某个模型时去掉它的那一票重算真值（留一法），报告偏差量。</p></div>
<div class="card"><h3>不做人工核验（用户决定）</h3><p>按用户要求，本版不安排人工逐页核验；三方一致率和分歧页清单随数据发布，供使用者判断。</p></div></div></section>
<section><h2>覆盖矩阵（文档数 / 页数）</h2>{cov}
<p class="note">绿色 = 凑满 5 份文档；红色 / N/A = 不足 3 份或缺失。凑不齐的格不用合成页或别的语种补，如实留空。报纸、杂志、PPT 在中小语种里最难找。</p></section>
<section><h2>标注质量</h2>{ann_html}</section>
<section><h2>许可与发布</h2>{rel_html}
<div class="card"><p>按两层发布：A 层（政府、教育机构、开放许可期刊等可再分发的文档）发布页面图像 + 标注；B 层只发布原始 URL、CommonCrawl WARC 指针、页码、PDF 哈希、固定 DPI 渲染脚本和标注，限研究用途、提供下架通道。按域名粗分，当前约 <b>{n_open}</b> / {len(doms)} 份文档来自政府 / 教育机构域名，逐份许可仍需发布前核对。</p></div></section>
<section><h2>标注样例</h2><div class="thumbs">{samp_html}</div></section>
<section><h2>模型在真实集上的表现</h2>{bench_html}</section>
"""
    doc = f"""<!doctype html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>真实评测集 · SynthDoG-Doc</title>
<script>(function(){{var t='light';try{{t=localStorage.getItem('portal-theme-light-v1')||'light'}}catch(e){{}}document.documentElement.setAttribute('data-theme',t);}})();</script>
{style}
<style>
table.t{{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--panel)}}
table.t th,table.t td{{border:1px solid var(--line);padding:5px 8px;text-align:left}}
table.t th{{background:var(--soft)}} table.t td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.scroll{{overflow-x:auto}} .best{{font-weight:700;color:var(--green)}} .weak{{color:var(--red)}}
.note{{color:var(--muted);font-size:13px}}
.thumbs{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}}
.thumbs figure{{margin:0}} .thumbs img{{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff}}
.thumbs figcaption{{font-size:12px;color:var(--muted);text-align:center}}
</style>
</head>
<body>
<header class="top"><div class="topin">
  <div class="brand"><a href="index.html" style="text-decoration:none">SynthDoG-Doc</a></div>
  <nav id="nav">{nav}<a href="index.html">第一阶段门户</a></nav>
  <button id="themebtn" title="切换浅色 / 深色">🌓 主题</button>
</div></header>
<main>{body}</main>
<script>document.getElementById('themebtn').onclick=function(){{var r=document.documentElement;var t=r.getAttribute('data-theme')==='dark'?'light':'dark';r.setAttribute('data-theme',t);try{{localStorage.setItem('portal-theme-light-v1',t)}}catch(e){{}}}};</script>
</body>
</html>
"""
    (portal / "evalset.html").write_text(doc, encoding="utf-8")
    print("evalset.html written", len(man), "pages", len(samp), "samples")


if __name__ == "__main__":
    main()

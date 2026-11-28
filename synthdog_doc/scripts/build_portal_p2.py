"""Phase-2 portal pages: overview, languages, data pool, benchmark, production (the real eval set has its own page,
built on branch feat/real-evalset). Static HTML in the same style as the phase-1 portal (light theme by default,
UTF-8 declared first); each page reads only local JSON summaries.

  python3 scripts/build_portal_p2.py --portal /data/synthdog-doc/portal
"""
import argparse
import html
import json
import re
import shutil
from pathlib import Path

D = Path("/data/synthdog-doc")
PAGES = [("p2.html", "第二阶段总览"), ("languages.html", "语言扩展"), ("datapool.html", "数据池"),
         ("benchmark.html", "模型评测"), ("evalset.html", "真实评测集"), ("production.html", "批量生产")]
TYPE_ZH = {"ppt": "PPT", "exam": "试卷", "paper_single": "单栏论文", "paper_double": "双栏论文", "newspaper": "报纸",
           "magazine": "杂志", "book": "书籍", "textbook": "教材", "report": "研报"}


def e(x):
    return html.escape(str(x if x is not None else "—"))


def style_of(portal):
    s = (portal / "index.html").read_text(encoding="utf-8")
    return s[s.index("<style>"):s.index("</style>") + len("</style>")]


def page(portal, fname, title, body, extra_css=""):
    nav = "".join(f'<a href="{f}"{" class=\"on\"" if f == fname else ""}>{t}</a>' for f, t in PAGES)
    doc = f"""<!doctype html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · SynthDoG-Doc</title>
<script>(function(){{var t='light';try{{t=localStorage.getItem('portal-theme-light-v1')||'light'}}catch(e){{}}document.documentElement.setAttribute('data-theme',t);}})();</script>
{style_of(portal)}
<style>
table.t{{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--panel)}}
table.t th,table.t td{{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}}
table.t th{{background:var(--soft);font-weight:600}}
table.t td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.scroll{{overflow-x:auto}}
.best{{font-weight:700;color:var(--green)}}
.weak{{color:var(--red)}}
.pill{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;background:var(--pri-soft);color:var(--pri);margin-right:4px}}
.note{{color:var(--muted);font-size:13px}}
.thumbs{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}}
.thumbs figure{{margin:0}} .thumbs img{{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff}}
.thumbs figcaption{{font-size:12px;color:var(--muted);text-align:center}}
{extra_css}
</style>
</head>
<body>
<header class="top"><div class="topin">
  <div class="brand"><a href="index.html" style="text-decoration:none">SynthDoG-Doc</a></div>
  <nav id="nav">{nav}<a href="index.html">第一阶段门户</a></nav>
  <button id="themebtn" title="切换浅色 / 深色">🌓 主题</button>
</div></header>
<main>
{body}
</main>
<script>
document.getElementById('themebtn').onclick=function(){{var r=document.documentElement;var t=r.getAttribute('data-theme')==='dark'?'light':'dark';r.setAttribute('data-theme',t);try{{localStorage.setItem('portal-theme-light-v1',t)}}catch(e){{}}}};
</script>
</body>
</html>
"""
    (portal / fname).write_text(doc, encoding="utf-8")


def table(head, rows, num_cols=()):
    th = "".join(f"<th>{h}</th>" for h in head)
    trs = []
    for r in rows:
        tds = "".join(f'<td class="n">{c}</td>' if i in num_cols else f"<td>{c}</td>" for i, c in enumerate(r))
        trs.append(f"<tr>{tds}</tr>")
    return f'<div class="scroll"><table class="t"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def fmt(x, d=2, pct=False):
    if x is None:
        return "—"
    return f"{x * 100:.{d}f}" if pct else f"{x:.{d}f}"


def thumbs(portal, src_dir, pattern_list, sub, w=420):
    """Copy (resized) page images into portal/p2/<sub>/ and return relative paths."""
    from PIL import Image  # noqa: PLC0415
    out = portal / "p2" / sub
    out.mkdir(parents=True, exist_ok=True)
    res = []
    for name, cap in pattern_list:
        src = Path(src_dir) / f"{name}.jpg"
        if not src.exists():
            continue
        dst = out / f"{name}.jpg"
        if not dst.exists():
            im = Image.open(src).convert("RGB")
            im.thumbnail((w, w * 2))
            im.save(dst, quality=82)
        res.append((f"p2/{sub}/{name}.jpg", cap))
    return res


# ------------------------------------------------------------------------------------------------ pages
def build_languages(portal):
    L = json.loads((D / "portal_src/languages.json").read_text())
    rows = []
    for r in L["languages"]:
        tags = (('<span class="pill">Top-15</span>' if r["top15"] else "") +
                ('<span class="pill">Top-20</span>' if r["top20"] and not r["top15"] else ""))
        rows.append([e(r["rank"] or ""), f"<b>{e(r['zh'])}</b>", e(r["en"]), e(r["native"]), e(r["code"]), e(r["script"]),
                     e(r["tier"]), e(r["speakers_m"] if r["speakers_m"] else "（与简体合计）"), e(r["finepdfs_m"]),
                     e(r["fineweb2_m"]), e(r["ppocrv5"]), tags])
    langs_tbl = table(["序", "中文名", "英文名", "本地写法", "代码", "文字系统", "分层", "使用人数（百万）",
                       "FinePDFs 文档（百万）", "FineWeb-2 文档（百万）", "PP-OCRv5 覆盖", "规模目标"], rows,
                      num_cols=(0, 7, 8, 9))
    # v7 pages from the new-language benchmark sample (first clean digital page per language x type)
    man = [json.loads(x) for x in (D / "bench/bench1080/manifest.jsonl").read_text().splitlines() if x.strip()]
    Lz = {r["code"]: r["zh"] for r in L["languages"]}
    samples = []
    for code in ["zh-Hans", "zh-Hant", "ja", "ko", "vi", "th", "en", "tr", "fa", "it", "pl", "nl"]:
        for t in ["newspaper", "paper_double", "book", "exam"]:
            cand = [m for m in man if m["lang"] == code and m["doc_type"] == t]
            pick = next((m for m in cand if m["branch"] == "digital"), cand[0] if cand else None)
            if pick:
                samples.append((pick["name"], f"{Lz.get(code, code)} · {TYPE_ZH[t]}"))
    th = thumbs(portal, D / "bench/bench1080/images", samples, "lang")
    vert = []
    th_html = "".join(f'<figure><img src="{p}" loading="lazy" alt=""><figcaption>{e(c)}</figcaption></figure>'
                      for p, c in vert + th)
    J = json.loads((D / "portal_src/judge_p2.json").read_text()) if (D / "portal_src/judge_p2.json").exists() else {}
    judge_html = ""
    if J.get("p2_r1") and J.get("p2_r2"):
        r1, r2 = J["p2_r1"], J["p2_r2"]

        def pc(x):
            return f"{x * 100:.0f}%" if x is not None else "—"
        jrows = [[f"<b>{e({'sol': 'GPT-6.1-Sol', 'opus': 'Claude Opus 5.5'}.get(j, j))}</b>", e(r2["by_judge"][j]["n_syn"]),
                  pc(r1["by_judge"][j]["fool_rate"]), f"<b>{pc(r2['by_judge'][j]['fool_rate'])}</b>",
                  pc(r2["by_judge"][j]["real_recall"])] for j in r2["by_judge"]]
        jt = table(["评委", "合成页数", "误判为真（v6）", "误判为真（v7）", "真页识别为真"], jrows, num_cols=(1, 2, 3, 4))
        trows = [[f"<b>{e(TYPE_ZH.get(t, t))}</b>", pc(r1["by_type"].get(t, {}).get("fool_rate")),
                  f"<b>{pc(v['fool_rate'])}</b>", fmt(r1["by_type"].get(t, {}).get("overall"), 2), fmt(v["overall"], 2)]
                 for t, v in r2["by_type"].items()]
        tt = table(["文档类型", "误判为真 v6", "误判为真 v7", "整体真实感 v6（1–5）", "整体真实感 v7"], trows, num_cols=(1, 2, 3, 4))
        Lz = {r["code"]: r["zh"] for r in L["languages"]}
        lrows = [[f"<b>{e(Lz.get(c, c))}</b>", pc(r1["by_lang"].get(c, {}).get("fool_rate")), f"<b>{pc(v.get('fool_rate'))}</b>",
                  fmt(r1["by_lang"].get(c, {}).get("overall"), 2), fmt(v.get("overall"), 2)] for c, v in r2["by_lang"].items()]
        lt = table(["语言", "误判为真 v6", "误判为真 v7", "整体真实感 v6", "整体真实感 v7"], lrows, num_cols=(1, 2, 3, 4))
        judge_html = f"""<section><h2>新语言盲评：v6 → v7</h2>
<p>两位评委（GPT-6.1-Sol、Claude Opus 5.5）各自独立看图，判断“真文档还是合成页”，并按版式、排印、本地习惯、内容连贯、整体真实感 1–5 分打分；每轮 12 种新语言 × 9 类，混入 26 张真实页做对照。第一轮（v6）的问题清单逐条修复后重评（v7）：货币金额、对冲句、波斯 / 泰文本地数字、试卷题号与标签、书籍脚注与插图、中日文标题断词与段末孤字。</p>
<div class="grid g2"><div>{jt}</div><div class="card"><h3>怎么读</h3><p>“误判为真”= 评委把合成页当成真实文档的比例，越高说明越像真的；“真页识别为真”是对照组，两轮都是 100%，说明评委没有乱判。Opus 比 Sol 严格得多，所以两人分开看。</p></div></div>
<div class="grid g2" style="margin-top:14px"><div>{tt}</div><div>{lt}</div></div>
<p class="note">每格样本量小（每类型 24 份评审、每语言 17~18 份），只看趋势，不做显著性结论。书籍、PPT 已接近“以假乱真”；双栏论文、研报、报纸仍容易被识破，主要扣分点是内容拼接痕迹（句子从半截开始、段落主题跳跃）和成像过于均匀。</p></section>"""
    body = f"""
<section><h1>语言扩展：从 10 种到 22 种</h1>
<p class="sub">第一阶段只覆盖去掉中英文后的 Top-10。第二阶段按“业务需要 → 真实语料够不够 → 排版能不能做好 → 使用人数”的顺序，新增 12 种，并定出开源库的 Top-15 与压测用的 Top-20。</p>
<div class="kpis"><div class="kpi"><b>22</b>支持的语言 / 书写配置</div><div class="kpi"><b>12</b>本阶段新增</div>
<div class="kpi"><b>Top-15</b>开源库每种 ≥10 万页</div><div class="kpi"><b>Top-20</b>批量压测每种 1 万页</div></div>
</section>
<section><h2>选择逻辑（通俗版）</h2>
<div class="grid g2"><div class="card"><h3>一句话</h3><p>像给团队排课题优先级：先看谁“非做不可”（中英文、中国周边、欧美发达国家、人口大国），再看“有没有米下锅”（网上有没有足够多的真实文档文本），再看“锅能不能炒”（字体、断行、从右往左等排版能不能做对），最后同档里按使用人数排。</p></div>
<div class="card"><h3>为什么不用一个打分公式</h3><p>“人数 × 稀缺度 × 可行性”这类乘法里，稀缺度高的语言往往可行性低，两项互相抵消，排出来的结果解释不清。三位评审模型（GPT-6-Astra、Gemini-4-Argon、Claude Opus 5.5）一致建议改成“门槛 + 排序”。</p></div></div>
<div class="grid g3" style="margin-top:14px">
<div class="card"><h3>门槛 1：真实语料</h3><p>FinePDFs（真实 PDF 正文）+ FineWeb-2（网页正文）里过滤后要有足够多的文档，保证每语种 10 万页不靠重复。</p></div>
<div class="card"><h3>门槛 2：字体与排版</h3><p>至少 2 个完整覆盖该文字的开源字体家族；无空格的中日泰、从右往左的波斯 / 乌尔都、叠加声调的越南文都要有对应的断行与排印规则。</p></div>
<div class="card"><h3>门槛 3：评审可控</h3><p>能用盲评 + 自动质检判断“像不像真文档”。朝鲜文因合规原因只作为韩文的内部实验变体，不进开源版。</p></div></div>
</section>
<section><h2>语言总表（中英文对照）</h2>{langs_tbl}
<p class="note">使用人数取 Ethnologue 2026（Wikipedia 表）；简繁中文按书写配置分别计数，不重复计算人口。FinePDFs / FineWeb-2 为 HF datasets-server 实测行数（2026-11-28）。下一阶段候选（T2）：{e(L["t2"])}。</p></section>
<section><h2>新语言要解决的排版问题</h2>
<div class="grid g3">
<div class="card"><h3>中日文</h3><p>按字切分、避头尾（句号逗号不出现在行首、左括号不留在行尾）、标题与短句按词断行、段末不留单字；繁中台湾 / 香港用「」；日文书籍支持竖排（从右往左的竖行）。</p></div>
<div class="card"><h3>泰文</h3><p>词与词之间没有空格：用浏览器内置的 ICU 词典（Intl.Segmenter）切词再排版，保证不在词中间断行；行高加大，避免上下叠加的元音、声调符号被切掉。</p></div>
<div class="card"><h3>韩文</h3><p>按语节（空格分隔的词）断行，不把一个词拆到两行。</p></div>
<div class="card"><h3>越南文</h3><p>统一 Unicode NFC；只用覆盖越南文全部叠加声调的字体；加大行距，框住上方声调。</p></div>
<div class="card"><h3>波斯文</h3><p>从右往左；用波斯专用码位 ی / ک、波斯数字 ۰–۹、波斯小数点与百分号。</p></div>
<div class="card"><h3>土耳其 / 波兰 / 荷兰 / 意大利 / 英文</h3><p>土耳其文大小写 i→İ、ı→I；波兰、意大利、荷兰、英文用词典断字；数字千分位、小数点、百分号按本地习惯（土耳其文写作 %25）。</p></div>
</div></section>
{judge_html}
<section><h2>新语言样张</h2><div class="thumbs">{th_html}</div></section>
"""
    page(portal, "languages.html", "语言扩展", body)


def build_datapool(portal):
    st = json.loads((D / "datapool/pool_stats_v1.json").read_text()) if (D / "datapool/pool_stats_v1.json").exists() else {}
    L = {r["code"]: r for r in json.loads((D / "portal_src/languages.json").read_text())["languages"]}
    rows, tot_pages, tot_chars = [], 0, 0
    for code in sorted(st, key=lambda c: (L.get(c, {}).get("rank") or 99, c)):
        r = st[code]
        if "error" in r:
            continue
        f, w = r["finepdfs"], r.get("fineweb", {})
        tot_pages += f["pages_kept"]
        tot_chars += f["chars_kept"] + w.get("chars_kept", 0)
        rows.append([f"<b>{e(L.get(code, {}).get('zh', code))}</b>", e(code), f"{f['docs_in']:,}", f"{f['docs_kept']:,}",
                     f"{f['docs_kept'] / max(1, f['docs_in']) * 100:.0f}%", f"{f['pages_kept']:,}",
                     f"{f['chars_kept'] / 1e6:.0f}", f"{w.get('docs_kept', 0):,}", f"{w.get('chars_kept', 0) / 1e6:.0f}"])
    tbl = table(["语言", "代码", "FinePDFs 输入文档", "保留文档", "保留率", "保留页", "页文本（百万字符）",
                 "FineWeb-2 保留文档", "网页文本（百万字符）"], rows, num_cols=(2, 3, 4, 5, 6, 7, 8))
    body = f"""
<section><h1>数据池：从“几千篇网页”到“几十万篇真实 PDF”</h1>
<p class="sub">第一阶段的正文原料是每语种几千篇网页（FineWeb-2 抽样）+ 维基百科 + 大模型内容包。要做开源的大规模文档库，第二阶段把主池换成 <b>FinePDFs</b>（CommonCrawl 抓到的真实 PDF 抽取全文，文本天然是“文档”而不是网页），网页正文只用来补新闻、杂志类版面。</p>
<div class="kpis"><div class="kpi"><b>57</b>个 HF 分片（216 GB）经数采平台下载入 JFS</div><div class="kpi"><b>{tot_pages:,}</b>已入池的真实 PDF 页</div>
<div class="kpi"><b>{tot_chars / 1e9:.1f}</b>十亿字符可用正文</div><div class="kpi"><b>{len(rows)}</b>个语种已建池</div></div></section>
<section><h2>来源与许可</h2>
<div class="grid g2"><div class="card"><h3>主池：FinePDFs（ODC-By）</h3><p>HuggingFaceFW/finepdfs，4.76 亿份文档、1732 个语种。每条记录带原始 URL、CommonCrawl WARC 文件与偏移（能取回原始 PDF）、按页切分位置、抽取方式（原生文字层 / OCR）、质量分。每语种先取 1 个分片（约 4.5 GB，数十万文档），规模不够时再加分片。</p></div>
<div class="card"><h3>补充：FineWeb-2（ODC-By）</h3><p>多语种网页正文，按国家域名 / 新闻站过滤后给报纸、杂志版面用；FinePDFs 偏少的乌尔都、孟加拉、印地用它补足。维基百科（CC BY-SA）单列，不混入开源主体。</p></div>
<div class="card"><h3>许可注意</h3><p>ODC-By 只覆盖“数据集的整理”，不转移底层文档的著作权。开源发布时：合成页面只用池中文本的片段重新排版；真实评测集分两层（可再分发文档发图像 + 标注；其余只发链接、WARC 指针和标注）。内部 crop 图片不进开源版，改用 Wikimedia Commons（CC0 / PD / CC BY）与代码重绘的图表。</p></div>
<div class="card"><h3>评测集隔离</h3><p>真实评测集的文档与合成正文同出 FinePDFs，入选评测集的文档 id 会从合成正文池中剔除，避免“考题泄漏”。</p></div></div></section>
<section><h2>清洗规则（每条都计数）</h2>
<div class="card"><ol>
<li><b>语种</b>：整篇语言识别结果与配置一致（中文再按简繁字形分开）。</li>
<li><b>去重</b>：duplicate_count ≤ 1。</li>
<li><b>完整</b>：is_truncated = False（CommonCrawl 截断的不要）。</li>
<li><b>扫描质量</b>：OCR 抽取的扫描件要求 OCR 质量分 ≥ 0.5。</li>
<li><b>文字纯度</b>：目标文字系统的字母占 ≥ 80%——专门拦住老式非 Unicode 字体导致的“乱码 PDF”（印地 Kruti Dev、孟加拉 Bijoy 等）。</li>
<li><b>长度</b>：≥ 500 字符；按 PDF 页边界切成页片段，每页 ≥ 300 字符（中日泰 ≥ 150）。</li>
<li><b>隐私</b>：邮箱 / 电话密度过高的通讯录、表单类整篇丢弃。</li></ol></div></section>
<section><h2>各语种入池统计</h2>{tbl}
<p class="note">一个分片的统计；产物在 JFS <code>processed/synthdog_doc/datapool/v1/&lt;语言&gt;/</code>（finepdfs_pages.parquet、fineweb_docs.parquet）。每语种 10 万合成页约需 3~8 万个不同页片段，Top-15 全部满足。</p></section>
"""
    page(portal, "datapool.html", "数据池", body)


def rank_corr(a, b):
    """Spearman rho and Kendall tau between two {model: score} dicts over their common models."""
    common = [k for k in a if k in b and a[k] is not None and b[k] is not None]
    n = len(common)
    if n < 3:
        return None

    def ranks(d):
        order = sorted(common, key=lambda k: -d[k])
        return {k: i for i, k in enumerate(order)}
    ra, rb = ranks(a), ranks(b)
    rho = 1 - 6 * sum((ra[k] - rb[k]) ** 2 for k in common) / (n * (n * n - 1))
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            x, y = common[i], common[j]
            sgn = (a[x] - a[y]) * (b[x] - b[y])
            conc += sgn > 0
            disc += sgn < 0
    return {"spearman": rho, "kendall": (conc - disc) / (n * (n - 1) / 2), "n": n}


def build_benchmark(portal):
    rep = json.loads((D / "bench/runs/bench1980/report.json").read_text())
    sub = {k: json.loads((D / f"bench/runs/{k}/report.json").read_text())["models"] for k in ("bench900", "bench1080")}
    realp = D / "bench/runs/real1591/report.json"
    real = json.loads(realp.read_text())["models"] if realp.exists() else None
    M = rep["models"]
    names = [n for n in M if n != "gt-oracle"] + (["gt-oracle"] if "gt-oracle" in M else [])
    best = max((M[n]["overall"] for n in names if n != "gt-oracle"))
    best_name = next(M[n]["display"] for n in names if M[n]["overall"] == best)
    rows = []
    for n in names:
        m = M[n]
        ned = (((m.get("text_metric") or {}).get("all") or {}).get("all") or {}).get("ned_strict")
        fa = (m.get("run") or {}).get("first_attempt") or {}
        st = (m.get("run") or {}).get("status") or {}
        fails = sum(v for k, v in fa.items() if k != "ok")
        final_fail = sum(v for k, v in st.items() if k not in ("ok", "missing"))
        ov = f'<span class="{"best" if m["overall"] == best else ""}">{m["overall"]:.2f}</span>'
        rows.append([f"<b>{e(m['display'])}</b>", ov, fmt(sub["bench900"].get(n, {}).get("overall"), 2),
                     fmt(sub["bench1080"].get(n, {}).get("overall"), 2), fmt(m["text_edit"], 3),
                     fmt(m["formula_cdm"], 1, True), fmt(m["table_teds"], 1, True), fmt(m["reading_order_edit"], 3),
                     fmt(ned, 3), "—" if n == "gt-oracle" else f"{fails} / {final_fail}"])
    main_tbl = table(["模型", "综合分 ↑（22 语，1980 页）", "旧 10 语（900 页）", "新 12 语（1080 页）", "文本编辑距离 ↓",
                      "公式 CDM ↑", "表格 TEDS ↑", "阅读顺序 ↓", "页级字符错误率 ↓（保留附标）", "失败页：首次 / 重试后"],
                     rows, num_cols=(1, 2, 3, 4, 5, 6, 7, 8, 9))

    def bucket_table(Ms, prefix, labels, metric="overall", order=None):
        keys = sorted({k.split(": ", 1)[1] for n in names for k in Ms[n]["buckets"] if k.startswith(prefix + ": ")},
                      key=lambda k: (order.index(k) if order and k in order else 99, k))
        out = []
        for n in names:
            if n not in Ms:
                continue
            bs = Ms[n]["buckets"]
            if metric == "text":
                vals = [(lambda b: (1 - b["text_edit"]) * 100 if b and b.get("text_edit") is not None else None)(
                    bs.get(f"{prefix}: {k}")) for k in keys]
            else:
                vals = [(bs.get(f"{prefix}: {k}") or {}).get("overall") for k in keys]
            cells = [f'<span class="{"weak" if v < 80 else ""}">{v:.1f}</span>' if v is not None else "—" for v in vals]
            out.append([f"<b>{e(Ms[n]['display'])}</b>"] + cells)
        return table(["模型"] + [e(labels.get(k, k)) for k in keys], out, num_cols=tuple(range(1, len(keys) + 1)))
    LJ = json.loads((D / "portal_src/languages.json").read_text())["languages"]
    L = {r["code"]: r["zh"] for r in LJ}
    lorder = [r["code"] for r in sorted(LJ, key=lambda r: r["rank"] or 99)]
    lang_tbl = bucket_table(M, "sdd_lang", L, order=lorder)
    type_tbl = bucket_table(M, "sdd_doc_type", TYPE_ZH, metric="text", order=list(TYPE_ZH))
    br_tbl = bucket_table(M, "sdd_branch", {"digital": "数字原生", "scan": "扫描复印", "photo": "手机翻拍"},
                          order=["digital", "scan", "photo"])
    if real:
        rrows = []
        rbest = max(m["overall"] for n, m in real.items() if n != "gt-oracle" and m.get("overall") is not None)
        for n in names:
            if n not in real:
                continue
            m = real[n]
            ned = (((m.get("text_metric") or {}).get("all") or {}).get("all") or {}).get("ned_strict")
            ov = f'<span class="{"best" if m["overall"] == rbest else ""}">{fmt(m["overall"], 2)}</span>'
            loo = fmt(m.get("overall_loo"), 2) if m.get("overall_loo") is not None else "—"
            rrows.append([f"<b>{e(m['display'])}</b>", ov, loo, fmt(m["text_edit"], 3), fmt(m["formula_cdm"], 1, True),
                          fmt(m["table_teds"], 1, True), fmt(m["reading_order_edit"], 3), fmt(ned, 3)])
        rc = rank_corr({n: M[n]["overall"] for n in names if n != "gt-oracle"},
                       {n: real[n]["overall"] for n in real if n != "gt-oracle"})
        real_html = table(["模型", "综合分 ↑", "留一法综合分（去掉自己那一票）", "文本编辑距离 ↓", "公式 CDM ↑", "表格 TEDS ↑",
                           "阅读顺序 ↓", "页级字符错误率 ↓"], rrows, num_cols=(1, 2, 3, 4, 5, 6, 7))
        if rc:
            real_html += (f"<p>合成集（22 语）与真实集的模型排名一致性：Spearman ρ = <b>{rc['spearman']:.2f}</b>，"
                          f"Kendall τ = <b>{rc['kendall']:.2f}</b>（{rc['n']} 个模型）。</p>")
        real_html += ("<h3 style='margin-top:14px'>真实集分语言</h3>" + bucket_table(real, "sdd_lang", L, order=lorder) +
                      "<h3 style='margin-top:14px'>真实集分文档类型（文本得分）</h3>" +
                      bucket_table(real, "sdd_doc_type", TYPE_ZH, metric="text", order=list(TYPE_ZH)))
    else:
        real_html = "<p class='note'>真实评测集的标注完成后在此打分（7 个模型 + 标注自检 + 留一法）。</p>"
    body = f"""
<section><h1>模型评测</h1>
<p class="sub">同一套 OmniDocBench 官方口径，比较 7 个文档解析模型在 SynthDoG-Doc 合成页（22 种语言 × 9 类版面，1980 页）和真实评测集上的表现。</p>
<div class="kpis"><div class="kpi"><b>1980</b>合成评测页（22 语 × 9 类，按成像分支分层）</div><div class="kpi"><b>7</b>个模型</div>
<div class="kpi"><b>{M['gt-oracle']['overall']:.2f}</b>标注自检分（拿标注当答案打分，验证流程）</div><div class="kpi"><b>{best:.2f}</b>最佳综合分（{e(best_name)}）</div></div></section>
<section><h2>总表（合成集）</h2>{main_tbl}
<p class="note">综合分 = ((1 − 文本编辑距离) × 100 + 公式 CDM × 100 + 表格 TEDS × 100) / 3（OmniDocBench v1.5 口径，评分镜像 omnidocbench-eval:v16-flat1）。合成集由两批组成：旧 10 语 900 页（模板 v6）与新 12 语 1080 页（模板 v7），合在一起统一打分。“页级字符错误率”是补充指标：官方文本归一化会删掉组合附标（天城文元音符号、阿拉伯文标音符号等），这里保留它们、按整页阅读顺序计算。失败页（拒答、截断、超时）照常按空输出计分，不剔除；重试一次仍失败的页如实计 0。</p></section>
<section><h2>分语言消融（合成集，综合分）</h2>{lang_tbl}
<p class="note">红色 = 低于 80。MinerU2.5-Pro 与 PaddleOCR-VL-1.6 在阿拉伯文、乌尔都文（Nastaliq）、波斯文上明显掉分；通用大模型在这些语言上保持 87~94。Claude Opus 5.5 的英文分被 9 页英文报纸拖低：这些页两次请求都被网关拦截（输出内容过滤 / 流中断），按规则计为空输出。</p></section>
<section><h2>分文档类型（文本得分）</h2>{type_tbl}
<p class="note">文本得分 = (1 − 文本编辑距离) × 100。书籍、报纸等版面多数页没有公式或表格，算不出三项合成的综合分，所以按类型只比文本。</p></section>
<section><h2>分成像方式（综合分）</h2>{br_tbl}</section>
<section><h2>真实评测集</h2>{real_html}
<p class="note">真实集的构建方法、覆盖矩阵、许可分层见 <a href="evalset.html">真实评测集</a> 页。GPT-6-Astra 与 Claude Opus 5.5 同时是标注者之一，表中“留一法”一列是去掉该模型的标注、只用另外两位标注者重建真值后的得分，用来衡量“自己给自己出题”的偏差。</p></section>
<section><h2>评测设置</h2>
<div class="grid g2"><div class="card"><h3>模型与推理</h3><ul>
<li>MinerU2.5-Pro（1.2B）：官方两阶段（版面 → 逐块识别），vLLM 服务，1×H100。</li>
<li>PaddleOCR-VL-1.6（0.9B）：PP-DocLayoutV3 版面 + 逐区域识别的两阶段复现（阅读顺序用 XY-cut，不是官方排序模型，偏保守）。</li>
<li>Qwen3.5-4B：不开 thinking、repetition penalty 1.1、4MP；Qwen3.8-27B：开 thinking、不加 penalty、4MP。</li>
<li>GPT-6-Astra / GPT-6.1-Sol / Claude Opus 5.5：统一的多语种整页 Markdown 提示词（要求原文照录、不翻译、保留本地数字，RTL 先右栏），effort = medium。</li></ul></div>
<div class="card"><h3>口径要点</h3><ul>
<li>页眉、页脚、页码按 OmniDocBench 规则不计分；图注照常转写。</li>
<li>修正了合成标注中关系字段名（relation → relation_type）与官方不一致的问题，否则评分器报错。</li>
<li>网关并发上限导致的失败（Concurrency limit）属于基础设施问题，原样重试；模型自身的拒答、截断、内容过滤只重试一次，结果如实计分。</li></ul></div></div></section>
"""
    page(portal, "benchmark.html", "模型评测", body)


def build_production(portal):
    P = json.loads((D / "portal_src/production.json").read_text()) if (D / "portal_src/production.json").exists() else {}
    bench = P.get("bench", [])
    rows = [[f"<b>{e(b['name'])}</b>", e(b.get("desc")), e(b["pages"]), f"{b['wall']:.0f}", f"{b['pages'] / b['wall']:.2f}",
             f"{b['cpu'] / b['pages']:.2f}", f"{b['cpu'] / b['wall']:.0f}"] for b in bench]
    btbl = table(["配置", "说明", "页数", "墙钟（秒）", "页 / 秒", "实耗 CPU 核·秒 / 页", "平均占用核数"], rows,
                 num_cols=(2, 3, 4, 5, 6)) if rows else "<p class='note'>压测进行中。</p>"
    bo = P.get("bakeoff", {})
    borows = [[f"<b>{e(r['name'])}</b>", e(r.get("all")), e(r.get("paper")), e(r.get("exam")), e(r.get("news")),
               e(r.get("cost_pack")), e(r.get("note", ""))] for r in bo.get("rows", [])]
    botbl = table(["候选模型", "不劣于 Sol（全部）", "论文", "试卷", "新闻编辑", "每包成本（USD，公开价量级）", "说明"], borows) \
        if borows else ""
    prod = P.get("run200k", {})
    if prod.get("groups"):
        Lz = {r["code"]: r["zh"] for r in json.loads((D / "portal_src/languages.json").read_text())["languages"]}
        grows = []
        for g in prod["groups"]:
            v = g.get("verify") or {}
            ok = (v.get("missing") == 0 and v.get("duplicates") == 0 and v.get("unexpected") == 0 and not g["verify_bad"])
            grows.append([f"<b>{e(g['group'])}</b>", e("、".join(Lz.get(c, c) for c in g["langs"].split(","))),
                          f"{g['pages']:,}", e(g["errors"]), f"{g['wall'] / 60:.1f}", f"{g['pages_per_sec']:.1f}",
                          f"{g['core_sec_per_page']:.2f}", f"{g['gb']:.0f}", e(g.get("shards")),
                          ("✅ " if ok else "⚠️ ") + f"缺 {e(v.get('missing'))} / 重 {e(v.get('duplicates'))} / 抽读坏 {g['verify_bad']}"])
        prod_tbl = table(["组", "语言（各 9 类 × 1111 页）", "页数", "失败", "墙钟（分钟）", "页 / 秒", "核·秒 / 页",
                          "产物 GB", "分片数", "验收（键差集 / 重复 / 抽样读回）"], grows, num_cols=(2, 3, 4, 5, 6, 7, 8))
        st = {}
        for g in prod["groups"]:
            for k, v in ((g.get("timing") or {}).get("stages") or {}).items():
                st.setdefault(k, []).append(v["median"])
        stage_zh = {"open": "开页面", "goto": "载入 HTML", "fonts": "等字体", "layout": "排版 JS", "extract": "取坐标",
                    "screenshot": "截图", "degrade_export": "图像退化 + 导出标注", "jpeg": "JPEG 编码", "write": "写出",
                    "build": "生成 HTML"}
        stage_html = "".join(f"<li>{e(stage_zh.get(k, k))}：<b>{sum(v) / len(v):.3f} 秒</b></li>" for k, v in st.items())
        em = {}
        for g in prod["groups"]:
            for k, v in ((g.get("verify") or {}).get("empty_markdown") or {}).items():
                em[k] = em.get(k, 0) + v
        em_txt = "、".join(f"{k} {v:,} 页" for k, v in sorted(em.items(), key=lambda kv: -kv[1])) or "无"
        prod_html = f"""<p>4 台 64 核 CPU worker 并行，每台一组 5 种语言 × 9 类 × 1111 页，共 <b>{prod['pages']:,}</b> 页、失败 <b>{prod['errors']}</b> 页；
总计 <b>{prod['cpu_core_hours']}</b> 核·时（平均 <b>{prod['core_sec_per_page']}</b> 核·秒 / 页），最慢一组 {prod['wall_max'] / 60:.0f} 分钟跑完，产物 {prod['gb']:.0f} GB（JFS <code>processed/synthdog_doc/prod200k/</code>）。</p>
{prod_tbl}
<div class="grid g2" style="margin-top:14px"><div class="card"><h3>每页各阶段耗时（中位数，四组平均）</h3><ul>{stage_html}</ul>
<p class="note">“开页面”不含每个进程第一次启动浏览器（约 40 秒，每 400 页回收一次时重来）。</p></div>
<div class="card"><h3>验收怎么做的</h3><ul><li>键差集：按“类型 × 语言 × 序号”列出应有的 49,995 个页名，与分片里实际的页名逐个比对，缺失、多余、重复都为 0 才算过。</li>
<li>抽样读回：每组随机 100 页完整读出，JPEG 能解码且尺寸与记录一致、OmniDocBench 标注能解析、Markdown 非空（整页广告除外）。</li>
<li>Markdown 为空的页：{e(em_txt)}。全部是整页广告——按 OmniDocBench 规则广告标为 abandon、不转写，属预期行为。</li></ul></div></div>"""
    else:
        prod_html = "<p class='note'>Top-20 × 1 万页压测进行中。</p>"
    cost = P.get("cost", {})
    cost_html = "".join(f"<li>{e(k)}：<b>{e(v)}</b></li>" for k, v in cost.items())
    body = f"""
<section><h1>批量生产：速度、成本与改写模型选型</h1>
<p class="sub">渲染本身不花 API 钱，只花 CPU；钱主要花在大模型写内容包（论文、试卷、PPT、研报、教材、杂志专题与新闻编辑）。所以先把“每页要几个 CPU 核·秒”和“每页摊多少 token”分开测清楚，再按任务给内容包选性价比最高的模型。</p></section>
<section><h2>渲染速度（同一批页面，不同配置）</h2>{btbl}
<p class="note">“实耗 CPU”是所有子进程（Python + Chromium）真实消耗的核·秒，不是申请核数 × 时间。第一阶段的“7.3 核·秒 / 页”是按申请核数折算的。</p>
<div class="grid g2" style="margin-top:14px"><div class="card"><h3>做了哪些优化</h3><ul>
<li>浏览器常驻：每个进程只启动一次 Chromium，跨批复用、每 400 页回收（原来每 6 页就重启一次）。</li>
<li>输出改为大分片：每批页面写成一个 zstd 压缩的 Parquet 分片（图像 JPEG 字节 + 标注 + Markdown + 元数据），不再每页 4 个小文件。</li>
<li>JPEG 截图、OpenCV 单线程：避免几十个进程互相抢线程。</li>
<li>分阶段计时：排版 JS 只要约 30 毫秒；真正耗时的是截图编码、图像退化与解码 —— 下一步优化方向。</li></ul></div>
<div class="card"><h3>结论</h3><ul><li>64 进程（= 核数）最好：再多进程只会互相抢占。</li><li>单台 64 核每小时约 8~10 万页；渲染不是瓶颈，瓶颈在 LLM 内容包（见下）。</li></ul></div></div></section>
<section><h2>Top-20 × 每语种 1 万页压测</h2>{prod_html}</section>
<section><h2>内容包改写模型选型（bake-off）</h2>
<p>同样的提示词和真实种子文本，7 个难语种（阿拉伯、印地、孟加拉、日、泰、繁中、德）× 3 类任务（论文、试卷、新闻编辑）× 每格 10 包；评委不评自家模型（Opus 评 GPT / DeepSeek / Gemini，Gemini 评 Sonnet），A/B 位置随机。</p>
{botbl}
<p class="note">{e(bo.get("conclusion", ""))}</p></section>
<section><h2>成本模型</h2><div class="card"><ul>{cost_html}</ul></div></section>
"""
    page(portal, "production.html", "批量生产", body)


def build_p2(portal):
    body = """
<section><h1>第二阶段总览</h1>
<p class="sub">在第一阶段（9 类 × 10 语、9000 页）基础上，第二阶段做六件事。每件事一个页面；方案由三位评审模型（GPT-6-Astra、Gemini-4-Argon、Claude Opus 5.5）讨论定稿，主会话实测执行。</p>
<div class="grid g3">
<div class="card"><h3><a href="languages.html">1. 语言扩展</a></h3><p>10 → 22 种：加入简繁中文、英文、日韩越泰、土耳其、波斯、意大利、波兰、荷兰；中日泰无空格断行、日文竖排、波斯 RTL 等排版能力。</p></div>
<div class="card"><h3><a href="datapool.html">2. 数据池</a></h3><p>正文主池换成 FinePDFs 真实 PDF 文本，每语种数十万页，支撑开源库 Top-15 每种 ≥10 万页。</p></div>
<div class="card"><h3><a href="evalset.html">3. 真实评测集</a></h3><p>每语种 × 每类版面 5 份真实 PDF、10 页，三模型标注，可开源发布（单独 MR）。</p></div>
<div class="card"><h3><a href="benchmark.html">4. 模型评测</a></h3><p>7 个模型在合成集与真实集上的综合分、分元素、分语言结果。</p></div>
<div class="card"><h3><a href="production.html">5. 批量生产</a></h3><p>速度、成本实测与优化；Top-20 × 每语种 1 万页压测；LLM 改写模型选型。</p></div>
<div class="card"><h3>6. 汇总 review</h3><p>本门户即汇总；review 通过后合并 phase2 与 feat/real-evalset 两个 MR。</p></div>
</div></section>
"""
    page(portal, "p2.html", "第二阶段总览", body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portal", default=str(D / "portal"))
    ap.add_argument("--only", default="p2,languages,datapool,benchmark,production")
    a = ap.parse_args()
    portal = Path(a.portal)
    todo = a.only.split(",")
    if "p2" in todo:
        build_p2(portal)
    if "languages" in todo:
        build_languages(portal)
    if "datapool" in todo:
        build_datapool(portal)
    if "benchmark" in todo:
        build_benchmark(portal)
    if "production" in todo:
        build_production(portal)
    print("built", todo)


if __name__ == "__main__":
    main()

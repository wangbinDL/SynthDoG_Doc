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
table.t th{{background:var(--soft);font-weight:600;position:sticky;top:56px}}
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
    samples = []
    for code in ["zh-Hans", "zh-Hant", "ja", "ko", "vi", "th", "en", "tr", "fa", "it", "pl", "nl"]:
        for t in ["newspaper", "paper_double", "book", "exam"]:
            src = D / "renders" / ("p2_grid_zh" if code.startswith("zh") else "p2_grid1")
            samples.append((f"{t}__{code}__v6__0000", f"{code} · {TYPE_ZH[t]}"))
    th = thumbs(portal, D / "renders/p2_grid_all", samples, "lang")
    vert = thumbs(portal, Path("/tmp/sdd_vert"), [("book__ja__v6__0000", "日文书籍竖排")], "lang")
    th_html = "".join(f'<figure><img src="{p}" loading="lazy" alt=""><figcaption>{e(c)}</figcaption></figure>'
                      for p, c in vert + th)
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


def build_benchmark(portal):
    rep = json.loads((D / "bench/runs/bench900/report.json").read_text())
    M = rep["models"]
    names = [n for n in M if n != "gt-oracle"] + (["gt-oracle"] if "gt-oracle" in M else [])
    best = max((M[n]["overall"] for n in names if n != "gt-oracle"))
    rows = []
    for n in names:
        m = M[n]
        ned = (((m.get("text_metric") or {}).get("all") or {}).get("all") or {}).get("ned_strict")
        fa = (m.get("run") or {}).get("first_attempt") or {}
        fails = sum(v for k, v in fa.items() if k != "ok")
        ov = f'<span class="{"best" if m["overall"] == best else ""}">{m["overall"]:.2f}</span>'
        rows.append([f"<b>{e(m['display'])}</b>", ov, fmt(m["text_edit"], 3), fmt(m["formula_cdm"], 1, True),
                     fmt(m["table_teds"], 1, True), fmt(m["table_teds_s"], 1, True), fmt(m["reading_order_edit"], 3),
                     fmt(ned, 3), e(fails if n not in ("gt-oracle",) else "—")])
    main_tbl = table(["模型", "综合分 ↑", "文本编辑距离 ↓", "公式 CDM ↑", "表格 TEDS ↑", "TEDS-S ↑", "阅读顺序 ↓",
                      "页级字符错误率 ↓（保留标音符号）", "首次请求失败页"], rows, num_cols=(1, 2, 3, 4, 5, 6, 7, 8))

    def bucket_table(prefix, labels):
        keys = sorted({k.split(": ", 1)[1] for n in names for k in M[n]["buckets"] if k.startswith(prefix + ": ")})
        rows = []
        for n in names:
            vals = [(M[n]["buckets"].get(f"{prefix}: {k}") or {}).get("overall") for k in keys]
            good = [v for v in vals if v is not None]
            hi = max(good) if good else None
            cells = []
            for v in vals:
                cls = "weak" if v is not None and v < 80 else ""
                cells.append(f'<span class="{cls}">{v:.1f}</span>' if v is not None else "—")
            rows.append([f"<b>{e(M[n]['display'])}</b>"] + cells)
        return table(["模型"] + [e(labels.get(k, k)) for k in keys], rows, num_cols=tuple(range(1, len(keys) + 1)))
    L = {r["code"]: r["zh"] for r in json.loads((D / "portal_src/languages.json").read_text())["languages"]}
    lang_tbl = bucket_table("sdd_lang", L)
    type_tbl = bucket_table("sdd_doc_type", TYPE_ZH)
    br_tbl = bucket_table("sdd_branch", {"digital": "数字原生", "scan": "扫描复印", "photo": "手机翻拍"})
    body = f"""
<section><h1>模型评测</h1>
<p class="sub">同一套 OmniDocBench 官方口径，比较 7 个文档解析模型在 SynthDoG-Doc 合成页（900 页，9 类 × 10 语 × 10 页）上的表现；真实评测集的结果见 <a href="evalset.html">真实评测集</a> 页，构建完成后在此汇总两者的排名一致性。</p>
<div class="kpis"><div class="kpi"><b>900</b>合成评测页（按成像分支分层抽样）</div><div class="kpi"><b>7</b>个模型</div>
<div class="kpi"><b>99.94</b>标注自检分（拿标注当答案打分，验证流程）</div><div class="kpi"><b>{best:.2f}</b>最佳综合分（Claude Opus 5.5）</div></div></section>
<section><h2>总表</h2>{main_tbl}
<p class="note">综合分 = ((1 − 文本编辑距离) × 100 + 公式 CDM × 100 + 表格 TEDS × 100) / 3（OmniDocBench v1.5 口径，评分镜像 omnidocbench-eval:v16-flat1）。“页级字符错误率”是补充指标：官方文本归一化会删掉组合附标（天城文元音符号、阿拉伯文标音符号等），这里保留它们、按整页阅读顺序计算；结果与官方口径接近，说明这批模型的错误主要不在附标上。失败页（拒答、截断、超时）照常按空输出计分，不剔除。</p></section>
<section><h2>分语言消融</h2>{lang_tbl}
<p class="note">红色 = 综合分低于 80。MinerU2.5-Pro 与 PaddleOCR-VL-1.6 在阿拉伯文、乌尔都文（Nastaliq）上明显掉分；Qwen3.8-27B 在这两种语言上保持 89~93。</p></section>
<section><h2>分文档类型</h2>{type_tbl}</section>
<section><h2>分成像方式</h2>{br_tbl}</section>
<section><h2>评测设置</h2>
<div class="grid g2"><div class="card"><h3>模型与推理</h3><ul>
<li>MinerU2.5-Pro（1.2B）：官方两阶段（版面 → 逐块识别），vLLM 服务，1×H100。</li>
<li>PaddleOCR-VL-1.6（0.9B）：PP-DocLayoutV3 版面 + 逐区域识别的两阶段复现（阅读顺序用 XY-cut，不是官方排序模型，偏保守）。</li>
<li>Qwen3.5-4B：不开 thinking、repetition penalty 1.1、4MP；Qwen3.8-27B：开 thinking、不加 penalty、4MP。</li>
<li>GPT-6-Astra / GPT-6.1-Sol / Claude Opus 5.5：统一的多语种整页 Markdown 提示词（要求原文照录、不翻译、保留本地数字，RTL 先右栏），effort = medium。</li></ul></div>
<div class="card"><h3>口径要点</h3><ul>
<li>页眉、页脚、页码按 OmniDocBench 规则不计分；图注照常转写。</li>
<li>修正了合成标注中关系字段名（relation → relation_type）与官方不一致的问题，否则评分器报错。</li>
<li>Opus 有 1 页首次被内容过滤拦截、1 页截断，原样重试一次后成功；表中“首次请求失败页”如实列出。</li></ul></div></div></section>
"""
    page(portal, "benchmark.html", "模型评测", body)


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
    ap.add_argument("--only", default="p2,languages,datapool,benchmark")
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
    print("built", todo)


if __name__ == "__main__":
    main()

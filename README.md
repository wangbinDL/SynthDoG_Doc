<div align="center">

# SynthDoG-Doc：多语种整页文档图像合成

为文档解析 / OCR 模型批量生产 **多语种、多版式、带精确标注** 的整页文档图像

**门户（IAP，内部访问）**：<https://mmdata-wb.iap.platform.shaipower.com/docintel/synthdog-doc/index.html>

</div>

---

## 一、项目介绍

原版 SynthDoG（来自 [Donut](docs/donut_README.md)）只是把一段文字贴到背景图上，用于 OCR 预训练。
SynthDoG-Doc 在它的基础上重写为 **整页文档合成器**：生成的页面像真实的报纸、试卷、论文、PPT，
同时给出与 [OmniDocBench](https://arxiv.org/abs/2412.07626) 同构的标注——每个块 / 每一行的位置、类别、阅读顺序、
文本、公式 LaTeX、表格 HTML——可以直接用于文档解析模型的训练与评测。

当前版本覆盖：

| 维度 | 范围 |
|---|---|
| 文档类型（9 类） | PPT 幻灯片、试卷、单栏论文、双栏论文、报纸、杂志、书籍、教材、研报 |
| 语言（10 种，去掉中英文后按使用人数取 Top-10） | 印地语、西班牙语、阿拉伯语、法语、孟加拉语、葡萄牙语、印尼语、乌尔都语、俄语、德语（选择依据见 [synthdog_doc/docs/languages.md](synthdog_doc/docs/languages.md)） |
| 每页产物 | 整页图像 `.jpg`、OmniDocBench 标注 `.json`、阅读顺序 Markdown `.md`、生成参数 `.meta.json` |
| 页面物理属性 | 纸张、长宽比、DPI 按 OmniDocBench 1651 页统计采样；数字原生 / 扫描复印 / 手机翻拍三种成像 |

## 二、目标

1. **补齐小语种文档数据**：中英文以外的语言真实标注数据稀缺，用合成数据补足版式与文字的多样性。
2. **标注与图像严格一致**：标注直接从渲染结果里量出来，不靠估计，避免“图里有字、标注里没有”。
3. **看起来像真的**：版式、字体、本地排版习惯（数字体系、标点、从右往左、断字）、内容连贯性都向真实文档靠拢，
   以两位视觉大模型评委的盲评 + 自动质检为准绳迭代。
4. **长期**：构建可开源的大规模多语种文档库，以及配套的真实文档评测集（见 [docs/TASKS.md](docs/TASKS.md)）。

## 三、思路

```
① 数据源                  ② 版式生成                    ③ 真值与成像                 ④ 模型评审迭代
各国维基 + 本国新闻网站    9 类模板 × 多种出版风格         从渲染结果量取块 / 行框        Opus 5.5 + GPT-6.1-Sol 盲评
大模型内容包（论文 / 试卷  无头 Chromium 渲染              类别、阅读顺序、LaTeX、表格     真假鉴别 · 问题清单 · 多样性
  / PPT / 研报 / 教材…）   自写分栏引擎（拆段、浮动体、     数字原生 / 扫描 / 翻拍退化      新旧版 A/B · 逐类签字
内部图片 crop + 430 款字体   栏平衡、孤行控制、公式适配）    （框随图像同步变换）           自动质检 lint → 改模板
OmniDocBench 尺寸统计      10 语种排印规则（RTL、断字…）    输出 ODB 同构 JSON + Markdown
```

几个关键取舍：

- **用浏览器排版，而不是用 PIL 贴字**：阿拉伯 / 乌尔都连写、天城体 / 孟加拉字形组合、从右往左、断字、两端对齐、
  公式（KaTeX），浏览器都现成支持；代价是每页约 7 个 CPU 核·秒，靠多核横向扩展（64 核约 9 页 / 秒）。
- **自写分栏引擎**：每个词都是可测量的元素，块框、行框、阅读顺序直接从渲染结果量出来，标注和图像天然一致。
- **内容真实性与可控性**：正文尽量用本国网站的真实文字（语言地道），标题、图注、表格数据由大模型“做编辑”，
  再做一致性补全（年份、单位、图表数据与正文一致）；配图只用“真正对题”的照片，宁缺毋滥。
- **评审闭环**：盲评真假（混入真实页防止评委“全判假”）、新旧版 A/B、16 页拼图看多样性、自动质检查客观缺陷，
  最后逐类签字。

## 四、当前成果（第一阶段）

| 指标 | v0（初始） | v6（最终） |
|---|---|---|
| 自动质检：无中高危缺陷的页面占比 | 79% | 98% |
| Opus 5.5 真实感 / 内容连贯（满分 5）\* | 2.08 / 1.80 | 2.59 / 2.61 |
| GPT-6.1-Sol 真实感\* | 3.02 | 3.59 |
| 两位评委共同签字通过的类别 | — | 试卷、单栏论文、报纸、杂志、研报 |

\* 评委分数取最后一次全类别盲评（第 6 轮，评的是 v5 模板）；v6 只改了教材、杂志和论文参考文献，第 7 轮只复评了教材和杂志。

最终数据：9 类 × 10 语 × 100 页 = 9000 页（0 失败，7.3 GB，存于 JFS `processed/synthdog_doc/sdd-v6/pages`），由 tag `v1.0` 的代码生成。迭代过程、版本对比、评审细节都在门户上。

## 五、目录结构

```
synthdog_doc/            SynthDoG-Doc 主体（Python 包 + 脚本 + 文档，详见 synthdog_doc/README.md）
  synthdog_doc/
    doctypes/            9 类文档模板
    assets/engine.js     页内分栏排版与真值提取引擎
    render.py generate.py degrade.py export.py lint.py judge.py …
  scripts/               评审、门户、素材打标、抽样等脚本
  docs/                  语言选择等文档
docs/TASKS.md            任务记录（阶段目标、拆解、决策、进度）
docs/donut_README.md     原 Donut / SynthDoG 说明
synthdog/                原版 SynthDoG
donut/ train.py …        原版 Donut 模型代码（未改动）
```

## 六、快速开始

```bash
pip install playwright pyphen opencv-python pillow numpy && playwright install chromium
cd synthdog_doc
# 字体、语料、内容包、图片池默认放在 /data/synthdog-doc（见各脚本参数）
python3 -m synthdog_doc.generate --types newspaper,exam --langs ar,hi --n 4 --version 6 --out /tmp/sdd --overlay
python3 -m synthdog_doc.lint --renders /tmp/sdd
```

## 七、致谢与许可

本项目基于 NAVER Clova 的 [Donut / SynthDoG](https://github.com/clovaai/donut)（MIT License），
原许可证见 [LICENSE](LICENSE)，第三方声明见 [NOTICE](NOTICE)。

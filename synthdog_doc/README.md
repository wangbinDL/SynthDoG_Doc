# synthdog_doc：SynthDoG-Doc 主体代码

整页多语种文档图像合成，输出与 OmniDocBench 同构的标注。项目介绍、目标与门户地址见[仓库首页 README](../README.md)，
原版 SynthDoG / Donut 说明见 [docs/donut_README.md](../docs/donut_README.md)。

| | |
|---|---|
| 文档类型 | `ppt` PPT、`exam` 试卷、`paper_single` 单栏论文、`paper_double` 双栏论文、`newspaper` 报纸、`magazine` 杂志、`book` 书籍、`textbook` 教材、`report` 研报 |
| 语言 | 印地语、西班牙语、阿拉伯语、法语、孟加拉语、葡萄牙语、印尼语、乌尔都语、俄语、德语（[选择依据](docs/languages.md)） |
| 每页产物 | `*.jpg` 整页图像；`*.json` OmniDocBench 标注（块 / 行框、类别、阅读顺序、LaTeX、表格 HTML）；`*.md` 页面 Markdown；`*.meta.json` 生成参数 |

## 流水线

1. **内容**：本国网站正文（FineWeb-2 中按国家域名 / 新闻站过滤）与维基百科正文，经大模型“编辑”成新闻稿；
   论文、试卷、PPT、研报、教材、杂志专题、广告等结构化内容包由大模型撰写，再做一致性补全
   （`corpus_fetch.py`、`content_gen.py`、`news_pack.py`、`pack_enrich.py`、`photo_assign.py`）。
2. **版式**：每类文档一套 HTML/CSS 模板（`doctypes/`），无头 Chromium（Playwright）渲染。
   `assets/engine.js` 把按词切分的正文排进各栏（拆段、标题与正文不分离、浮动体延后、栏平衡、孤行控制、
   标题 / 公式 / 表格自适应），并直接从渲染结果量取真值，所以框和像素永远一致。
3. **页面几何**：纸张、长宽比、DPI 按类别从 OmniDocBench 统计中采样（`geometry.py`）。
4. **成像**：数字原生、扫描复印（颗粒、倾斜、模糊、噪声、透印）或手机翻拍（透视、背景），标注随图像同步变换（`degrade.py`）。
5. **质检与评审**：`lint.py` 查客观缺陷（裸 LaTeX、数字体系错误、英文泄漏、空白区域、照片放大过度等）；
   `judge.py` 与 `scripts/judge_round.py`、`scripts/judge_signoff.py` 组织双模型盲评与逐类签字。

## 用法

```bash
pip install playwright pyphen opencv-python pillow numpy && playwright install chromium
# 字体、语料、内容包、图片池默认放在 /data/synthdog-doc（见各脚本参数）
python3 -m synthdog_doc.generate --types newspaper,exam --langs ar,hi --n 4 --version 6 --out /tmp/sdd --overlay
python3 -m synthdog_doc.lint --renders /tmp/sdd
```

`--version` 选择模板代际（0–6），最终数据集用 v6：9 类 × 10 语 × 100 页 = 9000 页。

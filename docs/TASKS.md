# SynthDoG-Doc 任务记录

> 本文件记录项目的阶段目标、拆解、决策与进度，随推进实时更新。
> 门户（IAP）：https://mmdata-wb.iap.platform.shaipower.com/docintel/synthdog-doc/index.html

## 第一阶段（已完成，2026-11-27 ~ 11-28）

- 9 类文档（PPT、试卷、单栏论文、双栏论文、报纸、杂志、书籍、教材、研报）× 10 种语言（印地、西班牙、阿拉伯、法、孟加拉、葡萄牙、印尼、乌尔都、俄、德）。
- 模板 v0 → v6，经 Opus 5.5 与 GPT-6.1-Sol 共 7 轮盲评、4 次逐类签字迭代；最终版生成 9000 页（每格 100 页）。
- 关键数字：自动质检无中高危缺陷 79% → 98%；Opus 真实感 2.08 → 2.59、内容连贯 1.80 → 2.61。

## 第二阶段（进行中，2026-11-28 起）

总原则：每个子任务独立分支、独立 MR；方案类决策由 CCG（GPT-6 Astra / Gemini 4 Argon / Claude Opus 5.5，均为最强 effort）讨论，主会话汇总、实测验证后执行；门户每个子任务一个页面。

| # | 子任务 | 产出 | MR / 分支 | 状态 |
|---|---|---|---|---|
| 0 | 仓库整理：清空历史，单一最新 commit；中文 README（项目介绍、目标与思路、门户地址）；清理无用中间产物 | master 单 commit `04e9577` + tag `v1.0` | 直推 master | 已完成（11-28 11:10） |
| 1 | 语言扩展（方案已由 CCG 定，见 docs/ccg_phase2_synthesis.md）：参考 Ethnologue 人口排名与 PaddleOCR PP-OCRv5 多语言支持，CCG 讨论优先级；加入简体中文、繁体中文、英文，以及日、韩、越、泰、欧美发达国家、阿拉伯语区人口大国等语言；门户给出选择逻辑与中英文对照 | 语言注册表 + 字体 / 语料 / 内容包 / 排版规则；门户「语言」页 | `phase2` | 22 语已可渲染（含日文 / 繁中竖排）；新语言首轮盲评中 |
| 2 | 数据源扩展：为开源大规模文档库准备更大量、高质量、真实的数据池（目标：Top-15 语言每种 ≥100k 页） | 数据源调研与许可评估、数据池构建脚本与清单（JFS） | `phase2` | 57 个分片已入 JFS；数据池 v1 构建中（已完成 13 语种） |
| 3 | 真实评测集：每个语种 × 每类版面下载 5 份 PDF，随机采样 10 页；CCG 三模型构建高质量标注；可开源 release | 评测集 + 标注流水线 + 门户独立页面 | `feat/real-evalset`（单独 MR，独立 worktree） | 候选 9 万份 → 分类 → 平台取回 1364 份真实 PDF → 视觉核验中 |
| 4 | 模型评测：从 9000 页中抽 9×10×10=900 页，评测 MinerU2.5-Pro、PaddleOCR-VL-1.6、GPT-6-Astra、GPT-6.1-Sol、Opus 5.5、Qwen3.5-4B、Qwen3.8-27B；给 overall 与 element-wise（文本 / 公式 / 表格 / 阅读顺序）分数及分语言消融；同样评测真实评测集 | 评测结果 + 门户独立页面 | `phase2` | 合成集 900 页 7 模型已完成（Opus 96.89 / Astra 95.96 / Sol 94.67 / Qwen3.8-27B 92.75 / MinerU 88.05 / Qwen3.5-4B 87.04 / PaddleOCR-VL 86.13）；真实集待标注完成 |
| 5 | 批量生产：测算当前每页速度与成本（渲染 CPU、LLM 内容改写），优化代码支持 64 / 256 并发；在内容确定的前提下测 Top-20 语种 × 每语种 1 万页（各文档类型平均分配，每类约 1 万 / 9 页）= 20 万页的平均速度与成本；LLM 改写模型做性价比选型（候选 GPT-6.1-Sol 等） | 生产流水线 + 压测报告 | `feat/scale-production` | 待开始 |
| 6 | 汇总：更新门户供整体 review；review 通过后合并各 MR | 门户 v2 | — | 待开始 |

## 决策记录

| 日期 | 决策 | 依据 |
|---|---|---|
| 2026-11-28 | GitHub 仓库清空历史，仅保留一个最新 commit；旧历史在本地打 `archive/` 标签备份，不推送 | 用户要求 |
| 2026-11-28 | 删除 JFS 上 sdd-v4、sdd-v5 中间全量（各 7.3G）及冻结代码副本；保留 v0~v6 评测样张、评审记录、素材池与语料（后续优化与门户要用） | 用户要求“无用中间结果可删，影响后续优化的保留” |
| 2026-11-28 | 旧历史完整备份为 `/data/synthdog-doc/backup/synthdog_doc_history_20261128.bundle`（78 MB，含 master / synthdog-doc / sdd-v0~v6.1），本地另留 tag `archive/pre-squash`；GitHub 上已删除 synthdog-doc 分支与 sdd-* 标签 | 可随时 `git clone <bundle>` 恢复 |
| 2026-11-28 | 第二阶段数据源候选：FinePDFs（HF，ODC-By，4.76 亿份 CommonCrawl 真实 PDF，1732 个语种；每条带 WARC 路径与偏移，可取回原始 PDF）+ FineWeb-2 | HF datasets-server 实测行数，见 CCG 简报 |
| 2026-11-28 | CCG 第 2 轮定方案：T1 新增 12 语；Top-15 = en、zh-Hans、hi、es、ar、fr、bn、pt、id、ur、ru、de、ja、vi、ko；Top-20 再加 zh-Hant、tr、fa、th、it；朝鲜作为韩文变体不进开源版；日文 / 繁中书籍竖排本阶段做 | 三模型多数意见，详见 docs/ccg_phase2_synthesis.md |
| 2026-11-28 | Opus 5.5 在 max effort 下连续 3 次（32k/64k/128k 输出额度）只思考不出正文，第 4 次改用 xhigh 成功；如实记录 | CCG 原始报告 |
| 2026-11-28 | 修正 GT 导出：关系字段名 `relation` → `relation_type`（与官方 OmniDocBench 一致，否则评分器报错）；新增跨栏段落的 `truncated` 关系 | 900 页评测时发现 |
| 2026-11-28 | 真实评测集不做人工核验：标注由 CCG 三个最强模型（GPT-6-Astra / Gemini-4-Argon / Claude Opus 5.5）完成，配合 PDF 文字层、检测框和自动一致性检查；仍输出分歧页清单供参考 | 用户决定（覆盖 CCG 的人工核验建议） |
| 2026-11-28 | Top-20 压测口径：每个语种共 1 万页，各文档类型平均分配，合计 20 万页 | 用户确认 |
| 2026-11-28 | 残留 rjob 先经 CCG 三模型核对清单再删除 | 用户要求 |

---
name: "skillpingjia"
license: "Apache-2.0"
description: "Agent Skill 质量评分：硬门槛（H1/H2/H3/H4 三权分立一票否决）+ 七维 100 分制（触发设计 20 / 流程纪律 15 / 结构合理性 20 / 输出契约 15 / 护栏 10 / 配置边界 5 / 评估闭环 15），证据制报告。Make sure to use this skill whenever the user asks to evaluate/score/review a skill's quality, even if they don't explicitly say '评分'. 说打分/评估/合格吗/对比时用。安全审查归skill-vetter。"
---

# skillpingjia 📊

基于知识库 `references/playbook_snapshot.md`（playbook 包内快照，v3.4.1 起自带）的评分机制，
对任意 Agent Skill 做质量评估。评分目的是**指导改进优先级**，不是淘汰。

> **v3.4.1 变更摘要（2026-11-11 实际使用优化）**：
> - **噪音过滤**：files 清单/脚本计数/证据采集统一排除 `*.bak*`、`__pycache__`、`.git`、`.pyc/.tmp`——此前陈旧备份会被计入（pingjia 扫自己混进 8 个 .bak），污染 files 断言与证据采集
> - **`--summary` 模式**：`python3 scripts/score.py <目标> --summary` 裁掉 `skill_md_content` 全文字段、截断长 snippets，judge 日常评审够用（回归断言仍用全量模式）
> - **references 自包含**：playbook 细则快照拷进 `references/playbook_snapshot.md`，评分不再依赖 workspace 外部文件——本 skill 拷到任何 agent 都能全量工作

> **v3.4 变更摘要（2026-11-11 外部对标 — NVIDIA auto-ontology skill 套件解剖收敛）**：
> - **新增 `package_engineering` 线索采集器**：六项包工程线索——`contract_asset`（机读 workflow 契约 yaml/json，含 workflows/artifacts/statuses/gates 键）、`eval_report`（出厂评测报告 BENCHMARK.md/EVALUATION.md）、`disclosure_card`（披露卡 skill-card.md：风险/依赖/凭证声明）、`signature`（包签名 *.sig 类）、`kit_routing`（套件路由入口 AGENTS.md 含"用户动作→归属 skill"交接表）、`live_source_principle`（SKILL.md 声明"活真源"：运行时握手 > 抄录工具表）
> - **定位：线索非断言**（v3.1 传统不破）。命中作正向证据补充（contract_asset→流程纪律满分候选；eval_report→回归基线满分候选；kit_routing→技能互斥满分候选）；disclosure_card/signature 缺失**不扣分**，仅发布/共享类 skill（C5 触发）在报告中列为改进建议——防"用大厂包标准误伤个人小 skill"
> - 验收 case：`evals/cases/kit_engineering`（模拟五件套包，六项线索全命中）+ 真实样本回归（NVIDIA nvidia-ontology-query 实测 5/6，kit_routing 不命中为正确边界——路由入口在套件根不在成员包内，零误报）
> - 外部依据：NVIDIA 把 skill 从"提示词便签"抬升为"带契约、带测试报告、带签名的软件交付物"；我方 Matrix v0.2 的 SK-CONT/SK-EVAL 条款在其实战复现（行业趋同证据，记入 skill-design 判据 7）

> **v3.3 变更摘要（2026-09-07 实战反思 — jishufangan v3.15 三轮深度评审收敛）**：
> - **P0-1 IR 全链路双向闭合**：v3.2 element_closure 只查单向，v3.3 新增反向：producer 产出 ⊄ consumer 白名单（heading_preserved 案：parser 产生、renderer 认识、save_structure 的 allowed_types 拒绝——三模块三套定义漂移）。score.py 新增 `_collect_ir_closure()`：泛化正则采集 producer/consumer 类型名（不限 docx 词表），交叉比对产出"真实缺口"清单
> - **P0-2 静默失败扫描**：`except Exception: pass` 计数 + 有无配套 warning；规避静默吞错→heuristic 接管→产出"看起来正常"的危险伪装
> - **P1-1 兜底分支触发审计**：v3.3 新增，验证 target skill 的兜底条件不认上游实际产出的类型（h1_present 案的同款）
> - **P1-2 真实样本回归要求**：评估闭环 3 分拆出 1 分——必须有真实事故 case（jishufangan 回归）
> - **P2 声明-实现对照**：SKILL.md 承诺的管线 ⊆ 实际调用链
> - 设计底线3 条（继承 pingjia 传统）：泛化实现（行为特征识别，不绑 docx 词表）；线索非断言（v3.1 立的规矩不破）；自我矛盾自查
> - **验收咬合检查**：v3.3 必须回评 jishufangan v3.15 修复前快照——3 个新判据必须分别抓出 allowed_types 缺口、h1_present 盲点、裸 pass。**抓不出 = 判据实现有误，回工**。
> - 变更史下沉到 CHANGELOG.md，SKILL.md 仅留最新版摘要

> **v3.2 变更摘要（2026-08-22 实战反思）**：
> - **评分流程新增 1.5 步「执行验证 dry-run」**：不只静态读文件——真实跑目标 skill 的 `evals/runner.py`（记 PASS/FAIL），扫描 scripts 占位正文（如「内容待撰写」），核对 SKILL.md 示例代码引用的入口函数在 scripts 中是否存在（死引用检测）
> - **输出契约新增「元素闭合性」检查**：SKILL.md 承诺的 structure 元素类型（heading/body/table/image...）必须 ⊆ 渲染入口实际处理的分支；缺口（如 image 静默跳过）= 降档证据。**泛化实现**：渲染入口用行为特征识别（按元素类型分支 / 元素 API 调用），不依赖函数名
> - **触发设计新增「路由覆盖一致性」**：SKILL.md 内部有路由决策树/版本路由时，description 必须覆盖所有分支入口词（如「简版」「方案说明」）——**泛化实现**：分支词从路由章节上下文动态提取（X版/X模式/X路径/X方案 形态 + 双语兑底词），不依赖固定词表，适配任意领域 skill 的路由
> - **评估闭环新增「有效性」检查**：baseline 偏差 >5 自动标记需复盘；runner 是否真实可跑；验证器是否有「设计性偏离豁免」声明（区分预期偏离 vs 真实缺陷）
> - **报告新增「版本声明」**：git commit / branch / dirty / mtime——防评错副本
> - 背景：评 jishufangan 时发现「简版一键调用产出占位符」「generate_from_structure 静默跳过 image」两个真实缺陷，纯静态评分抓不到，必须 dry-run

> **v3.1 变更摘要（2026-08-18 反思修正）**：
> - 输出契约判据改为**问本质不问形式**（三问：数据独立于渲染？改数据不碰渲染出新版？可独立校验？）——中间表示不限 JSON，YAML/dict/数据层均可
> - score.py 新增 `contract_evidence` 线索采集（自动扫描中间表示/渲染入口/校验/防漂移），**线索非断言**，judge 自行判断
> - 评分流程新增第 4 步**满分复核**：1.0 子项必须附一句「为什么不是 0.5」，写不出理由自动降 0.5
> - 背景：评 jishufangan 时输出契约误给满分（表面特征齐全但中间表示未落盘），暴露判据可操作性不足

> **v3 变更摘要（2026-08-18）**：
> - 计分制 110 → **100**（方案 B：触发 20 / 流程 15 / 结构 20 / 输出 15 / 护栏 10 / 配置 5 / 评估 15），分档回归 100 制习惯（≥80 优秀 / 60-79 良好 / <60 不合格）
> - 配置边界 10→5（子项 3/3/2/2 → 2/1/1/1），评估闭环 20→15（子项 5/5/5/5 → 4/4/4/3）
> - llm_score.py 改为**调用方注入**（删全部网络代码）：换模型 / 复制给别人用零改动
> - 评分流程新增「草稿也走全流程」防偷懒草稿（源自 k12 讲义 3.4）
> - 详见 references/weights_rationale.md

> **v2 变更摘要（2026-08-17 回炉）**：
> - 新增硬门槛 H4（三权分立一票否决）
> - 维度权重重分配：触发 25→20，结构 15→20，评估 15→20；新增配置边界 10 分
> - 流程纪律子项：失败分级 4→6
> - 触发设计：核心信号 5→4，pushy 1 分
> - 输出契约：防漂移 3→4
> - H5（评估闭环≥5）暂缓：等 pingjia 自己有 evals/ 目录后再加，避免自我矛盾
> 详情见 CHANGELOG v3.3 条目（回炉建议已全部沉淀，原外部文档链接作废）

## 触发场景（description 被压缩时的兜底入口）

⚠️ 本 skill 的 frontmatter description 可能被工具链规范化压缩，因此把完整触发说明写在这里：

**必须使用本 skill 的场景：**
- 用户说「给这个 skill 打分」「评估这个 skill」「这个 skill 合格吗」「分析 skill 质量」
- 用户说「对比两个 skill」「哪个 skill 更好」「这个 skill 有什么问题」
- 用户说「你看看我的 skill 怎么样」「检查一下我的 skill」——即使没有明说"打分"，只要意图是质量评估就触发

**不要用本 skill 的场景（负触发）：**
- 安全审查 / 恶意代码排查 → 用 skill-vetter
- 创建 / 修改 skill → 用 skill-creator-guide
- 一次性代码审查、纯问答

**互斥声明：** 本 skill 只管质量评分；与 skill-vetter（安全）、skill-creator-guide（创建/审查流程）互补，评分报告中发现的硬伤如需修复，转交 skill-creator-guide。

## 评分机制总览

> 100 分制七维评分，每个子项 0/0.5/1 档位判据见 `references/scoring_rubrics.md`。
> 维度权重 v2 设计论证见 `references/weights_rationale.md`。

### 第一层 · 硬门槛（4 条，H1-H3 任一不过或 H4 严重命中即判不合格）

| # | 门槛 | 判定 |
|---|------|------|
| H1 | 有 YAML frontmatter（name + description） | 无 frontmatter = 不合格 |
| H2 | SKILL.md < 500 行 | ≥500 行 = 不合格 |
| H3 | description ≤ 1024 字符 | 超限 = 不合格 |
| **H4** | **三权分立未严重违反** | **严重违反 = 一票否决** |

**H4 判定细则（2026-08-17 新增）：**

❌ **一票否决**（任一命中即不合格）：
- SKILL.md 与 scripts/ 同时硬编码同一格式定义（字体/颜色/列宽/边框/合并）
- SKILL.md 与 assets/模板指向不一致（死引用、UUID 路径失效、模板文件不存在）
- SKILL.md 把确定性产物塞正文（≥30 行的 HTML/JSON/XML 模板）

✅ **仍走六维评分**（命中但未到否决级）：
- 只有 1 处硬编码，且量小（<10 行）
- SKILL.md 引用了模板路径但模板已迁移到 references/

任何硬门槛不过 → 直接判「不合格」，仍需继续六维评分（用于定位问题）。

> **关于 H5（评估闭环≥5）**：草案里要加，但**暂缓落地**——pingjia 自己当前没有 evals/ 目录，加上 H5 会自我矛盾。等 pingjia 自己的 evals/ 落地后再加。

### 第二层 · 七维加权评分（100 分制）

| 维度 | 满分 | 核心问题 |
|------|------|----------|
| 触发设计 | 20 | description 是唯一入口，写好了吗？ |
| 流程纪律 | 15 | 步骤化 + 产出物 + 失败处理，有吗？ |
| 结构合理性 | 20 | 三权分立（SKILL.md/references/scripts）？ |
| 输出契约 | 15 | 结构化中间表示（JSON 单源）？ |
| 护栏 | 10 | 降级路径 + 痕迹声明 + 用户语言防火墙？ |
| **配置边界** | **5** | **通用规则 vs 单点数据是否分离？** |
| 评估闭环 | 15 | evals + rubrics + with/without 对照？ |

分档：≥80 优秀 🟢｜60-79 良好 🟡｜<60 不合格 🔴

## 七维评分细则（LLM-as-judge，逐项 0/1/0.5）

### 1. 触发设计（20 分）

| 子项 | 分值 | 1.0（满分）标准 | 0.5（残缺）标准 |
|------|------|----------------|----------------|
| 显式触发词 | 5 | 任务词表完整（同义表达覆盖） | 只有 1-2 个词 |
| 隐式意图 | 5 | 含真实话术样例（用户绕弯表达） | 无样例 |
| 核心信号 | 4 | 一句话本质（用户意图而非功能描述） | 偏功能声明 |
| **pushy 句式** | 1 | 含 "Make sure to use..." 强指令 | 无 pushy |
| 负触发 | 3 | 明确不接什么 +「直接答」指示 | 无负触发 |
| 技能互斥 | 2 | 双向边界声明（与竞争 skill） | 单方或无 |
| **路由覆盖一致性** | 线索（不入分） | SKILL.md 有路由决策树/版本路由时，description 覆盖所有分支入口词 | 分支入口词缺失在 description |

⚠️ 判分要点：description 写「能做什么」= 0.5 档；写「用户想达成什么」+ pushy 指令 = 1.0 档。
参考 pushy 示例："Make sure to use this skill whenever the user mentions X... even if they don't explicitly ask for a 'X'"（playbook 第 75 行）。

⚠️ **路由覆盖一致性（泛化）**：`score.py` 自动产出 `route_evidence`。路由章节识别只认正文章节标题（`#`/`**` 行首，排除 `>` 引用块/变更摘要自指）；分支词从路由章节上下文动态提取（ROUTE_BRANCH_PATTERN：X版/X模式/X路径/X方案，前缀 1-4 字符 + 词边界，防句子中间切片；提取不到时用双语兑底词）——不绑定 jishufangan 的政务词表，对任意领域 skill 的路由（如 nvidia copilot 的仓库路由表）零误报。missing 非空 → description 未覆盖内部路由分支入口词，工具链只读 description 路由时会漏，判显式触发词 1.0 → 0.5。

### 2. 流程纪律（15 分）

| 子项 | 分值 | 1.0 标准 |
|------|------|----------|
| 步骤化管线 | 3 | 流程步骤明确（Step 0/1/2... 或 → 链） |
| 每步有产出 | 3 | 每步定义产出物 |
| 禁止路径 | 2 | 明确「不要做什么」（Never call...） |
| 打扰预算 | 1 | 澄清 0-2 问 + 默认值静默应用 |

### 3. 结构合理性（20 分）

- SKILL.md <500 行（5 分）：正文只留流程和指针
- 领域知识拆 references（**8** 分）：大块知识按需加载；H4 命中后此项必 0
- 确定性逻辑进 scripts（7 分）：脚本不判断，模型不碰格式

⚠️ 评分细化：references 拆解的 8 分里，H4 一票否决触发时此项直接归 0；不触发时按"references/ 目录存在 + 内容按需加载"给 0.5~1.0。

### 4. 输出契约（15 分）

⚠️ 核心判据：**模型产出「数据」还是「成品」？**（判据问本质，不问形式——中间表示可以是 JSON/YAML/dict/数据层，不限定文件格式）
- 结构化中间表示（5 分）：数据层独立于渲染逻辑（文件/变量/数据层不限形式）；函数式封装或数据嵌代码 = 0.5；直出成品 = 0
- 可校验（3 分）：输出可 0/1 判分
- 可重渲染（3 分）：改数据秒出新版、不碰渲染逻辑；需改脚本重跑 = 0.5
- 防漂移（4 分）：单一事实源机制（占位符/from_shared/CONSTANTS 任意形式）；两处硬编码 = 0
- **元素闭合性（v3.2 附加判据，泛化实现）**：SKILL.md 承诺的 structure 元素类型（heading/body/list_numbered/list_bullet/table/image）必须 ⊆ 渲染入口实际处理的分支。`score.py` 自动产出 `element_closure.unhandled`；非空（如 image 被静默跳过）= 「结构化中间表示」1.0 → 0.5 证据。**泛化要点**：渲染入口不依赖特定函数名（generate_from_* / convert_to_*），改为行为特征识别——任何函数体含按元素类型分支（typ/el/item == 分支）或调用元素 API（add_heading/add_table/add_image...）即视为渲染入口；非文档生成类 skill（无元素类型承诺）→ skill_md_types 为空，自然跳过，零误报
- 判 1.0 必须三问皆是：① 数据独立于渲染？② 改数据不碰渲染出新版？③ 可独立校验？
### 5. 护栏（10 分）

- 降级路径 + 痕迹声明（4 分）：外部依赖断了怎么办？声明了吗？
- 用户语言防火墙（3 分）：最终用户永远看不到 JSON/脚本/工具名
- 内容合规（3 分）：版权/原创/安全约束

### 5.5 配置边界（5 分）（新维度，2026-08-17 加，v3 缩至 5 分）

**判据：通用规则 vs 单点数据是否混进 Skill？**

| 子项 | 分值 | 1.0 标准 | 0.5 标准 | 0 标准 |
|------|------|----------|----------|--------|
| **个人邮箱/账号** | 2 | 全在 .env / config | 半硬编码（如 QQ 在 .env 但工作邮箱硬编码） | 2 处以上硬编码 |
| **项目/客户名** | 1 | 配置层或参数化 | 1 处硬编码 | 2 处以上硬编码 |
| **路径魔法** | 1 | 全用环境变量/sys.argv | 1 处短 `../../` 链 | 多处 `../../../` 魔法路径 |
| **模型/工具依赖** | 1 | 零硬编码 + 调用方注入（llm_score 模式） | 半参数化 | 硬编码模型/端点/绝对路径 |

**核心原理**：通用规则进 Skill，单点数据进配置（playbook 第 4 节原则）。
### 6. 评估闭环（15 分）（v3 缩至 15 分）

- evals/ 目录/文件（4 分）：有测试用例
- rubrics 判分（4 分）：P/R/O/M 四维或等效（本 skill：references/scoring_rubrics.md 档位表 + evals/rubric.md）
- with/without 对照（4 分）：同 prompt 带/不带 skill 双跑对比记录（evals/with_skill/ + evals/without_skill/）
- **回归基线**（**3** 分）：evals/baseline.json 含上次评估的预期分数，下次打分偏差 >5 必须复盘
- **有效性检查（v3.2）**：`score.py` 自动产出 `evaluation_effectiveness`：① runner 是否真实可跑（有 evals/runner.py 且 exit 0）；② baseline 偏差（expected vs actual，>5 → needs_review=true）；③ 豁免声明（目标是否声明「设计性偏离/预期 CRITICAL」——如 jishufangan 简版 validate 报 2 项预期 CRITICAL，声明了就不该机械扣分）

**关键判据**：带不带 skill 没差别 → 没有存在价值。

## 评分流程

1. **采集**：读 SKILL.md 全文 + 列目录结构 + 检查 evals/scripts/references/assets
2. **执行验证（dry-run）**：真实跑目标 skill 的 `evals/runner.py`（有则跑，记 exit code + 尾部输出）；扫描 scripts/*.py 占位正文（内容待撰写/TODO/lorem）；提取 SKILL.md ```python 代码块中的 one-shot 入口函数（convert_to_*/generate_from_*/build_*），核对 scripts 中是否存在同名 def（死引用检测）。`score.py` 自动产出 `executable_evidence` + `element_closure` 素材，judge 据此判分（dry-run 只识别入口不自动执行外部代码，防误跑）
3. **硬门槛**：4 条判定（H1/H2/H3/H4），记录证据
4. **七维评分**：逐子项 0/1/0.5，**每项必须引用证据**（SKILL.md 行号/章节名/文件存在性/dry-run 结果）；输出契约等软维度参考素材包 `contract_evidence` + `element_closure` 线索，但**线索不作自动判分依据**，judge 自行确认
5. **满分复核**：任何给 1.0 的子项，附一句「为什么不是 0.5」（形式自由，一句话即可）——防表面特征→满分；写不出理由的满分自动降 0.5
6. **一致性对照**：对同一 skill 间隔评分两次（或换一个 judge 视角重评），偏差 >5 分时复核差异维度——保证评分可复现
7. **汇总**：总分 + 分档 + 最强维度 + 最弱维度
8. **输出报告**：按下方模板
9. **草稿也走全流程**：评分草稿必须跑完 1-8 全部步骤（采集→dry-run→硬门槛→七维→满分复核→对照→汇总→报告），**不允许**「先给个大概分数」的偷懒草稿——草稿与正式报告同等严格（源自 k12 讲义 3.4 隐藏设计②）

## 输出报告模板

```
SKILL QUALITY REPORT
═══════════════════════════════════
Skill: [name] ｜ 路径: [path] ｜ 版本: [git commit@branch, dirty?] ｜ 评分时间: [ISO8601]
硬门槛: ✅/❌ H1[frontmatter] H2[<500行] H3[desc≤1024] H4[三权分立]
执行验证: runner [PASS/FAIL/无] ｜ 占位符 [无/有] ｜ 示例入口死引用 [无/有]
元素闭合性: unhandled=[...]（空=闭合）
路由覆盖: missing_in_description=[...]（空=覆盖）
包工程线索: [...]（contract_asset/eval_report/disclosure_card/signature/kit_routing/live_source 命中列表；缺失≠扣分，C5 类 skill 列改进建议）
───────────────────────────────────
触发设计    [x]/20 ｜ 证据: ...
流程纪律    [x]/15 ｜ 证据: ...
结构合理性  [x]/20 ｜ 证据: ...
输出契约    [x]/15 ｜ 证据: ...
护栏        [x]/10 ｜ 证据: ...
配置边界    [x]/5 ｜ 证据: ...
评估闭环    [x]/15 ｜ 证据: ...（runner 可跑/baseline 偏差/豁免声明）
───────────────────────────────────
总分: [x]/100 → 🟢优秀 / 🟡良好 / 🔴不合格
最强维度: ... ｜ 最弱维度: ...
改进优先级: 1. ... 2. ... 3. ...
═══════════════════════════════════
```

## 护栏与降级

- **知识库缺失**：优先读本包 `references/playbook_snapshot.md`（自带快照）；若快照也缺失，使用本文件内嵌的评分细则（七维表已在正文），并在报告中注明「依据内嵌细则，未对照知识库」
- **评分对象不可读**：目标 skill 目录不存在/SKILL.md 无法读取 → 报告失败原因，不强行打分（critical failure）
- **超长 skill**：SKILL.md >800 行时先读章节结构再抽样读正文，报告中注明「抽样评分」
- **LLM 评分不可用**（调用方未注入/无模型通道）→ 规则分照常输出（硬门槛 + 结构 + 评估闭环），LLM 维度标记 degraded，报告中注明「LLM 评分降级」——可降级，不是 critical failure
- **边界**：评分 ≠ 安全审查；发现恶意代码/危险权限，转 skill-vetter，不在此评分
- **回归基线**：baseline.json 含上次预期分；偏差 >5 强制复盘差异维度

## 环境准备（配置边界·依赖声明）

- **运行时**：Python 3.9+（仅标准库，零第三方依赖）
- **安装**：无需 pip install；requirements.txt 为声明文件（说明零依赖）
- **LLM 评分**：调用方注入模式（llm_score.py 不直连任何端点）
  - 生成 prompt：`python3 scripts/llm_score.py bundle.json --prompt-only`
  - Agent 用自己的模型通道作答 → 保存回复 → `python3 scripts/llm_score.py bundle.json --reply <file>` 解析算分
  - 或直接：`python3 scripts/score.py <skill_path>` 拿规则分（硬门槛 + 结构 + 评估闭环）

## 自测用例与回归入口

每次修改本 skill 后**必须**跑：

```bash
# 跑 evals（3 用例 + expected_score 真断言）
python3 evals/runner.py

# 跑回归基线（rules 能判的部分：硬门槛 + 结构合理性 + 评估闭环 + v3.2 新素材）
python3 scripts/regression.py
```

evals 三用例（见 `evals/cases/{normal,negative,boundary}/input.json`）：
1. **normal**：评 pingjia 自己，应 H1/H2/H3/H4 全过 + 结构合理性 20/20 + v3.2 新素材（version_info/executable_evidence/element_closure/route_evidence）非空
2. **negative**：完全没 frontmatter 的 fixture，应 H1 ❌ + H3 ❌
3. **boundary**：500 行整的 SKILL.md，应 H2 ❌

历史 v1 自测用例仍在 `examples/score_evals.md`（兼容性保留）。

## 评分细则详解

> 字段命名映射：`assets/report_template.json` 中 `H4_three_principles` = 三权分立一票否决（机器字段名用英文，中文文档用「H4 三权分立」）。

每个子项 0/0.5/1 档位范例 + 证据示例：见 `references/scoring_rubrics.md`（按维度索引）。

## 权重变更历史

v1→v2 变更对比 + 变更原因：见 `references/weights_rationale.md`。

## 理论依据

评分细则来源于 k12-teacher-skills 三权分立 + playbook 七步方法论。
章节速查与实战案例：见 `references/playbook_link.md`。

## 参考

- 知识库：knowledge/methods/agent-skill-creation-playbook.md
- 配套：skill-creator-guide（创建/审查流程）、skill-vetter（安全审查）
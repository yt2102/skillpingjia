# skillpingjia 变更史

> 所有版本的变更沉淀在这里。SKILL.md 只留最新版摘要，避免主体膨胀。

---

## v3.4.1（2026-11-11）

**触发原因：** 实际使用审查——三件对本机日常就有正收益的优化（社区贡献场景只是顺带受益）。

1. **噪音过滤（score.py `_is_noise`）**：files 清单、`_get_py_files` 脚本收集、脚本计数、包工程证据采集四处 `rglob` 统一排除 `*.bak*` / `__pycache__` / `.git` / `.pyc/.pyo/.tmp/~`。自证实锤：过滤前 pingjia 扫自己的 files 清单混进 8 个 .bak/pyc——陈旧备份参与证据采集=评的可能是死代码。
2. **`--summary` 模式**：裁 `skill_md_content` 全文 + 截断长 snippets（每项 ≤160 字符 ×2）。日常 judge 评审用 summary，回归断言用全量。
3. **references 自包含**：`references/playbook_snapshot.md`（workspace playbook 192 行完整快照），playbook_link.md 与 SKILL.md 引用改为包内优先。此前评分的理论依据外链 workspace 私有路径，skill 拷到别处细则断链。

**验收**：runner 7/7 PASS 零破坏；files 清单复扫 .bak=0；summary 模式 token 实测对比记入本条。

### 同日增补（v3.4.2 脱敏清洗，为可外发状态）

- **机构名脱敏**：fixture 内嵌的真实编制单位默认值 → `示例科技有限公司 集成业务部`（libjishu.py 默认值×2 + fixture SKILL.md 示例×2）；真实主管部门示例 → `示例主管单位`；细则示例中的真实厂商名 → "工作邮箱"泛称×2。回归检测力不受影响（heading 漂移/兜底盲点缺陷结构与机构名无关，runner 复跑验证）
- **路径匿名化**：regression_v315_report.md 机器绝对路径 → `<agent-home>/...`；agent 运行时名 → 泛称
- **人称匿名化**：weights_rationale.md 3 处内部人称 → 需求方 / 评审 agent（决策史内容原样保留）
- **悬空外链清理**：SKILL.md 飞书文档引用 → 改指 CHANGELOG v3.3（内容已全量沉淀）
- **LICENSE**：补 Apache-2.0 全文 + Application notice；frontmatter 加 `license: "Apache-2.0"` 字段
- 保留项（有意不改）：fixture 名 `jishufangan`（泛化词不指向特定方）、政务规范公开标准字样（回归样本真实性来源）、git 旧历史（发布日全新 init，本机无影响）
- **验收**：全库复扫机构名/人称/绝对路径/外部文档链接 = 0 命中；runner 7/7 PASS；自评 H1-H4 全过

---

## v3.4（2026-11-11）

**触发原因：** NVIDIA auto-ontology skill 套件（nvidia-ontology-setup/management/query，Apache-2.0，sigstore 签名）完整解剖。发现我方 Matrix v0.2 的 SK-CONT（机器契约）与 SK-EVAL（评测证据）条款在其上被完整实战复现，且其包形态暴露我方体系三个空白：skill 级 workflow 契约资产、出厂评测报告、披露卡+签名。

**变更范围：**

### 新增 `package_engineering` 线索采集器（score.py）

六项线索，全部"有/无+路径"事实采集，线索非断言：

| 线索 | 检测 | 判分含义（judge 裁量） |
|------|------|------|
| contract_asset | assets/ 或名字含 contract 的 yaml/json，内容含 ≥2 个契约键（workflows/input_artifacts/output_artifacts/required_fields/statuses/gates） | 流程产出物可机检 → 流程纪律-每步有产出 1.0 候选 |
| eval_report | BENCHMARK.md / EVALUATION.md / evaluation-report.md | 出厂带评测证据 → 评估闭环-回归基线 1.0 候选 |
| disclosure_card | skill-card.md / disclosure.md | 风险/依赖/凭证显式声明；缺失不扣分 |
| signature | *.sig / *.minisig / cosign.yaml / provenance.json | 供应链完整性；缺失不扣分 |
| kit_routing | AGENTS.md/INDEX.md 含交接表特征（owning skill/归属/handoff + 表格行指向 skill 名） | 多 skill 套件协作 → 触发设计-技能互斥 1.0 候选 |
| live_source_principle | SKILL.md 声明活真源（trust the handshake / 别把表抄进会话等，双语） | 防 Policy-Runtime Drift 自觉声明，正向信号 |

**防误伤设计**：disclosure_card/signature 缺失一律不扣分，仅 C5（发布/共享）触发器命中的 skill 在报告改进建议区列出——个人小 skill 不该被大厂包标准打残。

**验收**：
- 新 fixture `evals/cases/kit_engineering`（模拟五件套包）六项全命中，runner 7/7 PASS（6 项历史回归零破坏）
- 真实样本回归：NVIDIA nvidia-ontology-query 实测命中 5/6；kit_routing 不命中为**正确边界**（路由入口在套件根 AGENTS.md，成员包内没有——采集器不跨包误探）

**收口五件套**：代码 + 键表白名单（package_engineering/contract_asset/eval_report/disclosure_card/signature/kit_routing/live_source_principle/contract_keys/snippets/paths/present）+ SKILL.md 摘要与报告模板 + CHANGELOG + runner 全量重跑。baseline 不动（total_score 口径不变，新线索不参与规则分）。

**未做（明确不做）**：不新增硬门槛；不自动判分；不做签名验证（只探文件存在，验签需证书链，超出评分器边界）。

---

## v3.3（2026-09-07）

**触发原因：** jishufangan v3.15 三轮深度评审（ChatGPT 源码分析 + jishufangan 自评 + 第三方复核）的收敛结论。5 类盲区转化为 pingjia 判据。

**变更范围：**

### P0-1 · IR 全链路双向闭合性（双向闭合检查）

**理论依据：** v3.2 的 element_closure 只查单向——"SKILL.md 承诺的类型 ⊆ 渲染器处理的分支"。
jishufangan 事故证明还存在反向缺口：**parser 产出的类型 ⊄ 序列化器允许的类型**（heading_preserved 案：parser 产生、renderer 认识、save_structure 的 allowed_types 拒绝）。三个模块三套"合法类型"定义各自漂移，走落盘路径即炸。

**判据定义：**
```
producer_types = 解析器/生成入口实际产出的元素类型集合
consumer_types = 每个消费点（序列化/保存/加载/渲染/校验）声明的合法类型集合
缺口 = { producer 有、任一 consumer 无 } 的类型
缺口非空 → 「结构化中间表示」子项 1.0 → 0.5，并在报告中列出具体缺口对
```

**score.py 采集逻辑（伪代码）：**
```python
def ir_closure_evidence(skill_dir):
    ev = {"producers": {}, "consumers": {}, "gaps": []}
    # 1. 找 producer：函数体内含 X.append((TYPE, 形如元组)) 的类型字符串
    #    泛化正则：\.append\(\s*['"]([a-z_]+)['"]\s*,   → 采集类型名
    # 2. 找 consumer：allowed_types = {...} / {'a','b'} / ["a","b"] 等集合字面量，
    #    以及 if typ == / elif typ in 分支里出现的类型名（渲染分支即隐式白名单）
    # 3. 交叉比对：producer ∪ 与每个 consumer 的差集
    # 4. 只报"真实缺口"：排除同时无任何 consumer 声明的类型（可能是内部临时类型），
    #    保留"至少一个 consumer 认、另一个不认"的——那才是 contract drift
    return ev
```

**判定规则：**
- gaps 非空 → 输出契约「结构化中间表示」0.5，证据写明"类型 X 被 producer 产出但 consumer Y 拒绝"
- 无法静态识别 producer/consumer（如全动态构造）→ 输出 ` `ir_closure: inconclusive`，不扣分，报告注明"建议人工核对"

**测试用例：** fixtures/ 新增 `contract_drift/`——一个最小 python skill：parser 产出 `('heading_p', ...)`，save 函数 allowed_types 少它。断言 gaps 含 `heading_p`。

---

### P0-2 · 静默失败扫描（dry-run 增强）

**理论依据：** `except Exception: pass` 在解析路径累积 → 静默失败 → heuristic 接管 → 产出"看起来正常"的文档。比崩溃危险一个量级（把失败伪装成成功）。

**score.py 采集逻辑：**
```python
import re
PAT_PASS = re.compile(r'except[^:]*:\s*\n\s*pass\s*$', re.M)
PAT_WARN = re.compile(r'_?logger\.warning|logging\.warning|print\(.*WARN')

def silent_failure_evidence(scripts_root):
    ev = {"files_scanned": 0, "pass_count": 0, "warn_paired": 0, "suspicious": []}
    for py in scripts_root.rglob("*.py"):
        ev = ["files_scanned"] += 1
        content = py.read_text(encoding="utf-8")
        pass_hits = list(PAT_PASS.finditer(content))
        for m in pass_hits:
            # 检查同一文件是否有 warning 配套
            if not PAT_WARN.search(content):
                ev = ["pass_count"] += 1
                ev = ["suspicious"].append({
                    "file": str(py.relative_to(scripts_root)),
                    "line": content[:m.start()].count("\n") + 1,
                    "snippet": m.group(0)[:80],
                })
            else:
                ev = ["warn_paired"] += 1
    return ev
```

**判定规则：**
- pass_count > 5 且 warn_paired / pass_count < 0.3 → 配置边界或护栏降档证据
- 评分上不直接扣分（线索非断言），但报告里必列"裸 pass 位置+文件"，给 judge 提示

---

### P1-1 · 兜底分支触发审计

**理论依据：** v3.2 的 element_closure 已检查"渲染分支能处理哪些 type"，但**没检查兜底条件是否合理**。jishufangan v3.15 案例：parse_docx 产出 h1_present = False 时，generate_from_structure 兜底段（用 elif typ in ('body', ...)）**没把 h1_present 列进去**——h1_present 类型落进兜底失败、整个文档没 H1。

**判据定义：**
```
兜底分支 = 渲染/处理路径中"否则就……"或"if typ in (..., ):"或 except Exception: pass
兜底条件覆盖 = 兜底分支里的 typ in (xxx) / isinstance 检查，列出实际接受的类型
对比上游 producer 实际产出的类型（producer_types）
缺口 = producer 有、兜底条件无 → 落进兜底分支会无声失败
```

**score.py 采集：**
```python
FALLBACK_BRANCH_PATTERNS = [
    r'elif\s+typ\s+in\s+\(([^)]+)\)',
    r'if\s+typ\s+in\s+\(([^)]+)\)',
    r'except\s+\w+.*:\s*$',
    r'\.get\([\'"](\w+)[\'"]\s*,\s*None\)',  # dict.get 兜底 key
]
```

**测试用例：** fixtures/ 新增 `blind_fallback/`——最小 python skill：parser 产出 `('h1_present', bool)`，renderer 的 `elif typ in (..., 'body',):` 缺 'h1_present'。断言 blind_fallback 触发。

---

### P1-2 · 真实样本回归要求

**理论依据：** 评估闭环分（15）拆出 1 分专给"必须有真实事故 case"。否则 skill 可以用 synthetic fixture 自我循环验证——无法证明对真实世界有效。

**判据定义：**
```
评估闭环子项拆分为：
- 1 分：evals/ 含真实事故 case（即 jishufangan 这种"踩过的坑"的回归）
- 1 分：rubric.md 有明档分档（≥80/60-79/<60）
- 1 分：baseline.json 记录 + 偏差 >5 自动复盘
（其他子项项不变）
```

**验证：** pingjia 自己有 evals/，按此判据走。jishufangan v3.15 修复前快照已存档，可回评。

---

### P2 · 声明-实现对照

**理论依据：** SKILL.md 可能描述了"5 个入口"但 scripts/ 实际只暴露 2 个——LLM-as-judge 读 SKILL.md 时会按字面理解，用了不存在的入口 → silent fail。

**本期半自动：** score.py 采集 SKILL.md 中 code block 提到的入口函数名 + scripts/ 实际暴露的 `def xxx(` 列表，差集 → report evidence。判定交给 judge（区分"装饰性提及" vs "承诺调用"）。

---

### 设计底线（继承 pingjia 传统）

1. **泛化实现**——全部行为特征识别（类型字面量交叉/异常模式/兜底语义），不绑 docx 词表，非文档类 skill 零误报
2. **线索非断言**——静态采集只产 evidence，judge 确认才动分（v3.1 立的规矩不破）
3. **自我矛盾自查**——加"真实样本覆盖"门槛前，先给 pingjia 自己补上 jishufangan 回归 case（呼应 H5 暂缓的同一逻辑）

### 验收"咬合检查"

**v3.3 完成后必须回评 jishufangan v3.15（修复前快照）**：三个新判据必须分别抓出 allowed_types 缺口、h1_present 盲点、裸 pass——**抓不出任何一项 = 判据实现有误，回工**。评测器的进化必须用刚发生的事故验证，这一步把"pingjia 升级"和"jishufangan 修复"两条线锁成了一个闭环。

---

## v3.2（2026-08-22 实战反思）

### 评分流程新增 1.5 步「执行验证 dry-run」

- 真实跑目标 skill 的 `evals/runner.py`（记 PASS/FAIL）
- 扫描 scripts 占位正文（如「内容待撰写」）
- 核对 SKILL.md 示例代码引用的入口函数在 scripts 中是否存在（死引用检测）

### 输出契约新增「元素闭合性」检查

SKILL.md 承诺的 structure 元素类型（heading/body/table/image...）必须 ⊆ 渲染入口实际处理的分支。泛化实现：渲染入口用行为特征识别，不依赖函数名。

### 触发设计新增「路由覆盖一致性」

SKILL.md 内部有路由决策树/版本路由时，description 必须覆盖所有分支入口词。泛化实现：分支词从路由章节上下文动态提取。

### 评估闭环新增「有效性」检查

baseline 偏差 >5 自动标记需复盘；runner 是否真实可跑；验证器是否有「设计性偏离豁免」声明。

### 报告新增「版本声明」

git commit / branch / dirty / mtime——防评错副本。

**背景：** 评 jishufangan 时发现「简版一键调用产出占位符」「generate_from_structure 静默跳过 image」两个真实缺陷，纯静态评分抓不到，必须 dry-run。

---

## v3.1（2026-08-18 反思修正）

### 输出契约判据改为「问本质不问形式」

三问：数据独立于渲染？改数据不碰渲染出新版？可独立校验？——中间表示不限 JSON，YAML/dict/数据层均可。

### score.py 新增 `contract_evidence` 线索采集

自动扫描中间表示/渲染入口/校验/防漂移。**线索非断言**，judge 自行判断。

### 评分流程新增第 4 步「满分复核」

1.0 子项必须附一句「为什么不是 0.5」，写不出理由自动降 0.5。

**背景：** 评 jishufangan 时输出契约误给满分（表面特征齐全但中间表示未落盘），暴露判据可操作性不足。

---

## v3（2026-08-18）

- 计分制 110 → **100**（方案 B：触发 20 / 流程 15 / 结构 20 / 输出 15 / 护栏 10 / 配置 5 / 评估 15），分档回归 100 制习惯
- 配置边界 10→5（子项 3/3/2/2 → 2/1/1/1）
- 评估闭环 20→15（子项 5/5/5/5 → 4/4/4/3）
- llm_score.py 改为**调用方注入**（删全部网络代码）
- 评分流程新增「草稿也走全流程」防偷懒草稿
- 详见 references/weights_rationale.md

---

## v2（2026-08-17 回炉）

- 新增硬门槛 H4（三权分立一票否决）
- 维度权重重分配：触发 25→20，结构 15→20，评估 15→20；新增配置边界 10 分
- 流程纪律子项：失败分级 4→6
- 触发设计：核心信号 5→4
- 输出契约：防漂移 3→4
- H5（评估闭环≥5）**暂缓**：等 pingjia 自己有 evals/ 目录后再加，避免自我矛盾
- （原外部文档链接已清理，建议内容已全部沉淀于本 CHANGELOG 各版本条目）

---

## v1（初版）

基于知识库 `knowledge/methods/agent-skill-creation-playbook.md` 的评分机制，对任意 Agent Skill 做质量评估。
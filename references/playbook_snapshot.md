# Agent Skill 生成 Playbook（知识库）

> 用途：生成/审查/优化 Agent Skill 时查阅。基于《如何创建 Agent Skill —— 讲义（k12-teacher-skills 实战案例）》、Anthropic 官方方法论（agentskills.io + skill-creator）、本书 chapter2/chapter8。
> 配套：skills/skill-creator-guide/（创建流程总控）、skills/lean-skill-builder/（轻量构建）
> 案例源码：github.com/anthropics/k12-teacher-skills（Apache 2.0，SKILL.md 481 行 + evals）

---

## 0. 核心认知（先记住这三条）

1. **Skill 是能力包，不是 prompt**：目录 + SKILL.md + scripts/references/assets，随任务按需加载。
2. **渐进式披露三级**（上下文只花在刀刃上）：
   - L1 元数据（name + description）→ 常驻 ~100 词 → 决定「要不要加载」
   - L2 SKILL.md 正文 → 触发时加载（<500 行）→ 决定「怎么做」
   - L3 references/scripts/assets → 按需加载 → 决定「细节/执行」
3. **description 是唯一的触发入口**：`The description carries the entire burden of triggering.` 写不好，skill 永远不会被加载。

---

## 1. 判断：该不该做成 Skill？（chapter8 决策框架）

选择更新载体的首要依据是**目标能力能否被某种载体自然表达**：

| 经验类型 | 载体 |
|---|---|
| 事实/经验 | 知识文档（可检索参考） |
| 可语言化的策略，作用于特定领域/项目/工具 | **Skill**（按需加载的指令包） |
| 作用于几乎所有任务的规则 | 系统提示词 |
| 可精确执行的流程/约束 | 程序（工具代码） |
| 感知/语言风格/隐式策略（难压缩成规则） | 模型参数（后训练） |

经验升级路径：新策略 → 经验文档 → 多案例验证后提升为 Skill；步骤稳定后可编译成工具代码。
判断要点：**只在某个领域/项目/工具上生效的复杂流程，才适合写成 Skill**。通用规则进提示词，一次性的任务不写 Skill。

---

## 2. 解剖最佳标本：k12-teacher-skills 三权分立

```
k12-lesson-planning/
├── SKILL.md          # 481 行核心指令（frontmatter + 五步流程）= 大脑
├── references/       # 领域知识按需加载（math/ela/science/social_studies.md + 知识图谱调用序列 + 示例）= 教科书
└── scripts/          # 确定性执行（render_all.sh + render_lesson_docx.py）= 双手
```

设计要点：**脚本不做判断（规则写死在 SKILL.md），模型不碰格式（JSON 由脚本翻译）——各干各的，互不越权。**

为什么它是最佳标本：
- 触发设计完整：正触发 + 隐式意图 + 负触发 + 技能互斥，四层齐全
- 流程有纪律：每步有产出、有失败分级、有搜索预算、有打扰额度
- 评估可复制：P/R/O/M 四维 rubrics + LLM-as-judge，5 张 CSV

---

## 3. 七步创建方法论（核心）

总原则：**把 skill 当产品设计，不是写一段 prompt。**
① 想清楚 → ② 搭骨架 → ③ 写触发 → ④ 写流程 → ⑤ 输出契约 → ⑥ 加护栏 → ⑦ 建评估
**第 ③ 步（触发）重中之重——触发错了，后面全白搭。第 ⑤ 步（输出契约）最值得偷师。**

### ① 想清楚：动手前答 4 问
- 做什么？
- 何时触发？（显式 + 隐式）
- 输出格式？
- 要测试吗？（能客观验证 → 必须有 evals；主观输出如文风/设计可不强求）

### ② 搭骨架：硬规范
- SKILL.md < 500 行 / < 5000 tokens；超了拆进 references + 层级指针
- description ≤ 1024 字符（agentskills.io 硬性上限）
- 领域变体拆文件（官方 cloud-deploy 拆 aws/gcp/azure.md；k12 同款 math/ela/...）
- 大参考文件（>300 行）带目录
- ❌ 禁止包含：README/INSTALLATION/CHANGELOG 等人看文档

### ③ 写触发：description 是唯一的入口（重点）
原理：agent 启动时只读所有 skill 的 name + description 判断相关性。**Claude 天然 undertrigger（「该用不用」）→ description 要写得主动（pushy），不能只写「能做什么」。**
匹配对象是**用户意图**（用户想达成什么），不是 skill 内部实现。

k12 四层触发体系（模板）：
1. 正触发·显式词：任务词表（lesson plan / unit plan / daily plan...）
2. 正触发·隐式意图：真实话术样例（"I'm teaching long division to 5th graders"）
3. 核心信号：一句话本质（teacher needs new instructional content）
4. 负触发：明确不接什么（grading/rubric/quiz...），且指明「直接答」（不加载 ≠ 不回复）

进阶手法：
- **技能互斥（双向声明）**：两个相关 skill 都写对方边界，消解竞争（planning ↔ differentiation）
- **pushy 原则**：官方原话 "Make sure to use this skill whenever the user mentions dashboards, data visualization... even if they don't explicitly ask for a 'dashboard'"
- **触发测试**：约 20 条 eval queries——8-10 条应触发（变换措辞/明示暗示/简繁），8-10 条不应触发（重点 near-miss：关键词重叠但任务不同）

### ④ 写流程：流水线 + 编排纪律
k12 五步模板：
- Step 0 路由：判定领域 → 读对应 references（懒加载；不读 = critical failure）
- Step 1 澄清：0-2 个问题，其余默认值静默应用（打扰预算）
- Step 2 锚定：查外部权威数据（知识图谱）→ 先查后写防幻觉
- Step 3 构建：按规范组装内容（结构枚举全覆盖）
- Step 4 草稿：Human-in-the-loop 先给草稿，批准才产出
- Step 5 输出：写结构化 JSON → 脚本渲染（同一轮完成）

编排纪律（收窄模型决策空间）：
- 搜索预算：最多 3 次尝试（code → keywords → 变体），超限降级
- 并行批处理：独立调用一次并发
- 禁止路径：明确写「不要做什么」（Never call...）
- 提取纪律：只取指定的，其余丢弃
- 失败分级：critical failure（必做）vs 可降级（依赖断了 → 凭经验 + footer 声明）
- 草稿也走全流程（防「偷懒草稿」）

### ⑤ 输出契约：JSON 单源 + 防漂移（灵魂设计）
核心思想：**让 LLM 生成「数据」不是「成品」**——模型写结构化中间表示（JSON），确定性脚本翻译成成品格式（Word/HTML/...）。模型不手写 OOXML。

防漂移机制（from_shared）：
```
shared: { p1: "…题目…" }
教案:    from_shared(p1)
学生页:  from_shared(p1)   → 同一内容两处永远一致，改一处全同步
```

四大好处：可校验（JSON 合法 → 必能渲染）、可重渲染（修订成本≈0）、防漂移、模型友好。
实现层：给模型定义 block 类型「乐高积木」（paragraph/h2/table/callout...），渲染器映射成目标格式。
降级保障：依赖装不上 → 先出替代预览再大声报错，**绝不静默产出残缺交付物**。

### ⑥ 加护栏：信任与降级设计
| 护栏 | 做法 |
|---|---|
| 内容合规 | 外部材料只影响结构，输出文本必须原创 |
| 用户语言防火墙 | 对最终用户只说结果（「你的教案来了」），永不提 JSON/脚本/工具名 |
| 降级路径 | 外部依赖断 → 凭经验 + footer 声明；渲染失败 → 明确告知 |
| 默认值 | 全量构建为默认，草稿只在明确要求时给（减少摩擦） |

### ⑦ 建评估：质量闭环
P/R/O/M 四维 rubrics 模板：
- P（核心专业度 Pedagogy）：如数学探索须含 start-unknown 题型
- R（严谨度 Rigor）：出口题持误区者必须答错
- O（输出 Output）：格式可编辑、结构完整、密度达标
- M（脚手架 Model Scaffolding）：条件性准则（K-5 只在 K-5 生效，跳过 ≠ 失败）

官方评测流程（skill-creator）：
1. 2-3 个真实测试 prompt（保存 evals/evals.json）
2. **with-skill + baseline 双跑**：同 prompt 两个 subagent 同时启动（带/不带 skill）
3. 趁运行写量化断言（assertions）
4. 对比展示：skill 到底加了多少分
5. 改写 → 迭代 → 扩大测试集

**关键判据：带不带 skill 没差别 → 这个 skill 没有存在价值。**

---

## 4. 自查清单：创建前 9 问

1. description 够 pushy 吗？负触发和互斥写了吗？
2. 正文 < 500 行吗？领域内容拆进 references 了吗？
3. 流程步骤化了吗？每步有产出和失败处理吗？
4. 澄清设了打扰预算吗（0-2 问 + 默认值）？
5. 用了结构化中间表示吗？输出可校验、可重渲染、防漂移？
6. 外部依赖有降级路径 + 痕迹声明吗？
7. 用户永远看不到技术细节吗（JSON/脚本/工具名）？
8. 有 evals 吗？输出能否 0/1 判分？
9. 用真实任务跑过 with/without 对照吗？

**全部 ✅ 才算合格。任何一条 ❌，回到对应步骤重做。**

---

## 5. 常见坑：5 个典型错误

| 坑 | 症状 | 修复 |
|---|---|---|
| description 太谦虚 | 只写「能做什么」→ undertrigger | 写成指令 + 适用场景 + 用户没明说的也要列 |
| 正文塞满领域知识 | SKILL.md 超 500 行 → 上下文爆炸 | 细节拆 references，正文只留流程和指针 |
| 直接生成成品格式 | 模型手写 Word/PDF → 格式错误多 | 结构化中间表示 + 脚本渲染 |
| 无降级路径 | 外部 API 一断 → 直接失败或撒谎 | 降级 + 痕迹声明（footer） |
| 无评估就发布 | 质量靠感觉，迭代没依据 | rubrics + with/without 对照 |

---

## 6. 可迁移的六条原则

1. **结构化中间表示**：模型生成数据，脚本生成成品
2. **触发即全部**：description 承担所有触发责任
3. **先查后写**：外部权威数据锚定，防幻觉
4. **打扰预算**：默认值静默应用，问题额度 0-2
5. **降级是设计**：任何外部依赖都有降级路径 + 声明
6. **质量可度量**：rubrics + LLM-as-judge，版本可回归

---

## 7. 参考资料

- k12-teacher-skills 源码：github.com/anthropics/k12-teacher-skills
- Agent Skills 官方规范：agentskills.io（Specification / Best practices / Optimizing descriptions / Evaluating skills）
- 官方 skills 仓库：github.com/anthropics/skills（⭐168k，17 示例 + skill-creator）
- Engineering 博客：anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- 本书 chapter2（渐进式披露机制细节）、chapter8（经验沉淀为知识/指令/程序/参数的决策）
- 本地：skills/skill-creator-guide/（流程总控 + 本地踩坑）、skills/lean-skill-builder/

# Agent Skill 创建 Playbook 链接

> pingjia 评分细则的理论依据来源于 playbook。**v3.4.1 起本包自带快照**：`references/playbook_snapshot.md`（192 行完整版）。
> workspace 内如有更新版（`knowledge/methods/agent-skill-creation-playbook.md`）以更新版为准，读不到就用快照。

## 章节速查

| 章节 | 内容 | 跟 pingjia 维度的对应 |
|---|---|---|
| §0 核心认知 | L1/L2/L3 渐进式披露 | 结构合理性 |
| §1 判断该不该做成 Skill | 经验升级路径 | 护栏 |
| §2 k12-teacher-skills 三权分立 | 教科书解剖 | **H4 三权分立硬门槛依据** |
| §3 七步创建方法论 | ①想清楚 → ②搭骨架 → ③写触发 → ④写流程 → ⑤输出契约 → ⑥加护栏 → ⑦建评估 | 触发设计 + 流程纪律 + 输出契约 + 评估闭环 |
| §4 经验决策树 | 事实→知识库；策略→Skill；规则→系统提示词；流程→工具 | **配置边界**（通用规则 vs 单点数据） |
| §5 触发设计 | 正触发 + 隐式意图 + 负触发 + 互斥（4 层） | 触发设计 |
| §6 流程纪律 | 步骤化 + 产出 + 失败分级 + 搜索预算 + 打扰额度 | 流程纪律 |
| §7 评估闭环 | rubrics + LLM-as-judge + 5 张 CSV | 评估闭环 |

## 关键引用

### play 调查 §2 k12-teacher-skills

```
k12-lesson-planning/
├── SKILL.md          # 481 行核心指令（frontmatter + 五步流程）= 大脑
├── references/       # 领域知识按需加载 = 教科书
└── scripts/          # 确定性执行 = 双手
```

设计要点：**脚本不做判断（规则写死在 SKILL.md），模型不碰格式（JSON 由脚本翻译）——各干各的，互不越权。**

→ H4 三权分立硬门槛的理论依据

### play 调查 §4 经验决策树

| 经验类型 | 载体 |
|---|---|
| 事实/经验 | 知识文档（可检索参考） |
| 可语言化的策略 | **Skill**（按需加载的指令包） |
| 作用于几乎所有任务的规则 | 系统提示词 |
| 可精确执行的流程/约束 | 程序（工具代码） |

→ 配置边界维度依据：通用规则进 Skill，单点数据进配置

### play 调查 §5 触发设计

> **description 是唯一的触发入口**：`The description carries the entire burden of triggering.`

→ 触发设计维度依据

### play 调查 §7 评估闭环

> **关键判据**：带不带 skill 没差别 → 没有存在价值。

→ 评估闭环维度依据

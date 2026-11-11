# skillpingjia 评分 rubrics（判分依据）

> 本文件是「评估闭环·rubrics 判分」的落地文件。完整 0/0.5/1 三档判据见
> `references/scoring_rubrics.md`（按维度索引），此处为速查索引 + 判分说明。

## 判分方式

LLM-as-judge 按 `references/scoring_rubrics.md` 的三档范例逐子项判 0/0.5/1，
乘以维度权重（见 SKILL.md 七维表）得维度分，加权求和得总分（100 分制）。

## 维度速查（v3，100 分制）

| 维度 | 满分 | 核心判据 |
|------|------|----------|
| 触发设计 | 20 | description 是唯一入口：显式词/隐式意图/核心信号/pushy/负触发/互斥 |
| 流程纪律 | 15 | 步骤化 + 每步产出 + 失败分级 + 禁止路径 + 打扰预算 |
| 结构合理性 | 20 | 规则判：SKILL.md<500 行 / references 拆解 / scripts 确定性 |
| 输出契约 | 15 | 结构化中间表示 / 可校验 / 可重渲染 / 防漂移 |
| 护栏 | 10 | 降级路径 + 痕迹 / 用户语言防火墙 / 内容合规 |
| 配置边界 | 5 | 邮箱/项目/路径/模型依赖：通用规则 vs 单点数据分离 |
| 评估闭环 | 15 | 规则判：evals 用例 / rubrics / with-without / baseline |

## 判定原则

1. 每个子项只能 0/0.5/1，禁止中间值
2. 每个子项必须配 1 行证据（≤80 字，引用行号/章节/文件存在性）
3. structural_sanity 和 evaluation_closure 由 score.py 规则判，LLM 交叉验证
4. 带不带 skill 没差别 → 评估闭环判定 skill 无存在价值

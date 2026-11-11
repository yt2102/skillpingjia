"""
skillpingjia LLM-as-judge 评分脚本（v3：100 分制 + 调用方注入）

输入：score.py 输出的素材包（JSON）
输出：按 100 分制七维的数值评分（JSON）

v3 变更（2026-08-18）：
- 计分制 110 → 100（方案 B：触发 20 / 流程 15 / 结构 20 / 输出 15 / 护栏 10 / 配置 5 / 评估 15）
- 分档回归 100 制习惯：≥80 优秀 / 60-79 良好 / <60 不合格
- 删除全部网络调用代码（call_llm）——LLM 调用由调用方注入，脚本零外部依赖：
  * --prompt-only：只输出评分 prompt，由调用方（Agent / 任意模型）作答
  * --reply <file>：读取 LLM 回复文件 → 解析 → 算总分
- 因此换模型 / 复制给别人用都不需要改脚本

用法：
    python3 llm_score.py <bundle.json> --prompt-only            # 生成 prompt（调用方去调 LLM）
    python3 llm_score.py <bundle.json> --reply llm_reply.json   # 解析回复并算分
    cat bundle.json | python3 llm_score.py - --prompt-only
"""
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any

# 评分模板（从 SKILL.md + references/scoring_rubrics.md 提取的关键判据）
SCORING_PROMPT = """你是 skillpingjia 的 LLM-as-judge 评分员。

目标：评估一个 Agent Skill 的质量，按 100 分制七维打分。

# 评分子项（含 0/0.5/1 档位）

## 1. 触发设计 (20 分)
- 显式触发词 (5分): 任务词表完整 1.0 / 1-2 词 0.5 / 无 0
- 隐式意图 (5分): 真实话术样例 1.0 / 仅有功能描述 0.5 / 无 0
- 核心信号 (4分): 用户意图描述 1.0 / 偏功能声明 0.5 / 完全不提意图 0
- pushy 句式 (1分): 强指令句式 1.0 / 隐含 pushy 0.5 / 无 0
- 负触发 (3分): 列不接场景+直接答指示 1.0 / 仅列不接 0.5 / 无 0
- 技能互斥 (2分): 双向边界 1.0 / 单向 0.5 / 无 0

## 2. 流程纪律 (15 分)
- 步骤化管线 (3分): 显式 Step 0/1/2 或 → 链 1.0 / 模糊 0.5 / 无 0
- 每步有产出 (3分): 每步有产出物字段 1.0 / 部分 0.5 / 无 0
- 失败分级 (6分): critical vs 可降级区分 1.0 / 仅说"可能失败" 0.5 / 静默截断 0
- 禁止路径 (2分): "Never call..." 明确 1.0 / 模糊 0.5 / 无 0
- 打扰预算 (1分): 0-2 问+默认值 1.0 / 仅说一下 0.5 / 无 0

## 3. 结构合理性 (20 分) [规则判]
- SKILL.md <500 行 (5分): 真 1.0 / 假 0
- references 拆解 (8分): ≥3 份 1.0 / 1-2 份 0.5 / 全塞 SKILL.md 0
- scripts 确定性 (7分): 脚本接管+模型只写 JSON 1.0 / 部分 0.5 / 全 LLM 0

## 4. 输出契约 (15 分)
- 结构化中间表示 (5分): 数据层独立于渲染逻辑（文件/变量/数据层不限形式）1.0 / 函数式封装或数据嵌代码 0.5 / 直出成品 0
- 可校验 (3分): 输出可 0/1 判分 1.0 / 部分 0.5 / 无 0
- 可重渲染 (3分): 改数据秒出新版不碰渲染 1.0 / 需改脚本重跑 0.5 / 不可 0
- 防漂移 (4分): 单一事实源机制（占位符/from_shared/CONSTANTS 任意形式）1.0 / 注释提示 0.5 / 两处硬编码 0
⚠️ 判据问本质不问形式：中间表示可以是 JSON/YAML/dict，不限定文件格式。判 1.0 必须三问皆是：①数据独立于渲染？②改数据不碰渲染出新版？③可独立校验？

## 5. 护栏 (10 分)
- 降级路径+痕迹 (4分): fallback+stderr 警告 1.0 / 仅说明 0.5 / 无 0
- 用户语言防火墙 (3分): 终用户输出无 JSON/脚本名 1.0 / 偶有技术名 0.5 / 全是 0
- 内容合规 (3分): 版权+原创+安全约束 1.0 / 部分 0.5 / 无 0

## 6. 配置边界 (5 分) [v3 缩减至 5 分]
- 个人邮箱/账号 (2分): 全 .env/config 1.0 / 半硬编码 0.5 / 2+处硬编码 0
- 项目/客户名 (1分): config 接管 1.0 / 1 处硬编码 0.5 / 2+ 0
- 路径魔法 (1分): 全环境变量 1.0 / 1 处短链 0.5 / 多处 0
- 模型/工具依赖 (1分): 零硬编码+调用方注入 1.0 / 半参数化 0.5 / 硬编码模型/端点 0

## 7. 评估闭环 (15 分) [v3 缩减至 15 分]
- evals/ 目录 (4分): 有用例 1.0 / 仅 README 0.5 / 无 0
- rubrics 判分 (4分): 档位表+判据 1.0 / 部分 0.5 / 无 0
- with/without 对照 (4分): 双跑对照记录 1.0 / 仅计划 0.5 / 无 0
- 回归基线 (3分): baseline 文件+偏差复盘 1.0 / 仅文件 0.5 / 无 0

# 输出格式（强制 JSON schema）

输出**仅** JSON，每个子项给 0/0.5/1 三档之一，**配合一行证据**（≤80 字）：

```json
{{
  "trigger_design": {{"score": 0|0.5|1, "evidence": "..."}},
  "process_discipline": {{...}},
  "structural_sanity": {{"score": 0|0.5|1, "evidence": "..."}},
  "output_contract": {{...}},
  "guardrails": {{...}},
  "config_boundary": {{...}},
  "evaluation_closure": {{...}}
}}
```

# 关键要求

- **每个子项只能 0/0.5/1**——不要 0.7 这种中间值
- **每个子项必须配 1 行证据**（≤80 字，引用 SKILL.md 行号/章节/文件存在性）
- **structural_sanity 和 evaluation_closure 已被规则判过**——你仍要给分（用于交叉验证），但分数应与规则判一致
- **不输出 JSON 以外的内容**——只输出 ```json\n{...}\n```
- **不要 echo 用户输入**——直接输出评分

# 目标 SKILL.md 全文

```
__SKILL__
```

# 目标素材包（结构化信息）

```json
__BUNDLE__
```

请输出评分：
"""


def build_prompt(bundle: Dict[str, Any]) -> str:
    """从素材包构造评分 prompt（纯函数，无副作用）。"""
    bundle_json = json.dumps(
        {k: v for k, v in bundle.items() if k != "skill_md_content"},
        ensure_ascii=False, indent=2
    )
    skill_md_content = bundle.get("skill_md_content", "")
    return SCORING_PROMPT.replace("__SKILL__", skill_md_content).replace("__BUNDLE__", bundle_json)


def parse_llm_output(raw: str) -> Dict[str, Any]:
    """从 LLM 输出解析 JSON（容忍 ```json 包装）。"""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split('\n')
        in_block = False
        json_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                if in_block:
                    break
                in_block = True
                continue
            if in_block:
                json_lines.append(line)
        raw = '\n'.join(json_lines).strip()
    return json.loads(raw)


def compute_total(scores: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """从 7 维子项分算总分（v3：100 分制，方案 B 权重）。"""
    weights = {
        "trigger_design": {"显式触发词": 5, "隐式意图": 5, "核心信号": 4, "pushy 句式": 1, "负触发": 3, "技能互斥": 2},
        "process_discipline": {"步骤化管线": 3, "每步有产出": 3, "失败分级": 6, "禁止路径": 2, "打扰预算": 1},
        "structural_sanity": {"SKILL.md <500 行": 5, "references 拆解": 8, "scripts 确定性": 7},
        "output_contract": {"结构化中间表示": 5, "可校验": 3, "可重渲染": 3, "防漂移": 4},
        "guardrails": {"降级路径+痕迹": 4, "用户语言防火墙": 3, "内容合规": 3},
        "config_boundary": {"个人邮箱/账号": 2, "项目/客户名": 1, "路径魔法": 1, "模型/工具依赖": 1},
        "evaluation_closure": {"evals/ 目录": 4, "rubrics": 4, "with/without": 4, "回归基线": 3},
    }
    dim_max = {
        "trigger_design": 20, "process_discipline": 15, "structural_sanity": 20,
        "output_contract": 15, "guardrails": 10, "config_boundary": 5, "evaluation_closure": 15,
    }

    dim_scores = {}
    total = 0
    for dim, items in scores.items():
        w = weights.get(dim, {})
        s = sum(v["score"] * w.get(k, 0) for k, v in items.items())
        dim_scores[dim] = s
        total += s

    if total >= 80:
        tier = "🟢优秀"
    elif total >= 60:
        tier = "🟡良好"
    else:
        tier = "🔴不合格"

    return {
        "total": total,
        "max": 100,
        "tier": tier,
        "dim_scores": dim_scores,
        "dim_max": dim_max,
    }


def main():
    parser = argparse.ArgumentParser(description="skillpingjia LLM-as-judge 评分（调用方注入模式）")
    parser.add_argument("bundle", help="score.py 输出的素材包 JSON 路径，或 - 从 stdin")
    parser.add_argument("--prompt-only", action="store_true",
                        help="只输出评分 prompt 到 stdout（由调用方调 LLM 作答）")
    parser.add_argument("--reply", help="LLM 回复文件路径（解析并算分）")
    args = parser.parse_args()

    # 加载素材包
    if args.bundle == "-":
        bundle = json.load(sys.stdin)
    else:
        bundle = json.load(open(args.bundle))

    # 构造 prompt
    prompt = build_prompt(bundle)

    if args.prompt_only:
        # 调用方注入模式：只给 prompt
        print(prompt)
        return

    if not args.reply:
        print("用法: python3 llm_score.py <bundle.json> --prompt-only   # 生成 prompt",
              file=sys.stderr)
        print("      python3 llm_score.py <bundle.json> --reply <file>  # 解析回复算分",
              file=sys.stderr)
        print("LLM 调用由调用方注入（Agent 用自己的模型通道 / 任意模型作答），脚本不直连任何端点。",
              file=sys.stderr)
        sys.exit(2)

    # 读取 LLM 回复
    raw = Path(args.reply).read_text(encoding="utf-8")

    # 解析
    try:
        scores = parse_llm_output(raw)
    except json.JSONDecodeError as e:
        print(f"✗ LLM 回复不是合法 JSON: {e}", file=sys.stderr)
        print("回复前 500 字符:", file=sys.stderr)
        print(raw[:500], file=sys.stderr)
        sys.exit(1)

    # 结构校验：每个子项必须是 {"score": 0|0.5|1, "evidence": "..."} 格式
    for dim, items in scores.items():
        if not isinstance(items, dict):
            print(f"✗ 维度 {dim} 应为对象，实际 {type(items).__name__}", file=sys.stderr)
            sys.exit(1)
        for k, v in items.items():
            if not isinstance(v, dict) or "score" not in v:
                print(f"✗ 子项 {dim}.{k} 应为 {{\"score\": 0|0.5|1, \"evidence\": \"...\"}}，实际 {v!r}", file=sys.stderr)
                sys.exit(1)

    # 算总分
    summary = compute_total(scores)

    result = {
        "evaluator": "caller-injected",
        "score": summary,
        "items": scores,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

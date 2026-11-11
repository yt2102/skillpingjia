"""
skillpingjia 回归测试（v3：真实断言，不再 mock）

用法：
    python3 regression.py

跑 evals/ 目录下所有用例，对每个用例：
  1. 调 score.py 采集素材包
  2. 断言硬门槛 H1-H4 与 input.json 的 expected_score.hard_gates 一致
  3. 断言 rule_scores.structural_sanity / evaluation_closure ≥ 预期下限
  4. 断言 skill_md_lines（如提供）
输出 PASS/FAIL，退出码 0/1。
"""
import json
import subprocess
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).parent.parent / "evals"
SKILL_DIR = Path(__file__).parent.parent


def score_skill(target: Path) -> dict:
    """调 score.py 解析素材包。"""
    result = subprocess.run(
        ["python3", str(SKILL_DIR / "scripts" / "score.py"), str(target)],
        capture_output=True, text=True, timeout=15,
        env={"SKILLPINGJIA_DRYRUN": "0"}  # 防递归：内层 score.py 不再跑 runner
    )
    if result.returncode != 0:
        return {"error": result.stderr[:300]}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"score.py 输出非 JSON: {e}"}


def run_case(case_dir: Path) -> tuple:
    """跑一个用例，返回 (case_name, status, msg)。"""
    spec = json.loads((case_dir / "input.json").read_text())
    # 可移植性：target_path 支持相对路径（相对 skill 根目录解析），不绑定机器
    raw_target = spec["target_path"]
    target = Path(raw_target)
    if not target.is_absolute():
        target = (SKILL_DIR / raw_target).resolve()
    if not target.exists():
        # 自动构建 synthetic fixture
        if "frontmatter" in spec:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(spec["frontmatter"] + "\n" + spec.get("body", ""))
        elif "full_content" in spec:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(spec["full_content"])
        else:
            return case_dir.name, "FAIL", f"target_path 不存在: {target}"

    bundle = score_skill(target)
    if "error" in bundle:
        return case_dir.name, "FAIL", bundle["error"]

    expected = spec.get("expected_score", {})

    # 1. 硬门槛断言
    for gate, expected_pass in expected.get("hard_gates", {}).items():
        actual = bundle.get("hard_gates", {}).get(gate)
        if actual != expected_pass:
            return case_dir.name, "FAIL", f"{gate} 期望 {expected_pass} 实际 {actual}"

    # 2. 行数断言
    if "skill_md_lines" in expected:
        actual = bundle.get("skill_md_lines")
        if actual != expected["skill_md_lines"]:
            return case_dir.name, "FAIL", f"行数 期望 {expected['skill_md_lines']} 实际 {actual}"

    # 3. 结构合理性下限
    if "structural_sanity_min" in expected:
        actual = bundle.get("rule_scores", {}).get("structural_sanity", {}).get("score", 0)
        if actual < expected["structural_sanity_min"]:
            return case_dir.name, "FAIL", f"结构合理性 {actual} < {expected['structural_sanity_min']}"

    # 4. 评估闭环下限（v3: max 15）
    if "evaluation_closure_min" in expected:
        actual = bundle.get("rule_scores", {}).get("evaluation_closure", {}).get("score", 0)
        if actual < expected["evaluation_closure_min"]:
            return case_dir.name, "FAIL", f"评估闭环 {actual} < {expected['evaluation_closure_min']}"

    return case_dir.name, "PASS", "all assertions (real)"


def main():
    cases_dir = EVAL_DIR / "cases"
    if not cases_dir.exists():
        print(f"evals/cases 目录不存在: {cases_dir}")
        sys.exit(1)

    print(f"skillpingjia regression · v3 (真实断言)")
    print("=" * 50)

    results = []
    for case_dir in sorted(cases_dir.iterdir()):
        if not case_dir.is_dir():
            continue
        name, status, msg = run_case(case_dir)
        results.append((name, status, msg))
        mark = "✓" if status == "PASS" else "✗"
        print(f"  {mark} {name:10} {status}  {msg}")

    passed = sum(1 for _, s, _ in results if s == "PASS")
    print(f"\n--- {passed}/{len(results)} PASS ---")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()

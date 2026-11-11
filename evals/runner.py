"""
skillpingjia evals runner

跑 3 个用例：
- normal: 拿 pingjia 自己解析（应能自评）
- negative: 无 frontmatter（应 H1 判 ❌）
- boundary: 500 行整 SKILL.md（H2 应判 ❌）

输出 pytest 风格 PASS/FAIL。
"""
import json
import subprocess
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).parent
SKILL_DIR = EVAL_DIR.parent


def run_case(name: str, case_dir: Path, expected: dict) -> tuple:
    """跑一个用例，返回 (status, msg)。"""
    spec = json.loads((case_dir / "input.json").read_text())

    # 可移植性：target_path 支持相对路径（相对 skill 根解析），不绑定机器
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
            return "FAIL", f"target_path 不存在: {target}"

    result = subprocess.run(
        ["python3", str(SKILL_DIR / "scripts" / "score.py"), str(target)],
        capture_output=True, text=True, timeout=10,
        env={"SKILLPINGJIA_DRYRUN": "0"}  # 防递归：内层 score.py 不再跑 runner
    )
    if result.returncode != 0:
        return "FAIL", f"score.py 失败: {result.stderr[:200]}"

    bundle = json.loads(result.stdout)

    # 断言硬门槛
    for gate, expected_pass in expected.get("hard_gates", {}).items():
        actual = bundle.get("hard_gates", {}).get(gate)
        if actual != expected_pass:
            return "FAIL", f"{gate} 期望 {expected_pass} 实际 {actual}"

    # 断言行数
    if "skill_md_lines" in expected:
        actual = bundle.get("skill_md_lines")
        if actual != expected["skill_md_lines"]:
            return "FAIL", f"行数 期望 {expected['skill_md_lines']} 实际 {actual}"

    # 断言文件名
    if "files_must_contain" in expected:
        for f in expected["files_must_contain"]:
            if f not in bundle.get("files", []):
                return "FAIL", f"missing file: {f}"

    # 断言文件名不存在
    if "files_must_not_contain" in expected:
        for f in expected["files_must_not_contain"]:
            if f in bundle.get("files", []):
                return "FAIL", f"unexpected file: {f}"

    # 断言 expected_score（真实跑分）
    expected_score = expected.get("expected_score", {})
    if expected_score:
        # 硬门槛分数
        if "hard_gates" in expected_score:
            for gate, expected_pass in expected_score["hard_gates"].items():
                actual = bundle.get("hard_gates", {}).get(gate)
                if actual != expected_pass:
                    return "FAIL", f"{gate} 期望 {expected_pass} 实际 {actual}"
        # 结构合理性下限
        if "structural_sanity_min" in expected_score:
            actual = bundle.get("rule_scores", {}).get("structural_sanity", {}).get("score", 0)
            if actual < expected_score["structural_sanity_min"]:
                return "FAIL", f"结构合理性 {actual} < {expected_score['structural_sanity_min']}"
        # 评估闭环下限
        if "evaluation_closure_min" in expected_score:
            actual = bundle.get("rule_scores", {}).get("evaluation_closure", {}).get("score", 0)
            if actual < expected_score["evaluation_closure_min"]:
                return "FAIL", f"评估闭环 {actual} < {expected_score['evaluation_closure_min']}"

    # 断言 v3.2 素材（normal 用例：version_info / executable_evidence / element_closure / route_evidence）
    if expected.get("require_v32_material"):
        for key in ["version_info", "executable_evidence", "element_closure", "route_evidence"]:
            if key not in bundle:
                return "FAIL", f"v3.2 素材缺失: {key}"
        if "evaluation_effectiveness" not in bundle.get("rule_scores", {}):
            return "FAIL", "v3.2 素材缺失: rule_scores.evaluation_effectiveness"

    # v3.4：normal 用例自检新素材键存在（不判 present，pingjia 自己不是套件包）
    if expected.get("require_v34_material") and "package_engineering" not in bundle:
        return "FAIL", "v3.4 素材缺失: package_engineering"

    # 断言 v3.3 P0-1：ir_closure.gaps 命中（contract_drift fixture / v3.15 回归）
    # 只认 status="drift"（internal_only 是内部临时类型，按规格书不算缺口）
    if "expect_ir_closure_gaps" in expected:
        gaps = bundle.get("ir_closure", {}).get("evidence", {}).get("gaps", [])
        actual_drift_types = {g["type"] for g in gaps if g.get("status") == "drift"}
        for t in expected["expect_ir_closure_gaps"]:
            if t not in actual_drift_types:
                return "FAIL", f"ir_closure 期望抓出 drift={t}，实际 gaps={actual_drift_types}"

    # 断言 v3.3 P1-1：fallback_branches.uncovered 命中（blind_fallback fixture）
    if "expect_fallback_uncovered" in expected:
        uncovered = bundle.get("fallback_branches", {}).get("evidence", {}).get("uncovered", [])
        for t in expected["expect_fallback_uncovered"]:
            if t not in uncovered:
                return "FAIL", f"fallback_uncovered 期望含 {t}，实际={uncovered}"

    # v3.3.1 断言：CORE-003/FAIL-002 联合 —— warn_no_propagation ≥ 阈值即命中
    if "expect_warn_no_propagation_min" in expected:
        wnp = (
            bundle.get("silent_failures", {})
                  .get("evidence", {})
                  .get("warn_no_propagation", 0)
        )
        threshold = expected["expect_warn_no_propagation_min"]
        if wnp < threshold:
            return "FAIL", f"warn_no_propagation={wnp} < 阈值 {threshold}（SK-FAIL-002 未命中）"

    # v3.4 断言：package_engineering 五件套线索命中（kit_engineering fixture）
    if "expect_package_engineering" in expected:
        pe = bundle.get("package_engineering", {}).get("evidence", {})
        for key in expected["expect_package_engineering"]:
            if not pe.get(key, {}).get("present"):
                return "FAIL", f"package_engineering 期望命中 {key}，实际 summary={bundle.get('package_engineering', {}).get('summary')}"

    return "PASS", "all assertions (real)"


def main():
    cases = [
        ("normal", EVAL_DIR / "cases" / "normal", {
            "files_must_contain": ["SKILL.md", "references/scoring_rubrics.md"],
            "require_v32_material": True,
            "require_v34_material": True,
        }),
        ("negative", EVAL_DIR / "cases" / "negative", {
            "skill_md_lines": 1,
        }),
        ("boundary", EVAL_DIR / "cases" / "boundary", {}),
        ("contract_drift", EVAL_DIR / "cases" / "contract_drift", {
            "expect_ir_closure_gaps": ["heading_p"],
        }),
        ("blind_fallback", EVAL_DIR / "cases" / "blind_fallback", {
            "expect_fallback_uncovered": ["h1_present"],
        }),
        ("regression_jishufangan_v315", EVAL_DIR / "cases" / "regression_jishufangan_v315", {
            "expect_ir_closure_gaps": ["heading"],
            "expect_fallback_uncovered": ["heading"],
            # v3.3.1：CORE-003/FAIL-002 联合断言——7 个 pass 全带 warning 但全部未传播状态
            "expect_warn_no_propagation_min": 5,
        }),
        ("kit_engineering", EVAL_DIR / "cases" / "kit_engineering", {
            # v3.4：NVIDIA 五件套包形态 fixture——六项线索全命中
            "expect_package_engineering": [
                "contract_asset", "eval_report", "disclosure_card",
                "signature", "kit_routing", "live_source_principle",
            ],
        }),
    ]

    print(f"skillpingjia evals · runner")
    print("=" * 50)

    results = []
    for name, case_dir, expected in cases:
        status, msg = run_case(name, case_dir, expected)
        results.append((name, status, msg))
        mark = "✓" if status == "PASS" else "✗"
        print(f"  {mark} {name:10} {status}  {msg}")

    passed = sum(1 for _, s, _ in results if s == "PASS")
    print(f"\n--- {passed}/{len(results)} PASS ---")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()

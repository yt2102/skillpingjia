"""
jishufangan evals runner — 评测闭环执行器

按 skillpingjia v3.1 评审报告 P1 修复（评估闭环无执行器）。

功能：
1. 遍历 evals/cases/*/input.json
2. 对每个 case 生成 docx（with_skill + without_skill 双跑）
3. 记录 with/without 对比结果到 evals/{with_skill,without_skill}/<case>.json
4. 与 evals/baseline.json 对比，偏差 >5 触发复盘提醒

用法：
    python3 evals/runner.py                  # 跑全部 case
    python3 evals/runner.py simple_normal    # 跑指定 case
    python3 evals/runner.py --with-skill     # 只跑 with_skill
    python3 evals/runner.py --diff-baseline  # 对比 baseline
"""

import sys
import os
import json
import time
import argparse
import traceback
from datetime import datetime
from pathlib import Path

# 路径推导 + 一次性注入 sys.path（仅 SCRIPTS_DIR，SKILL_ROOT 不需要）
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# 模块顶层一次性 import（不再每次 run_case 重新 import）
import jishufangan_simple
import libjishu
from docx import Document


# ═══════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════

def _ok_result(path):
    """成功的 result dict"""
    return {
        "ok": True,
        "output": path,
        "size_kb": round(os.path.getsize(path) / 1024, 1),
    }


def _error_result(e):
    """失败的 result dict"""
    return {
        "ok": False,
        "error": str(e),
        "traceback": traceback.format_exc(),
    }


def _status_icon(result):
    return "✅" if result["ok"] else "❌"


def _timestamp():
    return int(time.time() * 1000)  # 毫秒级，避免同 case 内冲突


# ═══════════════════════════════════════════════════════════
#  Case loading
# ═══════════════════════════════════════════════════════════

def load_case(case_name):
    """加载 evals/cases/<case_name>/input.json"""
    case_path = SCRIPT_DIR / "cases" / case_name / "input.json"
    try:
        with open(case_path) as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Case 不存在: {case_path}") from e


def list_cases():
    """列出所有可用 case"""
    cases_dir = SCRIPT_DIR / "cases"
    if not cases_dir.exists():
        return []
    return sorted([
        d.name for d in cases_dir.iterdir()
        if d.is_dir() and (d / "input.json").exists()
    ])


# ═══════════════════════════════════════════════════════════
#  Generation functions
# ═══════════════════════════════════════════════════════════

def _fixture_to_body(fixture):
    """fixture['chapters'] → structure body 列表"""
    body = []
    for ch_title, sections in (fixture.get("chapters") or []):
        body.append(("heading", 1, ch_title))
        for sec in sections:
            body.append(("heading", 2, sec))
            body.append(("body", "（测试内容）"))
    return body


def run_with_skill(case_name, case):
    """根据 case 类型走对应 skill API

    路由：simple_ 开头 → jishufangan_simple，其他 → libjishu 标准版
    """
    is_simple = case_name.startswith("simple_")
    fixture = case.get("fixture", {})
    out = f"/tmp/jishufangan_runner_{_timestamp()}.docx"

    try:
        if is_simple:
            # v3.5 简版：不需要 org/date（无封面）
            jishufangan_simple.convert_to_simple_format(
                title=fixture.get("title", "测试方案"),
                chapters=fixture.get("chapters"),
                output_path=out,
            )
        else:
            structure = {
                "title": fixture.get("title", "测试方案"),
                "org": fixture.get("org") or libjishu._default_org(),
                "date": fixture.get("date") or libjishu._default_date(),
                "body": _fixture_to_body(fixture),
            }
            doc, _ = libjishu.create_document()
            libjishu.add_cover(
                doc, structure["title"], org=structure["org"], date=structure["date"]
            )
            libjishu.generate_from_structure(doc, structure)
            libjishu.save_docx(doc, out)

        return _ok_result(out)
    except Exception as e:
        return _error_result(e)


def run_without_skill(case):
    """裸 python-docx，模拟"不用 skill"的对照"""
    fixture = case.get("fixture", {})
    out = f"/tmp/jishufangan_runner_no_skill_{_timestamp()}.docx"

    try:
        doc = Document()
        doc.add_heading(fixture.get("title", "测试方案"), 0)
        doc.add_paragraph(f"编制单位：{fixture.get('org', libjishu._default_org())}")
        doc.add_paragraph(f"编制日期：{fixture.get('date', libjishu._default_date())}")
        for ch_title, sections in (fixture.get("chapters") or []):
            doc.add_heading(ch_title, 1)
            for sec in sections:
                doc.add_heading(sec, 2)
                doc.add_paragraph("（裸 docx 内容，无政务格式）")
        doc.save(out)
        return _ok_result(out)
    except Exception as e:
        return _error_result(e)


# ═══════════════════════════════════════════════════════════
#  Result persistence
# ═══════════════════════════════════════════════════════════

def save_result(skill_mode, case_name, result, case):
    """保存单次跑结果到 evals/{skill_mode}/<case_name>.json"""
    out_dir = SCRIPT_DIR / skill_mode
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{case_name}.json"

    record = {
        "case_name": case_name,
        "skill_mode": skill_mode,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "case_description": case.get("description", ""),
        "scenario": case.get("scenario", ""),
        "result": result,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    return out_path


# ═══════════════════════════════════════════════════════════
#  Baseline diff
# ═══════════════════════════════════════════════════════════

def load_baseline():
    try:
        with open(SCRIPT_DIR / "baseline.json") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def diff_baseline(current_total, baseline, threshold=5):
    """对比当前总分与 baseline，偏差 >threshold 触发复盘"""
    if not baseline:
        return {"status": "no_baseline", "message": "baseline.json 不存在"}

    baseline_total = baseline.get("total_score", 0)
    deviation = current_total - baseline_total

    if abs(deviation) > threshold:
        return {
            "status": "trigger_replay",
            "deviation": deviation,
            "message": (
                f"偏差 {deviation:+d} > {threshold} 阈值，"
                f"触发强制复盘（baseline={baseline_total}, current={current_total}）"
            ),
        }
    return {
        "status": "ok",
        "deviation": deviation,
        "message": f"偏差 {deviation:+d} 在容差内",
    }


# ═══════════════════════════════════════════════════════════
#  Runner
# ═══════════════════════════════════════════════════════════

# mode → 生成函数映射表（替代 if/else 分支）
MODE_GENERATORS = {
    "with_skill": run_with_skill,
    "without_skill": lambda case_name, case: run_without_skill(case),
}


def run_case(case_name, modes):
    """跑单个 case 的指定 mode 列表"""
    case = load_case(case_name)
    print(f"\n=== Case: {case_name} ===")
    print(f"  Description: {case.get('description', '')}")

    results = {}
    for mode, generator in MODE_GENERATORS.items():
        if mode not in modes:
            continue
        print(f"  → {mode}:", end=" ")
        result = generator(case_name, case)
        path = save_result(mode, case_name, result, case)
        print(f"{_status_icon(result)} ({result.get('size_kb', '?')} KB) → {path}")
        results[mode] = result
    return results


def cleanup_tmp_files():
    """清理 /tmp/jishufangan_runner*.docx"""
    for f in Path("/tmp").glob("jishufangan_runner*.docx"):
        f.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="jishufangan evals runner")
    parser.add_argument("cases", nargs="*", help="指定 case 名（不传则跑全部）")
    parser.add_argument(
        "--with-skill", dest="with_skill", action="store_true", default=True,
        help="跑 with_skill（默认 True）",
    )
    parser.add_argument(
        "--without-skill", dest="without_skill", action="store_true", default=True,
        help="跑 without_skill（默认 True）",
    )
    parser.add_argument(
        "--no-with-skill", action="store_false", dest="with_skill",
    )
    parser.add_argument(
        "--no-without-skill", action="store_false", dest="without_skill",
    )
    parser.add_argument(
        "--diff-baseline", action="store_true", help="对比 baseline.json",
    )
    parser.add_argument(
        "--threshold", type=int, default=5, help="baseline 偏差阈值（默认 5）",
    )
    parser.add_argument(
        "--keep-tmp", action="store_true", help="不清理 /tmp 中的输出文件",
    )
    args = parser.parse_args()

    cases = args.cases or list_cases()
    if not cases:
        print("❌ 没有可用 case")
        return 1

    modes = [m for m, enabled in [("with_skill", args.with_skill),
                                    ("without_skill", args.without_skill)] if enabled]

    print(f"🚀 jishufangan evals runner")
    print(f"   跑 {len(cases)} 个 case: {', '.join(cases)}")
    print(f"   modes: {', '.join(modes) or '(空)'}")

    start = time.time()
    failed = 0
    all_results = {}
    for case_name in cases:
        try:
            results = run_case(case_name, modes)
            all_results[case_name] = results
            failed += sum(1 for r in results.values() if not r["ok"])
        except Exception as e:
            print(f"❌ Case {case_name} 异常: {e}")
            traceback.print_exc()
            failed += 1

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"📊 评测完成：{len(cases)} case(s), {failed} 失败, 耗时 {elapsed:.1f}s")

    if args.diff_baseline and all_results:
        baseline = load_baseline()
        estimated = 100 - (failed * 100 // max(len(cases), 1))
        current_status = baseline.get("current_score") if baseline else None

        print(f"\n📋 Baseline 对比:")
        print(f"   估算总分：{estimated}（注：实际需 pingjia 评分）")
        if current_status == "pending":
            print(f"   Baseline 状态：{current_status}（等待 skillpingjia 重评）")
            print(f"   跳过偏差对比（待 baseline.total_score 更新）")
        else:
            diff = diff_baseline(estimated, baseline, args.threshold)
            print(f"   {diff['message']}")

    if not args.keep_tmp:
        cleanup_tmp_files()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
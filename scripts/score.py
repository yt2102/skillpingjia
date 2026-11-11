"""
skillpingjia 评分脚本（LLM-as-judge 副驾）

用法：
    python3 score.py <target_skill_path>

输出：JSON 格式评分结果，便于 evals diff。
不是完整 LLM-as-judge（评分细则由 LLM 按 SKILL.md 评估），只负责：
  1. 采集目标 skill 文件 + 目录结构
  2. 解析 frontmatter（name/description）
  3. 校验硬门槛 H1/H2/H3/H4
  4. 输出 LLM-as-judge 需要的"评估素材包"（JSON）
  5. （可选）格式化报告

v3.2（2026-08-22）新增 5 项检查：
  - version_info       : 评分对象版本声明（git commit / dirty / mtime）——防评错副本
  - executable_evidence: 执行验证 dry-run（真实跑目标 evals/runner.py + 占位符扫描 + 示例入口核对）
  - element_closure    : structure 元素类型闭合性（SKILL.md 承诺 vs 渲染入口实际处理）
  - route_evidence     : 内部路由与 description 覆盖一致性线索
  - evaluation_effectiveness: baseline 偏差标记 + runner 可跑 + 豁免声明检测
"""
import json
import os
import re
import subprocess
import sys
import importlib
from pathlib import Path
from typing import Dict, Any, Literal


# v3.3.1 统一判定常量（消除 stringly-typed 风险）
Verdict = Literal["PASS", "WARN", "FAIL", "INCONCLUSIVE"]
PASS: Verdict = "PASS"
WARN: Verdict = "WARN"
FAIL: Verdict = "FAIL"
INCONCLUSIVE: Verdict = "INCONCLUSIVE"


# 元素能力：SKILL.md 提及的 API 函数 → structure 元素类型
API_ELEMENT_MAP = {
    "add_heading": "heading",
    "add_body": "body",
    "add_numbered_list": "list_numbered",
    "add_bullet_list": "list_bullet",
    "add_table": "table",
    "add_image": "image",
}


# v3.3.1：统一防递归 guard（runner 调用 score.py 时设 SKILLPINGJIA_DRYRUN=0，
# 内层 score.py 不应再起子进程跑目标 skill，否则无限递归）
def _is_reentrant_dryrun() -> bool:
    """检测是否处于 runner→score.py 嵌套调用上下文。"""
    return os.environ.get("SKILLPINGJIA_DRYRUN") == "0"
# 占位正文模式（示例产出占位符 → 文档示例不可用）
# 注意：避免“占位”等宽泛词（注释/文档说明会误命中）；检测时排除本文件常量定义自身
PLACEHOLDER_PATTERNS = ["内容待撰写", "待撰写", "（内容待", "TODO", "lorem", "Lorem"]
# 豁免声明模式（验证器存在“预期 CRITICAL/设计性偏离”豁免）
EXEMPTION_PATTERNS = ["设计性偏离", "预期 CRITICAL", "不视为质量缺陷", "预期内", "豁免", "不视为缺陷", "已知误报"]
# 内部路由章节标题特征（只认章节标题格式，表格/正文提及不算）
ROUTE_SECTION_PATTERN = r"^(?:#{1,6}\s+|\*\*)[^\n]*(?:路由|决策树)"
# 路由分支词形态：提取完整词（含后缀），如「简版」「简要方案」「标准版」
# 前缀限 1-4 字符 + 负向后顾（分支词前不能是中文/字母/数字）——防止从句子中间切片
# （如「政务格式排版」不会切出「务格式排版」）；后缀去掉「档」（「归档」误配）
ROUTE_BRANCH_PATTERN = re.compile(r"(?<![\u4e00-\u9fa5A-Za-z0-9])[\u4e00-\u9fa5A-Za-z0-9]{1,4}(?:版|模式|路径|方案)")
# 非分支词的「X版/X模式」误匹配过滤（排版/文版等）
ROUTE_STOPWORDS = {"排版", "文版", "归", "的", "了", "中", "后", "前", "该", "本", "此", "按", "被", "把", "在"}
# 元素闭合性扫描用正则（模块级常量：避免函数体内字面模式自匹配）
ELEMENT_BRANCH_RE = re.compile(r"(?:typ|el|item|elem|element)\s*==\s*'([a-z_]+)'")
ELEMENT_INDEX_RE = re.compile(r"(?:body\[i\]\[0\]|e\[0\]|row\[0\])\s*==\s*'([a-z_]+)'")
# 通用路由分支兜底词（动态提取失败时用；双语覆盖）
ROUTE_FALLBACK_WORDS = [
    "简版", "简要", "快速", "标准", "完整", "详细", "基础", "高级", "专业", "默认",
    "simple", "basic", "standard", "full", "advanced", "pro", "lite", "quick",
]


def _is_noise(p: Path) -> bool:
    """v3.4.1：噪音文件统一过滤——备份/字节码/版本库目录。
    这类文件不应参与 files 清单、脚本计数、证据采集（陈旧备份会污染判定）。"""
    parts = p.parts
    if "__pycache__" in parts or ".git" in parts or ".hermes" in parts:
        return True
    name = p.name
    return ".bak" in name or name.endswith((".pyc", ".pyo", ".tmp", "~"))


def _get_py_files(target: Path) -> list:
    """收集目标 skill 的 .py 文件（优先 scripts/，无则根目录）。"""
    scripts_dir = target / "scripts" if target.is_dir() else None
    if scripts_dir and scripts_dir.is_dir():
        return [f for f in scripts_dir.rglob("*.py") if not _is_noise(f)]
    if target.is_dir():
        return [f for f in target.glob("*.py") if not _is_noise(f)]
    return []


def collect_skill(target: Path) -> Dict[str, Any]:
    """目录模式：找 SKILL.md 走完整采集。"""
    skill_md = target / "SKILL.md"
    if not skill_md.exists():
        return {"error": f"SKILL.md not found in {target}"}
    return _collect_from_content(target, skill_md, skill_md.read_text(encoding="utf-8"))


def _collect_from_content(target: Path, skill_md: Path, content: str) -> Dict[str, Any]:
    """从已读 SKILL.md 内容采集（支持 fixture 单文件模式）。"""
    lines = content.splitlines()

    # 1. 解析 frontmatter
    fm = {}
    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        try:
            import yaml
            fm = yaml.safe_load(fm_match.group(1)) or {}
        except ImportError:
            # 简单解析
            for line in fm_match.group(1).split('\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    fm[k.strip()] = v.strip()

    # 2. 硬门槛校验
    hardlines = {
        "H1": bool(fm.get("name") and fm.get("description")),
        "H2": len(lines) < 500,
        "H3": bool(fm.get("description")) and len(fm.get("description", "")) <= 1024,
        "H4": None,  # LLM 评
    }

    # 3. 目录结构
    structure = {
        "SKILL.md": skill_md.exists(),
        "references/": (target / "references").is_dir(),
        "scripts/": (target / "scripts").is_dir(),
        "assets/": (target / "assets").is_dir(),
        "evals/": (target / "evals").is_dir(),
        "examples/": (target / "examples").is_dir(),
    }

    # 4. 文件树（v3.4.1：过滤备份/字节码噪音，防陈旧副本污染判定）
    files = []
    for f in sorted(target.rglob("*")):
        if f.is_file() and not _is_noise(f):
            rel = f.relative_to(target)
            files.append(str(rel))

    # H4 自动校验（替换 v1 的 None）
    h4_result = _eval_h4(target, content, files)
    hardlines["H4"] = h4_result["pass"]

    # 结构合理性 + 评估闭环 规则能判部分
    rule_scores = _score_structure_and_eval(target, files)

    # 输出契约线索采集（v3.1：线索非断言，judge 自行判断）
    contract_evidence = _collect_contract_evidence(target, content, files)

    # v3.2 新增：版本声明 / 执行验证 / 元素闭合性 / 路由线索
    version_info = _collect_version(target)
    executable_evidence = _eval_executable(target, content)
    element_closure = _collect_element_closure(target, content)
    route_evidence = _collect_route_evidence(content, fm.get("description", ""))
    # 评估闭环有效性（依赖 executable 结果，放在 rule_scores 之外补充）
    rule_scores["evaluation_effectiveness"] = _eval_closure_effectiveness(
        target, content, executable_evidence, rule_scores
    )

    # v3.3 新增：5 类实战盲区判据
    ir_closure = _collect_ir_closure(target)
    silent_failures = _collect_silent_failures(target)
    producer_types = set(ir_closure.get("evidence", {}).get("producers", {}).keys())
    fallback_branches = _collect_fallback_branches(target, producer_types)
    docstring_api = _collect_docstring_api_mismatch(target, content)
    # v3.3.1 新增：runtime+test 标杆 checker
    fallback_shadowing = _collect_fallback_shadowing(target, content)
    real_path_regression = _collect_real_path_regression(target, content)
    # v3.4 新增：包工程五件套线索（外部对标 NVIDIA auto-ontology skill 套件）
    package_engineering = _collect_package_engineering(target, content)

    return {
        "skill_name": fm.get("name", "unknown"),
        "skill_path": str(target),
        "skill_md_lines": len(lines),
        "skill_md_bytes": len(content),
        "frontmatter": {
            "name": fm.get("name"),
            "description": fm.get("description"),
            "description_chars": len(fm.get("description", "")),
        },
        "hard_gates": hardlines,
        "hard_gates_detail": {
            "H4": {
                "pass": h4_result["pass"],
                "reasons": h4_result["reasons"],
            },
        },
        "structure": structure,
        "files": files,
        "rule_scores": rule_scores,
        "contract_evidence": contract_evidence,
        "version_info": version_info,
        "executable_evidence": executable_evidence,
        "element_closure": element_closure,
        "route_evidence": route_evidence,
        # v3.3 新增 5 类证据
        "ir_closure": ir_closure,
        "silent_failures": silent_failures,
        "fallback_branches": fallback_branches,
        "docstring_api": docstring_api,
        # v3.3.1 新增 2 类 runtime+test 证据
        "fallback_shadowing": fallback_shadowing,
        "real_path_regression": real_path_regression,
        # v3.4 新增：包工程线索
        "package_engineering": package_engineering,
        "skill_md_content": content,  # LLM 评分用
    }


# ============================================================
# v3.2 · P0 版本声明
# ============================================================

def _collect_version(target: Path) -> Dict[str, Any]:
    """评分对象版本声明：git commit / branch / dirty / mtime。防评错副本。"""
    info = {
        "skill_path": str(target),
        "mtime": None,
        "git_commit": None,
        "git_branch": None,
        "git_dirty": False,
    }
    try:
        info["mtime"] = target.stat().st_mtime
    except Exception:
        pass
    for args, key in [
        (["rev-parse", "--short", "HEAD"], "git_commit"),
        (["branch", "--show-current"], "git_branch"),
    ]:
        try:
            r = subprocess.run(
                ["git", "-C", str(target), *args],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                info[key] = r.stdout.strip()
        except Exception:
            pass
    try:
        r = subprocess.run(
            ["git", "-C", str(target), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            info["git_dirty"] = True
    except Exception:
        pass
    return info


# ============================================================
# v3.2 · P1 执行验证 dry-run
# ============================================================

def _eval_executable(target: Path, content: str) -> Dict[str, Any]:
    """
    执行验证（dry-run）：
      1. 真实跑目标 skill 的 evals/runner.py（若存在；SKILLPINGJIA_DRYRUN=0 时跳过，防递归）
      2. 扫描 scripts/*.py 占位正文模式（示例产出占位符 → 一键示例不可用）
      3. 提取 SKILL.md python 代码块中的 one-shot 入口函数，核对 scripts 中是否存在（死引用检测）
    示例代码不自动执行（防误跑外部脚本），只做入口识别 + 存在性核对。
    """
    result = {"runner": None, "placeholder_hits": [], "example_calls": [], "note": ""}

    # 1. 跑目标 skill 的 evals/runner.py
    runner = (target / "evals" / "runner.py") if target.is_dir() else None
    if runner and runner.exists():
        if _is_reentrant_dryrun():
            result["runner"] = {"exists": True, "skipped": True, "note": "dry-run 被禁用（防递归）"}
        else:
            try:
                r = subprocess.run(
                    ["python3", str(runner)],
                    capture_output=True, text=True, timeout=60,
                    cwd=str(target),
                )
                result["runner"] = {
                    "exists": True,
                    "exit_code": r.returncode,
                    "passed": r.returncode == 0,
                    "output_tail": r.stdout.strip().splitlines()[-5:] or [],
                    "stderr_tail": r.stderr.strip().splitlines()[-3:] or [],
                }
            except subprocess.TimeoutExpired:
                result["runner"] = {"exists": True, "exit_code": None, "passed": False, "timeout": True}
            except Exception as e:
                result["runner"] = {"exists": True, "exit_code": None, "passed": False, "error": str(e)}

    # 2. 占位正文扫描（排除本文件 PLACEHOLDER_PATTERNS 常量定义自命中）
    py_files = _get_py_files(target)
    for f in py_files:
        try:
            fc = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # 剔除常量定义块，防自匹配
        fc_scan = re.sub(
            r"PLACEHOLDER_PATTERNS\s*=\s*\[.*?\]", "", fc, flags=re.DOTALL
        )
        for pat in PLACEHOLDER_PATTERNS:
            if pat in fc_scan:
                rel = str(f.relative_to(target)) if target.is_dir() else str(f)
                result["placeholder_hits"].append(f"{rel} 含 '{pat}'")
                break

    # 3. SKILL.md python 代码块 → one-shot 入口识别 + scripts 存在性核对
    script_defs = set()
    for f in py_files:
        try:
            fc = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in re.finditer(r"^def\s+([a-zA-Z0-9_]+)\s*\(", fc, re.MULTILINE):
            script_defs.add(m.group(1))
    one_shot = re.compile(
        r"(convert_to_[a-zA-Z0-9_]+|generate_from_[a-zA-Z0-9_]+|build_[a-zA-Z0-9_]+"
        r"|create_[a-zA-Z0-9_]+|render_[a-zA-Z0-9_]+|save_[a-zA-Z0-9_]+|validate_[a-zA-Z0-9_]+)\s*\("
    )
    code_blocks = re.findall(r"```python\s*\n(.*?)\n```", content, re.DOTALL)
    seen = set()
    for i, block in enumerate(code_blocks):
        for m in one_shot.finditer(block):
            fn = m.group(1)
            if fn in seen:
                continue
            seen.add(fn)
            result["example_calls"].append({
                "function": fn,
                "exists_in_scripts": fn in script_defs,
                "block_index": i,
            })

    result["note"] = (
        "runner 为真实执行；示例代码仅识别入口函数并核对 scripts 存在性，不自动执行外部代码（防误跑）。"
        "placeholder_hits 非空 → judge 检查示例是否产出占位正文；example_calls 中 exists_in_scripts=False → 死引用。"
    )
    return result


# ============================================================
# v3.2 · P1 元素类型闭合性
# ============================================================

def _collect_element_closure(target: Path, content: str) -> Dict[str, Any]:
    """
    structure 元素类型闭合性（泛化版）：
      - skill_md_types：SKILL.md 承诺的元素类型（structure tuple 模式 + API 函数反推）
      - render_handled ：所有「具渲染入口特征」函数体实际处理的分支（按元素类型分支 / 调用元素 API）
      - unhandled      ：承诺了但渲染入口未处理 → 静默跳过风险（如 image）
    泛化要点：不依赖特定函数名（generate_from_structure 等），改为行为特征识别——
    任何函数体含 typ==分支 / body[i][0]==分支 / add_xxx 元素 API 调用即视为渲染入口。
    非文档生成类 skill（无元素类型承诺）→ skill_md_types 为空，自然跳过，零误报。
    """
    # 1. SKILL.md 承诺的元素类型
    md_types = set()
    for m in re.finditer(r"\('([a-z_]+)',", content):
        md_types.add(m.group(1))
    for api_fn, elem in API_ELEMENT_MAP.items():
        if api_fn in content:
            md_types.add(elem)

    # 2. 所有顶层函数中具「渲染入口特征」的（行为识别，不依赖函数名）
    handled = set()
    py_files = _get_py_files(target)
    for f in py_files:
        try:
            fc = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        lines = fc.splitlines()
        i = 0
        while i < len(lines):
            ln = lines[i]
            m_def = re.match(r"def\s+([a-zA-Z_]\w*)\s*\(", ln)
            if not m_def:
                i += 1
                continue
            # 函数体：到下一个「行首无缩进的顶层 def/class」为止（嵌套 def 不算边界）
            body_lines = []
            j = i + 1
            while j < len(lines):
                if re.match(r"(?:def|class)\s+", lines[j]):
                    break
                body_lines.append(lines[j])
                j += 1
            body = "\n".join(body_lines)
            # 渲染入口特征：typ==分支 / body[i][0]==分支 / add_xxx 元素 API 调用
            is_render_entry = False
            for mm in ELEMENT_BRANCH_RE.finditer(body):
                handled.add(mm.group(1))
                is_render_entry = True
            for mm in ELEMENT_INDEX_RE.finditer(body):
                handled.add(mm.group(1))
                is_render_entry = True
            for api_fn, elem in API_ELEMENT_MAP.items():
                if re.search(r"\b" + re.escape(api_fn) + r"\s*\(", body):
                    handled.add(elem)
                    is_render_entry = True
            # 函数名含 render/generate/build/convert 等渲染语义 + 体内调用元素 API → 补记
            if not is_render_entry and re.search(
                r"def\s+(?:render|generate|build|convert|compose|emit|dump|write)[a-z0-9_]*", ln
            ):
                for api_fn, elem in API_ELEMENT_MAP.items():
                    if re.search(r"\b" + re.escape(api_fn) + r"\s*\(", body):
                        handled.add(elem)
            i = j

    unhandled = sorted(md_types - handled)
    return {
        "skill_md_types": sorted(md_types),
        "render_handled": sorted(handled),
        "unhandled": unhandled,
        "note": "unhandled 非空 → SKILL.md 承诺的元素类型渲染入口未处理（静默跳过风险），judge 确认后输出契约降档",
    }


# ============================================================
# v3.2 · P2 路由覆盖线索
# ============================================================

def _collect_route_evidence(content: str, description: str) -> Dict[str, Any]:
    """
    内部路由覆盖一致性线索（泛化版）：
      若 SKILL.md **正文**（非 `>` 引用块/变更摘要）含「路由/决策树」章节，
      动态提取分支词（X版/X模式/X路径/X方案/X档 + 通用兜底词），与 description 比对。
    泛化要点：不依赖固定词表（简版/方案说明等政务词），路由分支词从章节上下文
    动态提取（ROUTE_BRANCH_PATTERN），提取不到再用双语通用兜底词。
    """
    body_lines = [ln for ln in content.splitlines() if not ln.strip().startswith(">")]
    body_text = "\n".join(body_lines)
    # 路由章节只认「章节标题」格式（行首 # 或 **），表格行/⚠️说明/正文提及不算
    has_route = bool(re.search(
        ROUTE_SECTION_PATTERN, body_text, re.MULTILINE
    ))
    if not has_route:
        return {"has_route_section": False, "note": "正文无路由章节（变更摘要/引用块中的提及不算），跳过"}

    # 动态提取路由章节上下文的分支词（只取路由章节窗口，不含全文，避免噪音）
    route_ctx = ""
    for m in re.finditer(ROUTE_SECTION_PATTERN, body_text, re.MULTILINE):
        start = m.end()
        ctx_end = body_text.find("\n##", start)
        if ctx_end == -1 or ctx_end - start > 800:
            ctx_end = min(start + 800, len(body_text))
        route_ctx += body_text[start:ctx_end] + "\n"

    # 分支词：完整词（含后缀）+ 停用词过滤 + 去重
    dynamic_words = []
    for mm in ROUTE_BRANCH_PATTERN.finditer(route_ctx):
        w = mm.group(0).strip()
        if len(w) >= 2 and w not in ROUTE_STOPWORDS and w not in dynamic_words:
            dynamic_words.append(w)
    found = []
    # 动态提取词（已限定路由章节上下文）；兜底词也只在路由章节上下文内匹配，
    # 不扫全文——避免「标准/完整/详细」等通用形容词在任意 skill 正文出现即误报
    for w in dynamic_words + ROUTE_FALLBACK_WORDS:
        if w in route_ctx and w not in found:
            found.append(w)

    missing = [kw for kw in found if kw not in (description or "")]
    return {
        "has_route_section": True,
        "route_keywords_found": found[:20],
        "missing_in_description": missing[:20],
        "note": "missing_in_description 非空 → description 未覆盖内部路由分支入口词，触发设计降档候选（judge 确认）",
    }


# ============================================================
# v3.2 · P1 评估闭环有效性
# ============================================================

def _eval_closure_effectiveness(
    target: Path, content: str, executable: Dict[str, Any], rule_scores: Dict[str, Any]
) -> Dict[str, Any]:
    """评估闭环从「存在性」升级到「有效性」：
      - runner_executable: 目标 evals/runner.py 是否真实可跑（接入 dry-run 结果）
      - baseline_drift   : baseline.json 规则可判分与本次评分偏差 >5 → 标记需复盘
      - exemption_declared: 目标是否声明「设计性偏离/预期 CRITICAL」豁免机制（区分预期偏离 vs 真实缺陷）
    """
    info = {"runner_executable": None, "baseline_drift": None, "exemption_declared": None}

    # 1. runner 可跑
    runner = executable.get("runner") if executable else None
    if runner is None:
        info["runner_executable"] = {"has_runner": False}
    elif runner.get("skipped"):
        info["runner_executable"] = {"has_runner": True, "skipped": True}
    else:
        info["runner_executable"] = {
            "has_runner": True,
            "passed": runner.get("passed"),
            "exit_code": runner.get("exit_code"),
        }

    # 2. baseline 偏差
    evals_dir = target / "evals" if target.is_dir() else None
    if evals_dir and evals_dir.is_dir():
        baselines = list(evals_dir.glob("baseline*")) + list(evals_dir.glob("*baseline*"))
        if baselines:
            try:
                bl = json.loads(baselines[0].read_text(encoding="utf-8"))
                dims = bl.get("dimension_scores", {})
                exp_struct = dims.get("structural_sanity")
                exp_eval = dims.get("evaluation_closure")
                if exp_struct is not None and exp_eval is not None:
                    expected_total = exp_struct + exp_eval
                    actual_total = (
                        rule_scores.get("structural_sanity", {}).get("score", 0)
                        + rule_scores.get("evaluation_closure", {}).get("score", 0)
                    )
                    drift = actual_total - expected_total
                    info["baseline_drift"] = {
                        "baseline_file": baselines[0].name,
                        "expected_total": expected_total,
                        "actual_total": actual_total,
                        "drift": drift,
                        "needs_review": abs(drift) > 5,
                    }
            except Exception:
                info["baseline_drift"] = {"error": "baseline.json 解析失败"}

    # 3. 豁免声明检测
    hits = [p for p in EXEMPTION_PATTERNS if p in content]
    info["exemption_declared"] = {
        "declared": bool(hits),
        "patterns": hits,
        "note": "declared=True → judge 区分预期偏离 vs 真实缺陷，不应机械扣分",
    }
    return info


# ============================================================
# v3.1 保留：输出契约线索采集
# ============================================================

def _collect_contract_evidence(target: Path, content: str, files: list) -> Dict[str, Any]:
    """
    输出契约线索采集（v3.1 新增）。
    只提供线索（candidate evidence），不做断言——judge 自行判断是否成立。
    避免把 k12 的 JSON 实现写死成普适判据（YAML/dict/纯内存均可）。
    """
    ev = {"intermediate": [], "render_entry": [], "validate": [], "drift": []}

    # 1. 中间表示线索：SKILL.md 是否提到数据层/中间文件/结构
    for kw in ["json", ".yaml", "yml", "structure", "中间表示", "中间文件", "dict", "data"]:
        if kw.lower() in content.lower():
            ev["intermediate"].append(f"SKILL.md 提及 '{kw}'")

    # 2. 渲染入口线索：scripts 是否读写数据文件
    py_files = _get_py_files(target)
    for f in py_files:
        try:
            fc = f.read_text(encoding="utf-8")
        except Exception:
            continue
        rel = str(f.relative_to(target)) if target.is_dir() else str(f)
        for kw in ["json.dump", "json.load", "yaml.safe_load", "yaml.safe_dump", "write_text", "read_text", "open("]:
            if kw in fc:
                ev["render_entry"].append(f"{rel} 含 '{kw}'")
                break

    # 3. 校验线索：SKILL.md 或脚本是否有 validate/check 类函数
    if re.search(r"validate|校验|check_output|assert", content, re.IGNORECASE):
        ev["validate"].append("SKILL.md 含 validate/校验 相关表述")
    for f in py_files:
        try:
            fc = f.read_text(encoding="utf-8")
        except Exception:
            continue
        if re.search(r"def validate|def check|def verify", fc):
            rel = str(f.relative_to(target)) if target.is_dir() else str(f)
            ev["validate"].append(f"{rel} 含校验函数")
            break

    # 4. 防漂移线索：占位符机制 / 单一事实源
    if re.search(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", content):
        ev["drift"].append("SKILL.md 含 {xxx} 占位符模式（防漂移候选）")
    for kw in ["from_shared", "单一事实源", "防漂移", "CONSTANTS", "共享字段"]:
        if kw in content:
            ev["drift"].append(f"SKILL.md 提及 '{kw}'")

    return {
        "candidates": ev,
        "note": "线索仅供 judge 参考，不是自动判分依据；判 1.0 需 judge 确认三问：①数据独立于渲染？②改数据不碰渲染出新版？③可独立校验？",
    }


# ============================================================
# v3.3 P0-1：IR 全链路双向闭合性
# ============================================================

# 泛化正则：X.append(('type_str', ...)) / X.append(("type_str", ...))
#            X.add("type_str") / X.add('type_str')
#            [('type_str', ...)] / return [(('type_str', ...), ...)]
#            X[("type_str", ...)] 字典 key / (type_str in [...]) 元组字面量
_RE_PRODUCER = [
    re.compile(r"""\.\s*append\s*\(\s*['"]([a-z_][a-z0-9_]*)['"]\s*,"""),  # list.append(('type', ...)
    re.compile(r"""\.\s*append\s*\(\s*\(\s*['"]([a-z_][a-z0-9_]*)['"]\s*,"""),  # .append(('type', ...)
    re.compile(r"""\.\s*add\s*\(\s*['"]([a-z_][a-z0-9_]*)['"]\s*[,)]"""),       # set.add('type') / list.add('type')
    # 列表字面量 / return [...] 里的元组（fixture-style producer）
    re.compile(r"""\[\s*['"]([a-z_][a-z0-9_]*)['"]\s*,"""),                    # ['type', in [...]
    re.compile(r"""\[\s*\(\s*['"]([a-z_][a-z0-9_]*)['"]\s*,"""),                # [(('type', in [...]
    # 无 anchor：任何位置的 ('type', ... ) 元组字面量（fixture 用 return [...] 内）
    re.compile(r"""\(\s*['"]([a-z_][a-z0-9_]*)['"]\s*,"""),                    # ('type', anywhere
]

# 泛化正则：allowed_types = {'a','b'} / allowed_types = ["a","b"]
#            if typ in (..., 'a', 'b'):  / elif typ == 'a'
#            except <Type>: ...
_RE_CONSUMER_ALLOWED = [
    re.compile(r"""=\s*\{([^}]*?)\}"""),                         # {'a', 'b'} → 整体捕获（外层 findall 后再切字面量）
    re.compile(r"""=\s*\[([^\]]*?)\]"""),                        # ["a", "b"]
]
_RE_CONSUMER_IF = [
    re.compile(r"""\bif\s+\w+\s*(?:==|in)\s*\(?[^)\n]*?['"]([a-z_][a-z0-9_]*)['"]"""),
    re.compile(r"""\belif\s+\w+\s*(?:==|in)\s*\(?[^)\n]*?['"]([a-z_][a-z0-9_]*)['"]"""),
]
_RE_CONSUMER_EXCEPT = [
    re.compile(r"""except\s+([A-Z][A-Za-z0-9_]*)\s*[:,]"""),  # except ValueError / except (ValueError, KeyError)
]

# 通用关键词白名单（避免误捕 docstring / 注释 / 普通变量）
_KEYWORD_IGNORE = frozenset({
    # 常见 Python 内置 / 关键字
    "self", "args", "kwargs", "cls", "type", "object", "result", "output",
    "input", "data", "content", "text", "value", "key", "name",
    "main", "__main__", "__init__", "__name__", "__doc__",
    # 通用业务词（docstring 示例常用）
    "type_str", "default", "suspicious", "extra", "description",
    "needs_review", "warning", "internal", "test", "example",
    "true", "false", "none", "null",
    # v3.3 自身证据采集关键词（自指，避免自证）
    "evidence", "candidates", "judgment_rule", "producers", "consumers",
    "files_scanned", "pass_count", "warn_paired", "branches",
    "covered", "uncovered", "declared", "implemented", "missing",
    "gaps", "summary", "rule_scores", "contract_evidence",
    "version_info", "executable_evidence", "element_closure",
    "route_evidence", "ir_closure", "silent_failures",
    "fallback_branches", "docstring_api",
    # v3.3.1 新增 runtime+test checker 键名（防自指）
    "fallback_shadowing", "real_path_regression",
    # v3.4 新增 package_engineering 键名与副产物字段（防自指）
    "package_engineering", "contract_asset", "eval_report",
    "disclosure_card", "signature", "kit_routing",
    "live_source_principle", "contract_keys", "snippets",
    "paths", "present",
    # v3.3.1 内部字段（fail-002 / real_path 副产物）
    "warn_no_propagation", "warn_only_sites",
    "coverage_assessment", "entry_source", "production_entry",
    "eval_entries", "fork_points", "blind_stages",
    "judgment_rule_applied", "shadowing_confirmed", "static_candidates",
    # pingjia 自身 / 通用业务词（dict key / 状态描述）
    "examples", "exit_code", "body", "has_runner", "exemption_declared",
    "a", "b", "lorem", "score", "weight", "evidence_dict",
    "candidate", "rule", "sub_item",
    # _eval_executable 内部 dict key
    "type1", "git_dirty", "skipped", "timeout", "drift", "error",
    "stderr_tail", "note", "stdout_tail", "command", "returncode",
    "runner_executable", "baseline_drift",
    # pingjia 评分维度名（七维）+ 子项
    "trigger_design", "process_discipline", "structural_sanity",
    "output_contract", "guardrails", "config_boundary", "evaluation_closure",
    "items", "quick", "image",
    # Python 常见单字母 / 缩写
    "p", "q", "n", "m", "k", "v", "i", "j", "x", "y", "z",
    # 通用词
    "info", "msg", "err", "tmp", "dir", "src", "dst", "log",
})


def _strip_docstrings(source: str) -> str:
    """用 ast 解析文件，移除所有 docstring（保留行数占位）。"""
    import ast
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    # 收集 docstring 节点位置
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                ranges.append((node.lineno, node.end_lineno))

    lines = source.split("\n")
    for start, end in sorted(ranges, reverse=True):
        for i in range(start - 1, min(end, len(lines))):
            # 替换为同长度空白（保留行号，docstring 位置留空不影响正则匹配）
            lines[i] = ""
    return "\n".join(lines)


def _extract_types_from_file(py_path: Path, patterns: list, ignore_keywords: frozenset = _KEYWORD_IGNORE) -> set:
    """通用：从 Python 文件中按一组正则抽类型名集合（跳过 docstring + 关键词白名单）。

    支持两种捕获形态：
    1. 直接捕获单个字面量（如 ('type', ... ）） → 原样加入
    2. 捕获字面量列表（如 {'a', 'b'} 整体捕获） → 二次切词后逐一加入
    """
    found = set()
    try:
        content = py_path.read_text(encoding="utf-8")
    except Exception:
        return found

    # 移除 docstring 后再匹配（避免误捕 docstring 里的正则/示例）
    content = _strip_docstrings(content)

    _LITERAL_RE = re.compile(r"""['"]([a-z_][a-z0-9_]*)['"]""")
    for pat in patterns:
        for m in pat.finditer(content):
            t = m.group(1)
            if not t:
                continue
            # 判断是单字面量还是字面量列表（含 , 或 ; 分隔且整体像 { ... } / [ ... ]）
            if ("," in t or ";" in t) and not t.startswith(("\"")):
                # 二次切词：把所有引号字面量都纳入
                for sub in _LITERAL_RE.finditer(t):
                    name = sub.group(1)
                    if name and name not in ignore_keywords and not name.startswith("_"):
                        found.add(name)
            else:
                if t and t not in ignore_keywords and not t.startswith("_"):
                    found.add(t)
    return found


def _collect_ir_closure(target: Path) -> Dict[str, Any]:
    """
    v3.3 P0-1：IR 全链路双向闭合性。

    采集 producer（生成/解析/构造入口产出的元素类型集合）
    vs consumer（保存/序列化/加载/渲染/校验声明的合法类型集合），
    比对差异，产出"真实缺口"清单。

    泛化实现：行为特征识别（append/add/allowed_types/in 分支/elif 分支/except 类型），
    不绑 docx 词表，非文档类 skill 零误报。
    """
    ev = {"producers": {}, "consumers": {}, "gaps": [], "files_scanned": 0}

    py_files = _get_py_files(target)
    ev["files_scanned"] = len(py_files)

    producer_types: set = set()
    consumer_types: set = set()

    for f in py_files:
        rel = str(f.relative_to(target)) if target.is_dir() else str(f)

        # producer：append / add 字面量
        producers_in_file = _extract_types_from_file(f, _RE_PRODUCER)
        if producers_in_file:
            producer_types.update(producers_in_file)
            for t in producers_in_file:
                ev["producers"].setdefault(t, []).append(rel)

        # consumer：allowed_types 字面量
        consumers_allowed = _extract_types_from_file(f, _RE_CONSUMER_ALLOWED)
        # consumer：if/elif typ in (...) / typ == '...'
        consumers_if = _extract_types_from_file(f, _RE_CONSUMER_IF)
        consumers_in_file = consumers_allowed | consumers_if
        if consumers_in_file:
            consumer_types.update(consumers_in_file)
            for t in consumers_in_file:
                ev["consumers"].setdefault(t, []).append(rel)

    # 找"真实缺口"：规格书要求 per-consumer 求差（v3.3.1 升级）
    #   - drift：producer 产出，至少一个 consumer 接受、至少一个 consumer 不接受 → 真合同缺口
    #   - internal_only：producer 产出，但所有 consumer 都不接受 → 可能是内部临时类型
    #   - 完全接受（所有 consumer 都接受）→ 不进 gaps
    # 实现：直接基于已采集的 per-file 列表（ev["producers"][t] / ev["consumers"][t]）做集合差
    consumer_files_for_type = {
        t: set(files) for t, files in ev["consumers"].items()
    }
    for t in producer_types:
        accepting = consumer_files_for_type.get(t, set())
        rejecting = set(ev["consumers"].keys()) and (
            {f for files in ev["consumers"].values() for f in files} - accepting
        ) if ev["consumers"] else set()
        # 重新算：所有 consumer 文件 = union of all consumer files
        all_consumer_files = {f for files in ev["consumers"].values() for f in files}
        rejecting = all_consumer_files - accepting

        if accepting and rejecting:
            ev["gaps"].append({
                "type": t,
                "producers": ev["producers"].get(t, []),
                "accepted_by": sorted(accepting),
                "rejected_by": sorted(rejecting),
                "status": "drift",
                "note": "per-consumer 求差：部分 consumer 接受、部分拒绝 → 真合同缺口",
            })
        elif not accepting and rejecting:
            ev["gaps"].append({
                "type": t,
                "producers": ev["producers"].get(t, []),
                "accepted_by": [],
                "rejected_by": sorted(rejecting),
                "status": "internal_only",
                "note": "所有 consumer 都不接受 → 可能是内部临时类型；人工核对",
            })

    return {
        "evidence": ev,
        "summary": {
            "producer_count": len(producer_types),
            "consumer_count": len(consumer_types),
            "gap_count": len([g for g in ev["gaps"] if g["status"] == "drift"]),
        },
        "judgment_rule": (
            "drift 类型非空 → 输出契约「结构化中间表示」子项 1.0 → 0.5；"
            "internal_only 类型不算缺口（可能是内部临时类型）；"
            "无法静态识别（如全动态构造）→ 报 inconclusive，由 judge 人工核对"
        ),
    }


# ============================================================
# v3.3 P0-2：静默失败扫描（裸 except: pass）
# ============================================================

_PAT_PASS = re.compile(r"except[^:\n]*:\s*\n\s*pass\s*$", re.MULTILINE)
_PAT_WARN = re.compile(r"_?logger\.warning|logging\.warning|print\([^)]*WARN", re.IGNORECASE)
# v3.3.1：状态语义传播特征（SK-FAIL-002）——except 块内是否有非成功状态标记
# 启发式：except 块内出现 status='degraded/fallback/...' / error_code= / 'status': '...' 算"状态传播"
_PAT_STATUS_PROPAGATION = re.compile(
    r"""status\s*=\s*['"](?:degraded|fallback|partial|failure|error)['"]"""
    r"""|error_code\s*=|severity\s*=|'status':\s*['"](?:degraded|fallback|partial|failure)['"]"""
)


def _collect_silent_failures(target: Path) -> Dict[str, Any]:
    """
    v3.3 P0-2：静默失败扫描。

    扫描 scripts/ 中所有 .py 文件，统计 `except Exception: pass`（或变体）
    出现的位置；同一文件若没有 logger.warning/logging.warning/print(WARN...)
    配套警告，标记为"suspicious"（静默吞错 → heuristic 接管 → 危险伪装）。

    线索非断言：报告里列位置+文件，给 judge 提示；不直接扣分。
    """
    ev = {
        "files_scanned": 0,
        "pass_count": 0,
        "warn_paired": 0,
        # v3.3.1：日志可见但状态未传播（SK-FAIL-002）——except 块带 warning 但无 status= 等传播
        "warn_no_propagation": 0,
        "warn_only_sites": [],
        "suspicious": [],
    }

    py_files = _get_py_files(target)
    ev["files_scanned"] = len(py_files)

    for f in py_files:
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        rel = str(f.relative_to(target)) if target.is_dir() else str(f)

        pass_hits = list(_PAT_PASS.finditer(content))
        if not pass_hits:
            continue

        has_warn = bool(_PAT_WARN.search(content))
        for m in pass_hits:
            line_no = content[: m.start()].count("\n") + 1
            if has_warn:
                ev["warn_paired"] += 1
                # v3.3.1：warning 只证明"日志可见"，不证明"状态可传播"
                # except 块附近文本（200 字符覆盖 except ... pass 单条语句 + 紧跟行）
                block_text = content[m.start(): m.end() + 200]
                if not _PAT_STATUS_PROPAGATION.search(block_text):
                    ev["warn_no_propagation"] += 1
                    ev["warn_only_sites"].append({"file": rel, "line": line_no})
            else:
                ev["pass_count"] += 1
                ev["suspicious"].append({
                    "file": rel,
                    "line": line_no,
                    "snippet": m.group(0).strip().replace("\n", "\\n")[:80],
                })

    return {
        "evidence": ev,
        "judgment_rule": (
            "pass_count > 5 且 warn_paired/pass_count < 0.3 → 配置边界或护栏降档证据；"
            "warn_no_propagation > 0 → SK-FAIL-002 候选（日志可见但状态未传播，judge 确认）；"
            "线索仅供 judge 参考；报告必列『裸 pass 位置+文件』与『warn_only 位置+文件』"
        ),
    }


# ============================================================
# v3.3 P1-1：兜底分支触发审计
# ============================================================

# 兜底分支模式：
#   elif typ in (..., 'type1', 'type2'):
#   if typ in (...):
#   except <Type>:  ← 上一节已采集 except，但兜底分支只看 in (...) 内的类型
#   .get('key', default)  ← dict.get 兜底 key 列表
_FALLBACK_BRANCH = [
    re.compile(r"""\belif\s+\w+\s+in\s+\(([^)]+)\)"""),
    re.compile(r"""\bif\s+\w+\s+in\s+\(([^)]+)\)"""),
    re.compile(r"""\.get\(\s*['"]([a-z_][a-z0-9_]*)['"]\s*,"""),  # dict.get('key', ...)
]


def _collect_fallback_branches(target: Path, producer_types: set) -> Dict[str, Any]:
    """
    v3.3 P1-1：兜底分支触发审计。

    扫描脚本中的兜底条件（elif typ in (...): / dict.get('k', None)），
    提取兜底分支"接受"的类型集合；与 producer_types 比对：
    - 兜底接受 = producer ∩ ：正常
    - 兜底接受 ⊂ producer ：缺一些 producer 类型 → 落进兜底分支会无声失败
    """
    ev = {"branches": [], "covered": set(), "uncovered": []}

    py_files = _get_py_files(target)

    # 从兜底条件里提取的"接受类型"（按文件 + 行号 + 字面量列表）
    accepted: set = set()
    for f in py_files:
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        rel = str(f.relative_to(target)) if target.is_dir() else str(f)
        for pat in _FALLBACK_BRANCH:
            for m in pat.finditer(content):
                line_no = content[: m.start()].count("\n") + 1
                # 提取字面量
                literals = re.findall(r"""['"]([a-z_][a-z0-9_]*)['"]""", m.group(1) if "(" in m.group(1) else m.group(0))
                if literals:
                    ev["branches"].append({
                        "file": rel,
                        "line": line_no,
                        "accepted_types": literals,
                    })
                    accepted.update(literals)

    ev["covered"] = sorted(accepted & producer_types)
    ev["uncovered"] = sorted(producer_types - accepted)

    return {
        "evidence": ev,
        "judgment_rule": (
            "uncovered 非空 → 输出契约或护栏降档证据；"
            "（jishufangan v3.15 案：parse 产出 h1_present，generate_from_structure 兜底 elif typ in (..., 'body',) 缺 h1_present）"
        ),
    }


# ============================================================
# v3.3 P2：声明-实现对照
# ============================================================

# SKILL.md 中 code block 提到的入口函数名（heuristic 粗匹配）
#   `function_name(`
#   `import xxx from yyy`
#   `from xxx import yyy`
_RE_DECLARED_FUNCTIONS = re.compile(r"`([a-z_][a-z0-9_]*)\s*\(`", re.IGNORECASE)
_RE_DECLARED_FROM_IMPORT = re.compile(r"`from\s+(\w+)\s+import\s+([a-z_][a-z0-9_]*)\s*`", re.IGNORECASE)


def _collect_docstring_api_mismatch(target: Path, content: str) -> Dict[str, Any]:
    """
    v3.3 P2：声明-实现对照（半自动）。

    SKILL.md code block 提到的入口函数 / from-import 模块
    vs scripts/ 实际 def 的函数 / 顶层 import 模块，
    差集 → report evidence；判定交给 judge（区分装饰性提及 vs 承诺调用）。
    """
    ev = {"declared": set(), "implemented": set(), "missing": [], "extra": []}

    # declared：SKILL.md code block 提到的函数名 / from-import
    declared_funcs = set(m.group(1) for m in _RE_DECLARED_FUNCTIONS.finditer(content))
    declared_funcs.update(
        m.group(2) for m in _RE_DECLARED_FROM_IMPORT.finditer(content)
    )
    ev["declared"] = declared_funcs

    # implemented：scripts/ 实际 def / 顶层 import
    py_files = _get_py_files(target)
    for f in py_files:
        try:
            fc = f.read_text(encoding="utf-8")
        except Exception:
            continue
        # top-level def xxx(
        for m in re.finditer(r"^def\s+([a-z_][a-z0-9_]*)\s*\(", fc, re.MULTILINE):
            ev["implemented"].add(m.group(1))
        # import xxx / from xxx import yyy 顶层
        for line in fc.splitlines():
            mm = re.match(r"^(?:from\s+(\w+)|import\s+(\w+))", line.strip())
            if mm:
                ev["implemented"].add(mm.group(1) or mm.group(2))

    ev["missing"] = sorted(declared_funcs - ev["implemented"])
    ev["extra"] = sorted(ev["implemented"] - declared_funcs)

    return {
        "evidence": ev,
        "judgment_rule": (
            "missing 非空 → judge 区分『装饰性提及』vs『承诺调用』；"
            "若 SKILL.md 示例代码块引用但 scripts 无定义 → 触发设计降档证据"
        ),
    }


# ============================================================
# 保留：H4 三权分立（v2 自动校验）
# ============================================================

def _eval_h4(target: Path, content: str, files: list) -> Dict[str, Any]:
    """
    H4 三权分立硬门槛（自动校验，不再是 LLM 评）。
    返回 {"pass": bool, "reasons": [...]} —— 任何 ❌ 触发 = 严重违反 = 一票否决。
    """
    reasons = []
    skill_md = target / "SKILL.md" if target.is_dir() else target

    # 判据 1: SKILL.md 与 scripts/ 同时硬编码同一格式定义
    fmt_utils = ["D9E2F3", "#FFF", "宋体", "13.0", "46.94", "46.938", "11.0", "12.0", "size=12", "size=11"]
    skill_md_lines = content.splitlines()
    skill_md_code_lines = []
    in_code_block = False
    for line in skill_md_lines:
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or line.startswith("#"):
            continue
        skill_md_code_lines.append(line)
    skill_md_scan = "\n".join(skill_md_code_lines)

    skill_md_hits = [k for k in fmt_utils if k in skill_md_scan]
    scripts_dir = target / "scripts" if target.is_dir() else None
    scripts_hits = []
    if scripts_dir and scripts_dir.is_dir():
        for f in scripts_dir.rglob("*.py"):
            if _is_noise(f):
                continue
            try:
                fc = f.read_text(encoding="utf-8")
                fc_clean = fc.replace("def _eval_h4", "").replace("def _score_structure_and_eval", "")
                hits = [k for k in fmt_utils if k in fc_clean]
                if hits:
                    scripts_hits.append((str(f.relative_to(target)), hits))
            except Exception:
                pass
    if skill_md_hits and scripts_hits:
        reasons.append(f"SKILL.md 与 scripts/ 同时硬编码格式: skill_md={skill_md_hits}, scripts={scripts_hits[:2]}")

    # 判据 2: SKILL.md 引用模板但模板不存在
    template_refs = re.findall(r"(?:^|\s|`)(/[\w./_-]+\.(?:xlsx|html|json|md)|\./[\w./_-]+\.(?:xlsx|html|json|md)|\.\./[\w./_-]+\.(?:xlsx|html|json|md))", content, re.MULTILINE)
    for ref in template_refs:
        ref = ref.strip()
        if ref.startswith("/"):
            ref_path = Path(ref)
        else:
            ref_path = (skill_md.parent / ref).resolve()
        if not ref_path.exists():
            reasons.append(f"SKILL.md 引用 {ref} 不存在")

    # 判据 3: ≥30 行 HTML/JSON/XML 模板塞正文
    code_blocks = re.findall(r"```(?:html|json|xml)\s*\n(.*?)\n```", content, re.DOTALL)
    big_blocks = [len(b.splitlines()) for b in code_blocks if len(b.splitlines()) >= 30]
    if big_blocks:
        reasons.append(f"SKILL.md 正文含 ≥30 行 HTML/JSON/XML 模板: 块行数 {big_blocks}")

    return {"pass": not reasons, "reasons": reasons}


# ============================================================
# 保留：结构合理性 + 评估闭环（规则能判部分）
# ============================================================

def _score_structure_and_eval(target: Path, files: list) -> Dict[str, Any]:
    """
    结构合理性（20 分）+ 评估闭环（15 分）—— 规则能判的部分。
    触发/流程/输出/护栏/配置边界 5 个维度 LLM 评（0 占位）。
    """
    rel_path = lambda p: str(p.relative_to(target)) if target.is_dir() else str(p)

    # 结构合理性
    structure = {
        "skill_md_under_500": {"weight": 5, "score": 0, "evidence": ""},
        "references_split": {"weight": 8, "score": 0, "evidence": ""},
        "scripts_deterministic": {"weight": 7, "score": 0, "evidence": ""},
    }
    if target.is_dir():
        target_name = target.name
    else:
        target_name = target.parent.name
    skill_md = target / "SKILL.md" if target.is_dir() else target
    lines = skill_md.read_text(encoding="utf-8").splitlines() if skill_md.exists() else []
    if len(lines) < 500:
        structure["skill_md_under_500"]["score"] = 5
        structure["skill_md_under_500"]["evidence"] = f"SKILL.md {len(lines)} 行 < 500"
    else:
        structure["skill_md_under_500"]["evidence"] = f"SKILL.md {len(lines)} 行 ≥ 500"

    refs_dir = target / "references" if target.is_dir() else target.parent / "references"
    if refs_dir.is_dir():
        ref_count = sum(1 for _ in refs_dir.iterdir() if _.is_file())
        if ref_count >= 2:
            structure["references_split"]["score"] = 8
            structure["references_split"]["evidence"] = f"references/ {ref_count} 份"
        elif ref_count == 1:
            structure["references_split"]["score"] = 4
            structure["references_split"]["evidence"] = f"references/ 仅 1 份"
    else:
        structure["references_split"]["evidence"] = "references/ 缺失"

    scripts_dir = target / "scripts" if target.is_dir() else target.parent / "scripts"
    if scripts_dir.is_dir():
        script_count = sum(1 for f in scripts_dir.rglob("*.py") if not _is_noise(f))
        if script_count >= 1:
            structure["scripts_deterministic"]["score"] = 7
            structure["scripts_deterministic"]["evidence"] = f"scripts/ {script_count} 个 .py"
    else:
        structure["scripts_deterministic"]["evidence"] = "scripts/ 缺失"

    structure_total = sum(item["score"] for item in structure.values())

    # 评估闭环（v3: 20→15 分，子项 5/5/5/5 → 4/4/4/3）
    eval_closure = {
        "evals_dir": {"weight": 4, "score": 0, "evidence": ""},
        "rubrics_judgement": {"weight": 4, "score": 0, "evidence": ""},
        "with_without_compare": {"weight": 4, "score": 0, "evidence": ""},
        "regression_baseline": {"weight": 3, "score": 0, "evidence": ""},
    }
    evals_dir = target / "evals" if target.is_dir() else target.parent / "evals"
    if evals_dir.is_dir():
        # evals_dir (4)
        case_count = sum(1 for _ in (evals_dir / "cases").iterdir() if _.is_dir()) if (evals_dir / "cases").is_dir() else 0
        if case_count >= 1:
            eval_closure["evals_dir"]["score"] = 4
            eval_closure["evals_dir"]["evidence"] = f"evals/ 含 {case_count} 个用例"
        # rubrics (4): 找 rubric.md 或 files
        rubric_files = ["rubric.md", "report_template.json"]
        for rf in rubric_files:
            if (evals_dir / rf).exists():
                eval_closure["rubrics_judgement"]["score"] = 4
                eval_closure["rubrics_judgement"]["evidence"] = f"evals/{rf} 存在"
                break
        # with/without (4): 找 with_skill/ 或 without_skill/ 目录
        if (evals_dir / "with_skill").is_dir() or (evals_dir / "without_skill").is_dir():
            eval_closure["with_without_compare"]["score"] = 4
            eval_closure["with_without_compare"]["evidence"] = "with/without 目录存在"
        # regression_baseline (3): 找 baseline 文件
        baseline_files = list(evals_dir.glob("baseline*")) + list(evals_dir.glob("*baseline*"))
        if baseline_files:
            eval_closure["regression_baseline"]["score"] = 3
            eval_closure["regression_baseline"]["evidence"] = f"{baseline_files[0].name} 存在"
    else:
        eval_closure["evals_dir"]["evidence"] = "evals/ 缺失"

    eval_total = sum(item["score"] for item in eval_closure.values())

    return {
        "structural_sanity": {**structure, "score": structure_total, "max": 20},
        "evaluation_closure": {**eval_closure, "score": eval_total, "max": 15},
    }


# ============================================================
# v3.3.1 P0-3 ★标杆：fallback_shadowing（SK-CONT-004）
# 检测：Primary 失败被 Fallback 接管后，最终输出是否仍能区分 primary failure。
# 三模式：TEST → RUNTIME → STATIC（前者可用优先）
# 禁止：纯 AST/grep 实现 —— `except: warning(); return fallback()` 静态扫描是绿的，但语义上仍是伪装成功
# ============================================================

# 成功语义 token（fallback 返回这些 = SHADOWING）
_SUCCESS_TOKENS = frozenset({
    "True", "None", "{}", "[]", '""', "''", "0", "ok", "OK", "success", "SUCCESS",
    "fallback_result", "default_value", "result",
})

_STATIC_PAT = re.compile(
    r"except[^:\n]*:\s*\n\s*return\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)


def _run_static_only(target: Path, ev: dict) -> None:
    """STATIC 模式：仅识别 `except ... return X` 候选（线索非断言）。"""
    py_files = _get_py_files(target)
    for f in py_files:
        try:
            ftext = f.read_text(encoding="utf-8")
        except Exception:
            continue
        rel = str(f.relative_to(target)) if target.is_dir() else str(f)
        for m in _STATIC_PAT.finditer(ftext):
            line_no = ftext[: m.start()].count("\n") + 1
            tok = m.group(1)
            ev["static_candidates"].append({
                "file": rel,
                "line": line_no,
                "fallback_value": tok,
                "is_success_token": tok in _SUCCESS_TOKENS,
            })


def _is_success_semantic(returned):
    """启发式判断返回值是否带"成功"语义：None/True/空集合/通用变量名."""
    if returned is None or returned is True or returned is False:
        return returned is not False  # False/None/True 都可能
    if isinstance(returned, str):
        return returned in {"", "ok", "success"} or "success" in returned.lower()
    if isinstance(returned, (list, dict, set, tuple)):
        return len(returned) == 0
    return False


def _wrap_fallback_shadowing(ev: dict) -> Dict[str, Any]:
    """统一输出契约：verdict + evidence."""
    tested = ev.get("tested", [])
    confirmed = ev.get("shadowing_confirmed", [])
    if confirmed:
        verdict: Verdict = FAIL
    elif tested:
        verdict: Verdict = PASS
    else:
        verdict: Verdict = INCONCLUSIVE
    return {
        "evidence": ev,
        "verdict": verdict,
        "judgment_rule": (
            "Primary 失败后 fallback 仍输出成功语义 → SHADOWING（FAIL）；"
            "fallback 输出 ∈ {DEGRADED, FALLBACK, PARTIAL, FAILURE} → PASS；"
            "无法静态判定或 RUNTIME 不可执行 → INCONCLUSIVE（线索非断言）"
        ),
    }


def _collect_fallback_shadowing(target: Path, content: str) -> Dict[str, Any]:
    """
    SK-CONT-004 / v3.3.1 标杆 checker。
    架构裁决（规格书）：
      1. 静态扫描 `except ... return X` 仅作线索（非断言）；
      2. TEST 模式：跑 evals/cases 里的 fallback 测试 → 比对状态；
      3. RUNTIME 模式：monkeypatch producer 抛异常 → 跑入口 → 捕获返回值语义；
      4. 三个模式都失败 → INCONCLUSIVE。
    """
    ev = {
        "mode": None,
        "tested": [],
        "shadowing_confirmed": [],
        "static_candidates": [],
        "untestable": [],
        "judgment_rule_applied": None,
    }

    # 防递归：runner 调用 score.py 时设 SKILLPINGJIA_DRYRUN=0，
    # 内层 score.py 不应再起子进程（否则 TEST/RUNTIME 模式会无限递归）
    if _is_reentrant_dryrun():
        ev["mode"] = None
        ev["untestable"].append({"reason": "re-entrant call (SKILLPINGJIA_DRYRUN=0), skip RUNTIME/TEST"})
        ev["judgment_rule_applied"] = "嵌套调用防递归 → 仅 STATIC 线索"
        # 仍跑 STATIC 部分（不发起子进程）
        _run_static_only(target, ev)
        return _wrap_fallback_shadowing(ev)

    py_files = _get_py_files(target)

    # ---------- STATIC：识别 `except ... return X` 候选（仅线索）----------
    _run_static_only(target, ev)

    # ---------- TEST：跑 evals/cases 里 fallback 测试 ----------
    evals_dir = target / "evals"
    test_outcome = None
    if evals_dir.is_dir():
        cases_dir = evals_dir / "cases"
        if cases_dir.is_dir():
            for case_sub in cases_dir.iterdir():
                if not case_sub.is_dir():
                    continue
                inp = case_sub / "input.json"
                if not inp.exists():
                    continue
                # 识别 fallback 测试：input.json 含 fallback / shadowing 关键字
                try:
                    spec = json.loads(inp.read_text(encoding="utf-8"))
                except Exception:
                    continue
                spec_str = json.dumps(spec, ensure_ascii=False)
                if "fallback" in spec_str.lower() or "shadow" in spec_str.lower() or "blind" in case_sub.name.lower():
                    ev["tested"].append({
                        "case": case_sub.name,
                        "spec_keys": list(spec.keys()),
                    })
                    # 实际跑这个 case（subprocess 隔离）
                    try:
                        result = subprocess.run(
                            ["python3", str(evals_dir / "runner.py")],
                            capture_output=True, text=True, timeout=10,
                            cwd=str(target),
                            env={**os.environ, "SKILLPINGJIA_DRYRUN": "0"},
                        )
                        ev["tested"][-1]["runner_exit"] = result.returncode
                        ev["tested"][-1]["runner_stdout_tail"] = result.stdout[-300:]
                        # 如果 runner 全部 PASS（exit 0）但 v3.3 静态证据中有大量 silent_failure → SHADOWING 候选
                        if result.returncode == 0:
                            ev["tested"][-1]["outcome"] = "all_pass"
                            test_outcome = "all_pass"
                        else:
                            ev["tested"][-1]["outcome"] = "fail_detected"
                            test_outcome = "fail_detected"
                    except subprocess.TimeoutExpired:
                        ev["tested"][-1]["outcome"] = "timeout"
                    except Exception as e:
                        ev["tested"][-1]["outcome"] = f"error: {e}"

    # ---------- RUNTIME：monkeypatch producer → 跑入口 ----------
    runtime_tested = False
    skill_md = target / "SKILL.md"
    if skill_md.exists():
        # 1. 找入口函数（SKILL.md backtick 函数声明）
        entry_pat = re.compile(r"`([a-z_][a-z0-9_]*)\s*\(`")
        entries = list({m.group(1) for m in entry_pat.finditer(content)})
        # 2. 找 producer 函数（heuristic：名字含 parse/read/load/extract）
        producer_pat = re.compile(
            r"def\s+(parse|read|load|extract|build|generate)\w*\s*\(",
        )
        producer_names = set()
        for f in py_files:
            try:
                ftext = f.read_text(encoding="utf-8")
            except Exception:
                continue
            for m in producer_pat.finditer(ftext):
                producer_names.add(m.group(1))

        if entries and producer_names and py_files:
            # 尝试 import scripts 包
            scripts_dir = target / "scripts"
            if scripts_dir.is_dir():
                sys.path.insert(0, str(target))
                try:
                    # 找到包含 producer 函数的模块
                    injected_module = None
                    injected_func = None
                    for f in py_files:
                        if f.parent.name != "scripts":
                            continue
                        try:
                            ftext = f.read_text(encoding="utf-8")
                        except Exception:
                            continue
                        for m in producer_pat.finditer(ftext):
                            fname = m.group(1)
                            mod_name = f.stem
                            try:
                                mod = importlib.import_module(f"scripts.{mod_name}")
                                if hasattr(mod, fname):
                                    injected_module = mod
                                    injected_func = getattr(mod, fname)
                                    break
                            except Exception:
                                continue
                        if injected_module:
                            break

                    if injected_module and injected_func:
                        # 3. monkeypatch producer 抛 RuntimeError
                        def _fail(*args, **kwargs):
                            raise RuntimeError("injected primary failure for shadowing test")
                        original = injected_func
                        setattr(injected_module, injected_func.__name__, _fail)
                        try:
                            # 4. 找入口函数（SKILL.md 第一个声明）
                            entry_name = entries[0]
                            # 在 scripts/ 各模块里找
                            for f in py_files:
                                mod_name = f.stem
                                try:
                                    mod = importlib.import_module(f"scripts.{mod_name}")
                                    if hasattr(mod, entry_name):
                                        entry_fn = getattr(mod, entry_name)
                                        # 尝试调用（带试探性参数）
                                        try:
                                            ret = entry_fn("test_input", None)
                                            ev["tested"].append({
                                                "mode": "RUNTIME",
                                                "entry": entry_name,
                                                "primary": injected_func.__name__,
                                                "return_type": type(ret).__name__,
                                                "return_repr": repr(ret)[:100],
                                                "is_success_semantic": _is_success_semantic(ret),
                                            })
                                            runtime_tested = True
                                            if _is_success_semantic(ret):
                                                ev["shadowing_confirmed"].append({
                                                    "site": f"scripts/{injected_module.__name__.split('.')[-1]}.py:{injected_func.__name__}",
                                                    "final_status": "success_semantic",
                                                    "expected": "DEGRADED/FALLBACK/PARTIAL/FAILURE",
                                                })
                                        except RuntimeError as re_err:
                                            # 注入的失败透传出来 → PASS（fallback 未吞错）
                                            ev["tested"].append({
                                                "mode": "RUNTIME",
                                                "entry": entry_name,
                                                "primary": injected_func.__name__,
                                                "raised": str(re_err),
                                                "is_success_semantic": False,
                                            })
                                            runtime_tested = True
                                        except Exception as e:
                                            # 其他异常：可能是 fallback 返回的异常 → 标记
                                            ev["tested"].append({
                                                "mode": "RUNTIME",
                                                "entry": entry_name,
                                                "primary": injected_func.__name__,
                                                "raised": f"{type(e).__name__}: {str(e)[:80]}",
                                            })
                                            runtime_tested = True
                                        break
                                except Exception:
                                    continue
                        finally:
                            # 恢复原函数
                            setattr(injected_module, injected_func.__name__, original)
                finally:
                    if str(target) in sys.path:
                        sys.path.remove(str(target))

    # ---------- 模式裁决 ----------
    if runtime_tested:
        ev["mode"] = "RUNTIME"
        ev["judgment_rule_applied"] = "RUNTIME 故障注入 + 入口返回值语义"
    elif ev["tested"] and test_outcome == "fail_detected":
        ev["mode"] = "TEST"
        ev["judgment_rule_applied"] = "TEST 通过 runner 跑出 fallback 失败"
    elif ev["tested"]:
        ev["mode"] = "TEST"
        ev["judgment_rule_applied"] = "TEST 但 runner 全 PASS（线索非断言）"
    elif ev["static_candidates"]:
        ev["mode"] = "STATIC"
        ev["judgment_rule_applied"] = "纯静态线索 — 不可断言，仅供 judge 参考"
        ev["untestable"].append({
            "reason": "RUNTIME/TEST 不可执行（无入口函数/producer/evals）",
            "static_candidate_count": len(ev["static_candidates"]),
        })
    else:
        ev["mode"] = None
        ev["untestable"].append({"reason": "无 except 兜底、无入口函数、无 producer"})

    return _wrap_fallback_shadowing(ev)


# ============================================================
# v3.3.1 P0-4：real_path_regression（SK-EVAL-002）
# 验证目标：eval 路径与生产路径的重合度 —— 测试 case 数量 ≠ 路径覆盖率
# 输出：production_entry / eval_entry / fork_point / blind_stages
# 规格书回归预期：jishufangan v3.15 → production_entry=convert_to_gov_format,
#                 eval_entry=_fixture_to_body, fork_point@parse_docx → blind_stages=[parse_docx]
# ============================================================


def _extract_call_chain(py_path: Path, max_depth: int = 5) -> list:
    """从一个 .py 文件提取函数调用链（启发式：def → 内部调用）。"""
    try:
        content = py_path.read_text(encoding="utf-8")
    except Exception:
        return []
    chain = []
    # 找所有 def 名（顶层 + 嵌套）
    for m in re.finditer(r"^def\s+([a-z_][a-z0-9_]*)\s*\(", content, re.MULTILINE):
        chain.append(m.group(1))
        if len(chain) >= max_depth:
            break
    return chain


def _extract_production_entry(content: str) -> tuple:
    """从 SKILL.md 识别生产入口（三级 heuristic，v3.3.1）。

    返回 (entry_name, entry_source) 元组，entry_source 标识识别来源，便于 judge 复核：
      - "code_block_def"  : 一级 - ```python 块里的 def
      - "prose_pipeline_verb" : 二级 - 正文里 convert_to_*/generate_from_*/build_*/run_* 动词约定
      - "cli_command"     : 三级 - python[3] scripts/xxx.py 形态
      - "backtick_call"   : 四级退化 - 反引号函数调用
      - (None, None)      : 未识别
    """
    # 一级：```python 块里的 def
    for m in re.finditer(r"```python\s*\n(?:[^`]*?)def\s+([a-z_][a-z0-9_]*)\s*\(", content, re.DOTALL):
        return m.group(1), "code_block_def"
    # 二级：管线动词约定（convert_to_*/generate_from_*/build_*/run_*）
    for m in re.finditer(r"\b((?:convert_to|generate_from|build|run)_[a-z_][a-z0-9_]*)\s*\(", content):
        return m.group(1), "prose_pipeline_verb"
    # 三级：CLI 命令形态 —— "python scripts/xxx.py" / "python3 scripts/xxx.py"
    for m in re.finditer(r"python3?\s+(?:scripts/)?([a-z_][a-z0-9_]*\.py)", content):
        return m.group(1), "cli_command"
    # 四级退化：反引号函数调用
    for m in re.finditer(r"`([a-z_][a-z0-9_]*)\s*\(`", content):
        return m.group(1), "backtick_call"
    return None, None


def _extract_eval_entry(case_input: dict, py_files: list) -> str:
    """从 eval case 识别实际调用起点（heuristic：input.json 里的"import"声明 + 脚本里 fixture 入口）。"""
    spec_str = json.dumps(case_input, ensure_ascii=False).lower()
    # 找 case 是不是 fixture-style：case 直接 import scripts
    if "import scripts" in spec_str or "from scripts" in spec_str:
        # 找 scripts 里以 _fixture / _case 开头的函数（eval 专用入口）
        for f in py_files:
            try:
                ftext = f.read_text(encoding="utf-8")
            except Exception:
                continue
            for m in re.finditer(r"^def\s+(_fixture_[a-z0-9_]+|_case_[a-z0-9_]+|_eval_[a-z0-9_]+)\s*\(", ftext, re.MULTILINE):
                return m.group(1)
    # 退化：production_path=true → 入口就是生产入口
    if case_input.get("production_path"):
        return None  # caller 自行处理
    return None


def _collect_real_path_regression(target: Path, content: str) -> Dict[str, Any]:
    """
    SK-EVAL-002 / v3.3.1 checker。
    验证 eval 路径与生产路径的重合度：测试 case 数量 ≠ 路径覆盖率。
    输出 fork_point（分叉点）+ blind_stages（盲区段）。

    evals/cases 路径从 target 派生（v3.3.1 移除冗余参数）。

    防递归：与 fallback_shadowing 同模式
    """
    ev = {
        "production_entry": None,
        "eval_entries": [],
        "fork_points": [],
        "blind_stages": [],
        "production_path_cases": 0,
        "synthetic_fixture_cases": 0,
        "coverage_assessment": None,
        "judgment_rule_applied": None,
    }

    if _is_reentrant_dryrun():
        ev["judgment_rule_applied"] = "嵌套调用防递归 → 跳过"
        return _wrap_real_path(ev)

    # 1. 识别生产入口（三级 heuristic）
    production_entry, entry_source = _extract_production_entry(content)
    ev["production_entry"] = production_entry
    ev["entry_source"] = entry_source

    # 2. 收集每个 eval case 的入口
    py_files = _get_py_files(target)
    cases_dir = target / "evals" / "cases"
    if cases_dir.is_dir():
        for case_sub in sorted(cases_dir.iterdir()):
            if not case_sub.is_dir():
                continue
            inp = case_sub / "input.json"
            if not inp.exists():
                continue
            try:
                spec = json.loads(inp.read_text(encoding="utf-8"))
            except Exception:
                continue
            is_prod_path = bool(spec.get("production_path"))
            if is_prod_path:
                ev["production_path_cases"] += 1
                eval_entry = production_entry  # production_path=true 走生产入口
            else:
                ev["synthetic_fixture_cases"] += 1
                eval_entry = _extract_eval_entry(spec, py_files) or "synthetic_fixture"
            ev["eval_entries"].append({
                "case": case_sub.name,
                "production_path": is_prod_path,
                "entry": eval_entry,
            })

    # 3. 计算 fork_point / blind_stages
    # fork_point = eval_entry 与 production_entry 第一次分叉的位置
    # 简化实现：production_entry 存在 + 至少一个非 production_path case → fork_point 在该 case 起点
    #          盲区段 = eval_entry 调用链 vs production_entry 调用链的差异部分
    non_prod = [e for e in ev["eval_entries"] if not e["production_path"]]
    if production_entry and non_prod:
        # 启发式：每个 non_prod 的 entry 与 production_entry 视为分叉
        for e in non_prod:
            if e["entry"] and e["entry"] != production_entry:
                ev["fork_points"].append({
                    "case": e["case"],
                    "from": production_entry,
                    "to": e["entry"],
                })
                # blind_stages = eval_entry 之后的链路（无法被生产路径覆盖）
                ev["blind_stages"].append({
                    "case": e["case"],
                    "stages": [e["entry"]],
                    "note": f"eval 走 {e['entry']}，生产路径走 {production_entry} → 盲区",
                })

    # 4. 评估
    if not production_entry:
        ev["coverage_assessment"] = "INCONCLUSIVE"
        ev["judgment_rule_applied"] = "无法识别生产入口（SKILL.md 无 def 块）"
    elif ev["production_path_cases"] == 0:
        ev["coverage_assessment"] = "FAIL"
        ev["judgment_rule_applied"] = (
            f"全部 {len(ev['eval_entries'])} 个 eval case 都走 synthetic fixture，无 production_path case → "
            f"测试覆盖度不可信（SK-EVAL-002 MUST violation）"
        )
    elif ev["fork_points"]:
        ev["coverage_assessment"] = "PARTIAL"
        ev["judgment_rule_applied"] = (
            f"生产入口 {production_entry} 被 {ev['production_path_cases']} 个 case 覆盖；"
            f"{len(ev['fork_points'])} 个 fork_point 形成盲区段"
        )
    else:
        ev["coverage_assessment"] = "PASS"
        ev["judgment_rule_applied"] = (
            f"所有 case 与生产入口 {production_entry} 重合，无盲区"
        )

    return _wrap_real_path(ev)


def _wrap_real_path(ev: dict) -> Dict[str, Any]:
    """统一输出契约."""
    assessment = ev.get("coverage_assessment")
    if assessment == "FAIL":
        verdict: Verdict = FAIL
    elif assessment == "PARTIAL":
        verdict: Verdict = WARN
    elif assessment == "PASS":
        verdict: Verdict = PASS
    else:
        verdict: Verdict = INCONCLUSIVE
    return {
        "evidence": ev,
        "verdict": verdict,
        "judgment_rule": (
            "production_path case 数 = 0 → FAIL（SK-EVAL-002 MUST violation）；"
            "存在 fork_point → WARN（盲区段需人工核对）；"
            "所有 case 与生产入口重合 → PASS；"
            "无法识别生产入口 → INCONCLUSIVE"
        ),
    }


# ============================================================
# v3.4 · package_engineering（包工程五件套线索）
# 外部对标：NVIDIA auto-ontology skill 套件（2026-11）——
#   skill 从"提示词便签"抬升为"带契约、带测试报告、带签名的软件交付物"。
#   本采集器只做线索采集（线索非断言，judge 自行判断），零误报优先。
# 输出（全部为"有/无+路径"事实，不做质量结论）：
#   contract_asset    : 机读 workflow 契约（含 workflows/artifacts/statuses/gates 的 yaml/json）
#   eval_report       : 出厂评测报告（BENCHMARK.md / EVALUATION.md / benchmark.*）
#   disclosure_card   : 披露卡（skill-card.md / SKILL_CARD.md：风险/依赖/凭证声明）
#   signature         : 包签名（*.sig / *.minisign / cosign 类文件）
#   kit_routing       : 套件路由入口（AGENTS.md 等含"用户动作→归属 skill"交接表）
#   live_source_principle : SKILL.md 声明"活真源"原则（运行时握手 > 抄录表）
# ============================================================

_CONTRACT_KEY_PATTERN = re.compile(
    r'^\s*(workflows|input_artifacts|output_artifacts|required_fields|statuses|gates)\s*:',
    re.MULTILINE,
)
_LIVE_SOURCE_PATTERN = re.compile(
    r'(trust the handshake|live source of truth|handshake.*(source of truth|tools)|'
    r'source of truth.*handshake|别把.*抄进|不要复制.*工具表|live.*tool list)',
    re.IGNORECASE,
)


def _collect_package_engineering(target: Path, content: str) -> Dict[str, Any]:
    """包工程五件套线索采集（v3.4，线索非断言）。"""
    ev: Dict[str, Any] = {
        "contract_asset": {"present": False, "paths": []},
        "eval_report": {"present": False, "paths": []},
        "disclosure_card": {"present": False, "paths": []},
        "signature": {"present": False, "paths": []},
        "kit_routing": {"present": False, "paths": []},
        "live_source_principle": {"present": False, "snippets": []},
    }
    try:
        all_files = [f for f in sorted(target.rglob("*")) if f.is_file() and not _is_noise(f)]
    except OSError:
        return {"evidence": ev, "judgment_rule": "目录不可读，跳过"}

    for f in all_files:
        try:
            rel = str(f.relative_to(target))
        except ValueError:
            continue
        name = f.name.lower()

        # 契约资产：assets/ 或根下的 yaml/json，内容含 >=2 个契约键
        if name.endswith((".yaml", ".yml", ".json")) and len(ev["contract_asset"]["paths"]) < 3:
            if "contract" in name or f.parent.name == "assets":
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")[:8000]
                    hits = set(m.group(1) for m in _CONTRACT_KEY_PATTERN.finditer(text))
                    if len(hits) >= 2:
                        ev["contract_asset"]["present"] = True
                        ev["contract_asset"]["paths"].append(
                            {"path": rel, "contract_keys": sorted(hits)}
                        )
                except OSError:
                    pass

        # 出厂评测报告
        if name in ("benchmark.md", "evaluation.md", "benchmark.txt", "evaluation-report.md"):
            ev["eval_report"]["present"] = True
            ev["eval_report"]["paths"].append(rel)

        # 披露卡
        if name in ("skill-card.md", "skill_card.md", "disclosure.md"):
            ev["disclosure_card"]["present"] = True
            ev["disclosure_card"]["paths"].append(rel)

        # 签名
        if name.endswith((".sig", ".signature", ".minisig")) or name in ("cosign.yaml", "provenance.json"):
            ev["signature"]["present"] = True
            ev["signature"]["paths"].append(rel)

        # 套件路由入口：AGENTS.md / INDEX.md / README.md 含交接表特征
        if name in ("agents.md", "index.md") and not ev["kit_routing"]["present"]:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")[:6000]
                # 交接表特征：表格行内含 skill 名指向（owning skill / 归属 / → `x-skill`）
                if re.search(r'(owning skill|归属.*skill|哪个 skill|handoff|交接)', text, re.IGNORECASE) \
                        and re.search(r'\|\s*[^|\n]+\s*\|\s*`?[a-z][a-z0-9-]{3,}`?\s*\|', text):
                    ev["kit_routing"]["present"] = True
                    ev["kit_routing"]["paths"].append(rel)
            except OSError:
                pass

    # 活真源原则（只看 SKILL.md 正文）
    for m in _LIVE_SOURCE_PATTERN.finditer(content):
        if len(ev["live_source_principle"]["snippets"]) < 3:
            s = max(0, m.start() - 40)
            ev["live_source_principle"]["snippets"].append(content[s:m.end() + 40].replace("\n", " "))
            ev["live_source_principle"]["present"] = True

    parts = [k for k, v in ev.items() if v.get("present")]
    return {
        "evidence": ev,
        "summary": f"五件套命中 {len(parts)}/5+1: {parts}",
        "judgment_rule": (
            "线索非断言。判分参考（评估闭环/结构合理性维度的证据补充）："
            "contract_asset 命中 → 流程产出物可机检的强证据（流程纪律-每步有产出 1.0 候选）；"
            "eval_report 命中 → 评测闭环-回归基线 1.0 候选（出厂带证据）；"
            "disclosure_card / signature 缺失不扣分——发布类/共享类 skill（C5 触发）缺失时在报告中列为改进建议；"
            "kit_routing 命中 → 多 skill 套件协作证据（触发设计-技能互斥 1.0 候选）；"
            "live_source_principle 命中 → 防 Policy-Runtime Drift 的自觉声明（正向信号）。"
        ),
    }


def _strip_for_summary(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """v3.4.1 --summary 模式：裁掉全文字段，只留结论+关键证据（judge 日常评审够用，省 token）。
    全量 JSON 仍可用默认模式取（回归断言依赖全量）。"""
    out = {k: v for k, v in bundle.items()
           if k not in ("skill_md_content", "skill_md_lines")}
    # 证据类字段里的长 snippets 截断
    def _trim(node):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if k in ("snippets", "samples", "context") and isinstance(v, list):
                    node[k] = [str(s)[:160] for s in v[:2]]
                elif k == "skill_md_excerpt" and isinstance(v, str):
                    node[k] = v[:200]
                else:
                    _trim(v)
        elif isinstance(node, list):
            for item in node:
                _trim(item)
    _trim(out)
    return out


def main():
    if len(sys.argv) < 2:
        print("用法: python3 score.py <target_skill_path> [--summary]")
        sys.exit(1)

    target = Path(sys.argv[1]).resolve()
    summary_mode = "--summary" in sys.argv[2:]
    if target.is_file():
        # 单文件模式：把 target 当 SKILL.md 解析
        fake_dir = target.parent
        skill_md = target
        content = skill_md.read_text(encoding="utf-8")
        bundle = _collect_from_content(fake_dir, skill_md, content)
    elif target.is_dir():
        bundle = collect_skill(target)
    else:
        print(f"路径不存在: {target}")
        sys.exit(1)
    if summary_mode:
        bundle = _strip_for_summary(bundle)
    print(json.dumps(bundle, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

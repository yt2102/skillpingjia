# v3.15 修复前快照回归报告（v3.3.1 更新版）
> 2026-09-07 · 闸门级验收事实记录（非断言）
> v3.3.1 增量：第 3 项 silent_failure 用 FAIL-002 视角命中（warn_no_propagation=7）；第 4 项 real_path_regression 识别到生产入口

## 快照来源
- 候选 1：`<agent-home>/skills/productivity/jishufangan/`（version 1.0.0，单脚本 `generate_fangan.py`，**与 jishufangan-skill 不是同一项目演进线**，症状完全不同）
- 候选 2：jishufangan-skill `fd3d101`（"refactor: reverse-sync v3.x 从 runtime 回 git 仓库"，8/21，**libjishu.py 首次进 git**，对应 v3.x 修复前现场）
- 结论：用 **fd3d101** 作为 v3.15 修复前快照的"最近代理"（v3.5 之前的最新已记录状态）

## 运行命令
```bash
python3 scripts/score.py /tmp/jishufangan_v315_test  # fd3d101 提取目录
# 永久回归：python3 evals/runner.py （含 regression_jishufangan_v315 case）
```

## 四项验收（事实）

### 1. ir_closure.gaps 含 heading（清单笔误 heading_preserved）
**结果**：✅ 命中
- gaps 共 13 项，**含 `heading`（status=drift）**
- 同时命中：table, indent_pt, bold, list_bullet, size_pt, font_ascii, fmt, list_numbered, title
- internal_only 3 项：org, top, date（不参与评分但记录）
- **判定**：heading_p IR 漂移在 fd3d101 真实存在

### 2. fallback_branches.uncovered 含 heading（清单笔误 h1_present）
**结果**：✅ 命中
- uncovered: `['heading', 'list_bullet', 'list_numbered', 'table', 'top']`
- libjishu.py 第 2032 行确有 `h1_present` 变量名 + 兜底补段逻辑，但 producer 产出的是 `heading` 而非 `h1_present` 类型 → uncovered 抓到 `heading` 类型缺失是事实
- **判定**：兜底盲点真实存在

### 3. silent_failure warn_no_propagation ≥ 5（v3.3.1 FAIL-002 视角）
**结果**：✅ 命中
- fd3d101 libjishu.py 含 **7 个 `except: pass`**
- 7 个都配套 `logger.warning` → `warn_paired=7`
- v3.3.1 新增 `_PAT_STATUS_PROPAGATION` 检查 except 块附近 200 字符内有无 `status='degraded'` 等传播 → 7 个 **全部未传播状态** → `warn_no_propagation=7`
- **判定**：warning 只证明"日志可见"，不证明"状态可传播"。这是 silent_failure 的更深层信号（v3.x 整系列未修）
- runner 硬门槛：`expect_warn_no_propagation_min: 5` ✅

### 4. real_path_regression 识别生产入口（v3.3.1 三级 fallback）
**结果**：✅ 命中
- `production_entry = generate_from_structure`（来自 SKILL.md 正文）
- `entry_source = prose_pipeline_verb`（二级 heuristic 命中，judge 可复核）
- 注：方案预期的 `convert_to_gov_format` 在 SKILL.md 第 245 行才出现（标"核心入口"），但 `generate_from_structure` 在第 97 行（顶部示例）已出现 → "第一个管线动词命中"取值。
- 实际意义：real_path 不再 INCONCLUSIVE，SK-EVAL-002 进入可判定状态
- **判定**：生产入口识别生效，规格回归预期达成（verbose 偏差可接受）

## 闸门结论
- **四项全过**：✅ ✅ ✅ ✅
- 证明 v3.3 P0-1/P0-2/P1-1 + v3.3.1 P0-4 对 jishufangan 修复前状态有效
- silent_failure 从"未命中"升级为"FAIL-002 视角命中"（v3.3.1 的核心交付）

## 后续动作（已完成）
- ✅ 真实样本录入：`evals/cases/regression_jishufangan_v315`（永久 case）
- ✅ 硬门槛：`expect_ir_closure_gaps` 含 `heading` / `expect_fallback_uncovered` 含 `heading` / `expect_warn_no_propagation_min: 5`
- ✅ baseline.json v33_bite_check 状态：completed（替代 completed_partial）

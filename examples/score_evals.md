# skillpingjia · 自测用例

修改本 skill 后运行以下 3 个用例验证。

## 用例 1：正面样本（正常 skill）

- 对象：`evals/cases/regression_jishufangan_v315`（包内真实事故 fixture）
- 断言：
  - 报告含全部 7 个维度分数行
  - ir_closure 抓出 `heading` 类型漂移（该 fixture 的已知缺陷）
  - fallback_branches.uncovered 含 `heading`

## 用例 2：负面样本（无 frontmatter）

- 对象：构造一个无 YAML frontmatter 的 SKILL.md（正文直接 `# test` 开头）
- 断言：
  - H1 判 ❌
  - 总分 <60（不合格）
  - 报告中「硬门槛」行标注失败项

## 用例 3：边界样本（500 行整）

- 对象：SKILL.md 恰好 500 行（含 frontmatter）
- 断言：H2 判 ❌（规范是 <500 行，500 整即超标），判定可复现

## 运行方式

- 读取本文件 → 对每个样本执行评分流程 → 对照断言逐条核对
- 全部通过 = ✅；任一失败 = 定位维度 → 修复 → 重跑


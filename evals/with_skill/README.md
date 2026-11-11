# with_skill 对照（带 skill 运行）

> 评估闭环 · with/without 对照的「带 skill」侧记录。

## 对照方法（源自 k12 讲义 3.7 官方评测流程）

1. 取 2-3 个真实测试 prompt（同一批 prompt 双跑）
2. 本目录：带 skill 的 subagent 输出
3. `../without_skill/`：不带 skill 的 subagent 输出（同 prompt、同时启动）
4. 对比展示：skill 到底加了多少分

## 判定

带不带 skill 没差别 → 该 skill 没有存在价值。

## 记录格式（每次对照后追加）

```
日期: YYYY-MM-DD
模型: xxx
Prompt: ...
带 skill 结果: [摘要 + 关键产出]
不带 skill 结果: [摘要 + 关键产出]
差异: [量化对比]
结论: [有/无存在价值]
```

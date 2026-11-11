# jishufangan 评分 rubrics

> 判分依据：P/R/O/M 四维（源自 k12 讲义 3.7）
> - P（专业度）：符合广州市政务规范 2025 版格式
> - R（严谨度）：structure.json 可独立校验；validate_output 24 项通过
> - O（输出）：docx 可编辑、结构完整、字体/编号/表格符合规范
> - M（脚手架）：降级路径明确（字体缺失/依赖缺失 → 声明不静默）

## 判定原则
1. 带不带 skill 没差别 → 没有存在价值（with/without 对照）
2. 每次修改后跑 evals + validate_output 验证

---
name: contract_drift
description: "Contract drift fixture: parser 产出 heading_p，save 的 allowed_types 缺它（v3.3 P0-1 应抓出）。"
---

# Contract Drift Fixture

最小 python skill，刻意制造 **IR 全链路双向闭合** 的 contract drift：

- `parser.py`：产出 `('heading_p', ...)` 类型（producer）
- `save.py`：`ALLOWED_TYPES = {'heading', 'body'}` —— **没有 heading_p**（consumer 不认）
- `renderer.py`：靠 `typ in ('heading', 'body')` 兜底分支判断类型（consumer 也不认 heading_p）

期望：pingjia v3.3 的 `_collect_ir_closure()` 能识别 drift，产出 gap `heading_p`。
---
name: blind_fallback
description: "Blind fallback fixture: parser 产出 h1_present，renderer 的 elif typ in (...) 兜底缺它（v3.3 P1-1 应抓出）。"
---

# Blind Fallback Fixture

最小 python skill，刻意制造 **兜底分支触发审计**盲点：

- `parser.py`：产出 `('h1_present', bool)` 类型（producer）
- `renderer.py`：用 `elif typ in ('body', 'list_bullet', 'table'):` 兜底（**不含 h1_present**）

期望：pingjia v3.3 的 `_collect_fallback_branches()` 能识别 uncovered = `['h1_present']`。
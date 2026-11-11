"""Contract drift fixture · consumer 部分：renderer 兜底接受 heading_p（关键 drift 点）。"""


def renderer(items):
    """Consumer B: 渲染兜底分支含 heading_p（与 save 形成 partial drift）。"""
    out = []
    for typ, *rest in items:
        if typ == 'heading':
            out.append(f'<h1>{rest[0]}</h1>')
        elif typ in ('heading_p', 'body'):  # 关键：接受 heading_p，但 save 拒绝 → drift
            out.append(f'<{typ}>{rest[0]}</{typ}>')
    return out

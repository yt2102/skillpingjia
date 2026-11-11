"""Contract drift fixture · consumer 部分：save 拒绝 heading_p（关键 drift 点）。"""

ALLOWED_TYPES = {'heading', 'body'}  # 关键：缺 'heading_p' → 与 renderer 形成 partial drift


def save(items, path):
    """Consumer A: 序列化时拒绝 heading_p。"""
    out = []
    for typ, *rest in items:
        if typ not in ALLOWED_TYPES:  # producer 产出 heading_p 会 raise
            raise ValueError(f'Unknown type: {typ}')
        out.append((typ, *rest))
    with open(path, 'w') as f:
        for item in out:
            f.write(f'{item}\n')

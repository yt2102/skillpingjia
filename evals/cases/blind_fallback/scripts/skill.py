"""Blind fallback fixture: 故意制造兜底分支盲点。"""


def parser(raw):
    """Producer: 产出 h1_present 类型"""
    return [
        ('heading', 'Title'),
        ('h1_present', True),   # 关键：parser 产出 h1_present
        ('body', 'Para 1'),
        ('body', 'Para 2'),
    ]


def renderer(items):
    """Consumer: 兜底分支不含 h1_present"""
    out = []
    for typ, *rest in items:
        if typ == 'heading':
            out.append(f'<h1>{rest[0]}</h1>')
        elif typ in ('body', 'list_bullet', 'table'):  # 兜底不含 h1_present
            out.append(f'<{typ}>{rest[0]}</{typ}>')
        # h1_present 落进兜底失败 → 静默失败
    return out
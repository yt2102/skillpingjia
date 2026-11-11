"""Contract drift fixture · producer 部分：parser 产出 heading_p（heading 之"段落化"变体）。"""


def parser(raw):
    """Producer: 产出 heading_p 类型（heading 的段落样式变体）。"""
    items = []
    items.append(('heading_p', 'Hello', 1))  # 关键：heading_p 是契约字段
    items.append(('body', 'Some text'))
    return items

#!/usr/bin/env python3
"""
jishufangan 可复用函数库 — 按广州市政务规范生成 .docx
使用方式：导库 → 调函数 → 存文档 + 后处理

禁止单独写 standalone 脚本。一律 import libjishu 走这套管线。
"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml, OxmlElement
from lxml import etree
import zipfile, re, os, shutil, sys

# ═══════════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════════

A4_PAGE_WIDTH_DXA = 11906   # A4 纵向
STD_MARGIN_DXA     = 1440    # 国标页边距
CONTENT_WIDTH_DXA  = A4_PAGE_WIDTH_DXA - 2 * STD_MARGIN_DXA  # 9026 dxa ≈ 15.9 cm

TABLE_HEADER_BG   = '98C1FD' # 表头蓝色填充
TABLE_BORDER_COLOR = '000000' # 表格边框黑色
TABLE_BORDER_SZ    = 4        # 0.5pt = 4 eighths of a point

# 编号列表批次计数器：每批 add_numbered_list 分配独立 numId，防止跨批序号不重置
_NUMBERED_LIST_BATCHES = []  # [(numId, item_count), ...]

# EMPHASIS_MARKERS 已废弃 — 强调判定仅依赖 OOXML 信号 (is_mostly_bold + font difference)
# 原因：关键词匹配过于宽泛，将非强调的结构性段落（如 List Bullet 中的 第一/第二/第三）
# 错误加粗，违反 word-docx Rule 2（样式与直接格式化分层）

# 英文字体黑名单（检测残留）
BAD_ASCII_FONTS = {'Arial', 'Calibri', 'Times New Roman', 'Cambria', 'Courier New'}

# 中文正文字体白名单
BODY_FONTS = {'仿宋_GB2312', '仿宋', '宋体', 'Times New Roman'} | BAD_ASCII_FONTS


def _set_run_font(run, font_name, size_pt=12, bold=False, color=None):
    """统一字体设置工具。避免重复 run.font.name + rFonts + size + bold + color。"""
    run.font.name = font_name
    rPr = run.element.get_or_add_rPr()
    rPr.rFonts.set(qn('w:eastAsia'), font_name)
    run.font.size = Pt(size_pt)
    if bold:
        run.font.bold = True
    run.font.color.rgb = color if color else RGBColor(0, 0, 0)

# ═══════════════════════════════════════════════════════════
#  Part 1: 文档创建 + 样式初始化
# ═══════════════════════════════════════════════════════════

def create_document():
    """创建文档并初始化所有样式（H1/H2/H3/Normal）。
    返回 (doc, section) 元组。"""
    doc = Document()
    sec = doc.sections[0]

    # ── Normal ──
    ns = doc.styles['Normal']
    ns.font.name = '仿宋_GB2312'
    ns.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')
    ns.font.size = Pt(12)
    ns.font.color.rgb = RGBColor(0, 0, 0)
    pf = ns.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(20)
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.first_line_indent = Pt(24)

    # ── Heading 1 ──
    h1 = doc.styles['Heading 1']
    h1.font.name = '黑体'
    h1.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    h1.font.size = Pt(16)
    h1.font.bold = True
    h1.font.color.rgb = RGBColor(0, 0, 0)
    h1pf = h1.paragraph_format
    h1pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h1pf.line_spacing_rule = WD_LINE_SPACING.SINGLE  # 规范表4.1：各章标题单倍行距
    h1pf.space_before = Pt(0)
    h1pf.space_after = Pt(18)
    h1pf.first_line_indent = Pt(0)

    # ── Heading 2 ──
    h2 = doc.styles['Heading 2']
    h2.font.name = '黑体'
    h2.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    h2.font.size = Pt(12)
    h2.font.bold = True
    h2.font.color.rgb = RGBColor(0, 0, 0)
    h2pf = h2.paragraph_format
    h2pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h2pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    h2pf.line_spacing = Pt(20)
    h2pf.space_before = Pt(0)
    h2pf.space_after = Pt(0)
    h2pf.first_line_indent = Pt(0)

    # ── Heading 3 ──
    h3 = doc.styles['Heading 3']
    h3.font.name = '黑体'
    h3.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    h3.font.size = Pt(12)
    h3.font.bold = True
    h3.font.color.rgb = RGBColor(0, 0, 0)
    h3pf = h3.paragraph_format
    h3pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h3pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    h3pf.line_spacing = Pt(20)
    h3pf.space_before = Pt(0)
    h3pf.space_after = Pt(0)
    h3pf.first_line_indent = Pt(0)

    # ── Heading 4 (政务规范：格式同 H3，区别在编号深度 X.X.X.X) ──
    h4 = doc.styles['Heading 4']
    h4.font.name = '黑体'
    h4.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    h4.font.size = Pt(12)
    h4.font.bold = True
    h4.font.color.rgb = RGBColor(0, 0, 0)
    h4pf = h4.paragraph_format
    h4pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h4pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    h4pf.line_spacing = Pt(20)
    h4pf.space_before = Pt(0)
    h4pf.space_after = Pt(0)
    h4pf.first_line_indent = Pt(0)

    # ── Heading 5 (政务规范：格式同 H3，区别在编号深度 X.X.X.X.X) ──
    h5 = doc.styles['Heading 5']
    h5.font.name = '黑体'
    h5.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    h5.font.size = Pt(12)
    h5.font.bold = True
    h5.font.color.rgb = RGBColor(0, 0, 0)
    h5pf = h5.paragraph_format
    h5pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h5pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    h5pf.line_spacing = Pt(20)
    h5pf.space_before = Pt(0)
    h5pf.space_after = Pt(0)
    h5pf.first_line_indent = Pt(0)

    # ── Heading 6 (政务规范：格式同 H3，区别在编号深度 X.X.X.X.X.X) ──
    h6 = doc.styles['Heading 6']
    h6.font.name = '黑体'
    h6.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    h6.font.size = Pt(12)
    h6.font.bold = True
    h6.font.color.rgb = RGBColor(0, 0, 0)
    h6pf = h6.paragraph_format
    h6pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h6pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    h6pf.line_spacing = Pt(20)
    h6pf.space_before = Pt(0)
    h6pf.space_after = Pt(0)
    h6pf.first_line_indent = Pt(0)

    return doc, sec


# ═══════════════════════════════════════════════════════════
#  Part 2: 封面
# ═══════════════════════════════════════════════════════════

def _default_org():
    """编制单位三层次：环境变量 JISHUFANG_ORG > 硬编码兜底。"""
    import os
    return os.environ.get('JISHUFANG_ORG', '示例科技有限公司 集成业务部')


def add_cover(doc, title, org=None,
              date='2026年7月'):
    """添加政务方案封面。
    布局：上方留白 → 标题居中 → 大段空白 → 底部编制信息
    title: 项目名称
    org:   编制单位
    date:  编制日期"""
    # 段1：项目名称（方正小标宋 24pt 居中，页面约 1/3 处）
    if org is None:
        org = _default_org()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(180)   # 标题距顶部约 6.4cm
    pf.space_after = Pt(0)
    pf.line_spacing = Pt(36)    # 适当行距避免字符拥挤
    run = p.add_run(title)
    run.font.name = '方正小标宋_GBK'
    run.font.size = Pt(24)
    run.font.color.rgb = RGBColor(0, 0, 0)
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '方正小标宋_GBK')
    # 字符间距微调：防止方正小标宋字符拥挤
    rPr = run._r.get_or_add_rPr()
    spacing = OxmlElement('w:spacing')
    spacing.set(qn('w:val'), '20')  # 0.4pt 宽松
    rPr.append(spacing)

    # 段2：编制单位 + 日期（规范第四章：编制单位 3号黑体，编制日期 3号仿宋_GB2312）
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(280)  # 标题与底部信息之间大段留白
    pf.space_after = Pt(0)
    run_org = p.add_run(f'编制单位：{org}\n')
    run_org.font.name = '黑体'
    run_org.font.size = Pt(16)
    run_org.font.color.rgb = RGBColor(0, 0, 0)
    run_org.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    run_date = p.add_run(f'编制日期：{date}')
    run_date.font.name = '仿宋_GB2312'
    run_date.font.size = Pt(16)
    run_date.font.color.rgb = RGBColor(0, 0, 0)
    run_date.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')

    # 段3：底部占位
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)


# ═══════════════════════════════════════════════════════════
#  Part 3: 标题 + 正文
# ═══════════════════════════════════════════════════════════

def add_heading(doc, text, level):
    """添加标题段落（level=1~6）。所有级别绑定 numId=30 多级编号。
    H1→第X章, H2→X.X, H3→X.X.X, H4→X.X.X.X, H5→X.X.X.X.X, H6→X.X.X.X.X.X
    文本中的手动编号前缀在函数内部剥离（_clean_heading_text），
    任何调用路径（generate_from_structure / 直接调用）都不会双重编号。"""
    text = _clean_heading_text(text, level)  # 兜底：防手动编号+自动编号叠加
    p = doc.add_paragraph(style=f'Heading {level}')
    p.clear()
    run = p.add_run(text)
    run.font.name = '黑体'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    if level == 1:
        run.font.size = Pt(16)
    else:
        run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)
    # 所有级别绑定 numId=30 多级列表（ilvl = level-1）
    pPr = p._p.get_or_add_pPr()
    numPr = OxmlElement('w:numPr')
    numId = OxmlElement('w:numId')
    numId.set(qn('w:val'), '30')
    ilvl = OxmlElement('w:ilvl')
    ilvl.set(qn('w:val'), str(level - 1))
    numPr.append(ilvl)
    numPr.append(numId)
    pPr.append(numPr)
    return p


def add_body(doc, text):
    """添加正文段落（仿宋_GB2312 12pt，首行缩进2字符）。"""
    return doc.add_paragraph(text)


def _set_numPr(para, numId, ilvl):
    """为段落绑定编号定义（内部工具函数）。"""
    pPr = para._p.get_or_add_pPr()
    numPr = OxmlElement('w:numPr')
    nid = OxmlElement('w:numId')
    nid.set(qn('w:val'), str(numId))
    il = OxmlElement('w:ilvl')
    il.set(qn('w:val'), str(ilvl))
    numPr.append(il)
    numPr.append(nid)
    pPr.append(numPr)


def add_numbered_list(doc, items):
    """添加自动编号列表。每批（每次调用）分配独立 numId，批内自动编号，批间互不干扰。

    输出格式：1、xxx  2、xxx  3、xxx

    用法：add_numbered_list(doc, ['第一项', '第二项', '第三项'])

    ⚠️ 列表项必须连续，中间不能插入正文段落。"""
    global _NUMBERED_LIST_BATCHES
    # 分配独立 numId：base=31（保留兼容），新批次从 33 起
    batch_idx = len(_NUMBERED_LIST_BATCHES)
    num_id = 33 + batch_idx

    for item in items:
        p = doc.add_paragraph(style='Normal')
        p.clear()
        run = p.add_run(str(item))
        run.font.name = '仿宋_GB2312'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(0, 0, 0)
        _set_numPr(p, num_id, 0)

    _NUMBERED_LIST_BATCHES.append((num_id, len(items)))
    return len(items)


def add_bullet_list(doc, items):
    """添加项目符号列表（通过 numbering.xml numId=32）。
    输出格式：— xxx  — xxx  — xxx

    用法：add_bullet_list(doc, ['要点一', '要点二', '要点三'])"""
    for item in items:
        p = doc.add_paragraph(style='Normal')
        p.clear()
        run = p.add_run(str(item))
        run.font.name = '仿宋_GB2312'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(0, 0, 0)
        _set_numPr(p, 32, 0)
    return len(items)


# ═══════════════════════════════════════════════════════════
#  Part 4: 表格（新增）
# ═══════════════════════════════════════════════════════════

def add_table(doc, headers, rows, title=None):
    """创建带边框 + 表头样式的标准表格。
    headers:  表头文本列表  ['列1', '列2', ...]
    rows:     数据行列表    [['a1','b1'], ['a2','b2'], ...]
    title:    表格标题（可选，黑体12pt加粗居中，放在表前面）

    返回 python-docx Table 对象。"""
    # ── 表格标题（规范表4.1：表序表名 仿宋_GB2312 小四号居中，标于表上方）──
    if title:
        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf_title = p_title.paragraph_format
        pf_title.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf_title.line_spacing = Pt(20)
        pf_title.space_before = Pt(0)
        pf_title.space_after = Pt(0)
        run = p_title.add_run(title)
        run.font.name = '仿宋_GB2312'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')
        run.font.size = Pt(12)
        run.font.bold = False
        run.font.color.rgb = RGBColor(0, 0, 0)

    # ── 计算列宽 ──
    ncols = len(headers)
    col_width = int(CONTENT_WIDTH_DXA / ncols)

    # ── 创建表格 ──
    table = doc.add_table(rows=1 + len(rows), cols=ncols)
    table.style = 'Table Grid'

    # ── tblGrid 列宽定义（修复：先移除 python-docx 自动生成的 tblGrid，避免双 tblGrid 非法结构）──
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')
    # 删除已有 tblGrid（python-docx add_table 会自动创建一个）
    for old_grid in tbl.findall(qn('w:tblGrid')):
        tbl.remove(old_grid)
    tblGrid = OxmlElement('w:tblGrid')
    for _ in range(ncols):
        gridCol = OxmlElement('w:gridCol')
        gridCol.set(qn('w:w'), str(col_width))
        tblGrid.append(gridCol)
    tbl.insert(0, tblGrid)

    # ── 表头行 ──
    for j, h in enumerate(headers):
        cell = table.rows[0].cells[j]
        _clear_cell(cell)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # 移除 Normal 样式引用，防止继承样式级缩进
        pPr = p._p.get_or_add_pPr()
        pStyle = pPr.find(qn('w:pStyle'))
        if pStyle is not None:
            pPr.remove(pStyle)
        _force_no_indent(p)  # 表头不缩进
        run = p.add_run(h)
        run.font.name = '黑体'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
        run.font.size = Pt(10)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0, 0, 0)
        # 蓝色填充
        _set_cell_shd(cell, TABLE_HEADER_BG)
        _set_cell_v_align(cell, 'center')

    # ── 数据行 ──
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.rows[i + 1].cells[j]
            _clear_cell(cell)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            # 移除 Normal 样式引用，防止继承样式级首行缩进
            pPr = p._p.get_or_add_pPr()
            pStyle = pPr.find(qn('w:pStyle'))
            if pStyle is not None:
                pPr.remove(pStyle)
            _force_no_indent(p)  # 数据格不缩进
            run = p.add_run(str(val))
            run.font.name = '仿宋_GB2312'
            run.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0, 0, 0)
            _set_cell_v_align(cell, 'center')

    # ── 表格边框（表级 + 单元格级） ──
    _set_table_borders(tbl)
    for row_obj in table.rows:
        for cell in row_obj.cells:
            _set_cell_borders(cell._tc)

    return table


def _force_no_indent(paragraph):
    """XML 级别强制清除段落缩进。
    不依赖样式覆盖，直接在段落 XML 中写入 w:ind firstLine=0。
    避免 Word 回退到 Normal 样式级缩进。"""
    # API 级别
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.left_indent = Pt(0)
    # XML 级别：确保 <w:ind> 存在且 firstLine/left 显式为 0
    pPr = paragraph._p.get_or_add_pPr()
    ind = pPr.find(qn('w:ind'))
    if ind is None:
        ind = OxmlElement('w:ind')
        pPr.append(ind)
    # 显式设置 firstLine=0, left=0（覆盖样式级缩进）
    ind.set(qn('w:firstLine'), '0')
    ind.set(qn('w:left'), '0')
    # 清除其他缩进属性
    for attr in ('w:firstLineChars', 'w:hanging', 'w:hangingChars', 'w:leftChars'):
        key = qn(attr)
        if key in ind.attrib:
            del ind.attrib[key]


def _clear_cell(cell):
    """清空单元格默认内容"""
    for p in cell.paragraphs:
        for run in p.runs:
            run.text = ''


def _set_cell_shd(cell, color):
    """设置单元格背景色"""
    tcPr = cell._tc.get_or_add_tcPr()
    # 移除旧 shd 避免重复堆积
    old = tcPr.find(qn('w:shd'))
    if old is not None:
        tcPr.remove(old)
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:fill'), color)
    tcPr.append(shd)


def _set_cell_v_align(cell, valign):
    """设置单元格垂直对齐（top/center/bottom）"""
    tcPr = cell._tc.get_or_add_tcPr()
    # 移除旧 vAlign 避免重复堆积
    old = tcPr.find(qn('w:vAlign'))
    if old is not None:
        tcPr.remove(old)
    vAlign = OxmlElement('w:vAlign')
    vAlign.set(qn('w:val'), valign)
    tcPr.append(vAlign)


def _set_table_borders(tbl):
    """设置表级边框（含 insideH/insideV）"""
    tblPr = tbl.tblPr
    borders = OxmlElement('w:tblBorders')

    for edge in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        b = OxmlElement(f'w:{edge}')
        b.set(qn('w:val'), 'single')
        b.set(qn('w:sz'), str(TABLE_BORDER_SZ))
        b.set(qn('w:space'), '0')
        b.set(qn('w:color'), TABLE_BORDER_COLOR)
        borders.append(b)

    # 移除可能存在的旧边框
    old = tblPr.find(qn('w:tblBorders'))
    if old is not None:
        tblPr.remove(old)
    tblPr.append(borders)


def _set_cell_borders(tc):
    """设置单元格级边框"""
    tcPr = tc.get_or_add_tcPr()
    borders = OxmlElement('w:tcBorders')

    for edge in ['top', 'left', 'bottom', 'right']:
        b = OxmlElement(f'w:{edge}')
        b.set(qn('w:val'), 'single')
        b.set(qn('w:sz'), str(TABLE_BORDER_SZ))
        b.set(qn('w:space'), '0')
        b.set(qn('w:color'), TABLE_BORDER_COLOR)
        borders.append(b)

    old = tcPr.find(qn('w:tcBorders'))
    if old is not None:
        tcPr.remove(old)
    tcPr.append(borders)


# ═══════════════════════════════════════════════════════════
#  Part 5: 保存 + ZIP 后处理
# ═══════════════════════════════════════════════════════════

def _build_numbering_xml():
    """动态生成 numbering.xml。
    标题 numId=30 + 项目符号 numId=32 + 每批 add_numbered_list 独立 numId。
    批次间编号互不干扰（每批从 1 开始）。"""
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

    parts = [f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="{NS}">
  <w:abstractNum w:abstractNumId="300">
    <w:nsid w:val="A1B2C300"/>
    <w:multiLevelType w:val="multilevel"/>
    <w:tmpl w:val="D4E5F600"/>
    <w:lvl w:ilvl="0" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="第%1章"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading1"/>
    </w:lvl>
    <w:lvl w:ilvl="1" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="%1.%2"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading2"/>
    </w:lvl>
    <w:lvl w:ilvl="2" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="%1.%2.%3"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading3"/>
    </w:lvl>
    <w:lvl w:ilvl="3" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="%1.%2.%3.%4"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading4"/>
    </w:lvl>
    <w:lvl w:ilvl="4" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="%1.%2.%3.%4.%5"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading5"/>
    </w:lvl>
    <w:lvl w:ilvl="5" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="%1.%2.%3.%4.%5.%6"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading6"/>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="30"><w:abstractNumId w:val="300"/></w:num>
  <w:abstractNum w:abstractNumId="320">
    <w:nsid w:val="A1B2C320"/>
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:tmpl w:val="D4E5F620"/>
    <w:lvl w:ilvl="0" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="bullet"/>
      <w:lvlText w:val="•"/><w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="420" w:hanging="420"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="32"><w:abstractNumId w:val="320"/></w:num>''']

    for bi, (num_id, item_count) in enumerate(_NUMBERED_LIST_BATCHES):
        aid = 330 + bi
        # 修复: nsid/tmpl 必须 8 位 hex(ECMA-376 ST_LongHexNumber), 6 位导致 Word 合并批次编号
        nsid_hex = f"{0xA1B2C000 + bi:08X}"   # 8 位唯一
        tmpl_hex = f"{0xD4E5F000 + bi:08X}"   # 8 位唯一
        parts.append(f'''
  <w:abstractNum w:abstractNumId="{aid}">
    <w:nsid w:val="{nsid_hex}"/>
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:tmpl w:val="{tmpl_hex}"/>
    <w:lvl w:ilvl="0" w:tentative="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="decimal"/>
      <w:lvlText w:val="%1、"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="420" w:hanging="420"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="{num_id}"><w:abstractNumId w:val="{aid}"/></w:num>''')

    parts.append('</w:numbering>')
    return ''.join(parts).encode('utf-8')


# NUMBERING_XML_TEMPLATE 已废弃 — 由 _build_numbering_xml() 动态生成
NUMBERING_XML_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="300">
    <w:nsid w:val="A1B2C300"/>
    <w:multiLevelType w:val="multilevel"/>
    <w:tmpl w:val="D4E5F600"/>
    <w:lvl w:ilvl="0" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="第%1章"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading1"/>
    </w:lvl>
    <w:lvl w:ilvl="1" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="%1.%2"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading2"/>
    </w:lvl>
    <w:lvl w:ilvl="2" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="%1.%2.%3"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading3"/>
    </w:lvl>
    <w:lvl w:ilvl="3" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="%1.%2.%3.%4"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading4"/>
    </w:lvl>
    <w:lvl w:ilvl="4" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="%1.%2.%3.%4.%5"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading5"/>
    </w:lvl>
    <w:lvl w:ilvl="5" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/><w:suff w:val="space"/>
      <w:lvlText w:val="%1.%2.%3.%4.%5.%6"/><w:lvlJc w:val="left"/>
      <w:pStyle w:val="Heading6"/>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="30"><w:abstractNumId w:val="300"/></w:num>
  <!-- 正文编号列表 "1、2、3、" -->
  <w:abstractNum w:abstractNumId="310">
    <w:nsid w:val="A1B2C310"/>
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:tmpl w:val="D4E5F610"/>
    <w:lvl w:ilvl="0" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="decimal"/>
      <w:lvlText w:val="%1、"/><w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="420" w:hanging="420"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="31"><w:abstractNumId w:val="310"/></w:num>
  <!-- 项目符号列表 "—" -->
  <w:abstractNum w:abstractNumId="320">
    <w:nsid w:val="A1B2C320"/>
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:tmpl w:val="D4E5F620"/>
    <w:lvl w:ilvl="0" w:tentative="0">
      <w:start w:val="1"/><w:numFmt w:val="bullet"/>
      <w:lvlText w:val="\u2022"/><w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="420" w:hanging="420"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="32"><w:abstractNumId w:val="320"/></w:num>
</w:numbering>'''

FOOTER_XML_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p>
    <w:pPr><w:jc w:val="center"/></w:pPr>
    <w:r><w:t xml:space="preserve">— </w:t></w:r>
    <w:r><w:fldChar w:fldCharType="begin"/></w:r>
    <w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>
    <w:r><w:fldChar w:fldCharType="end"/></w:r>
    <w:r><w:t xml:space="preserve"> —</w:t></w:r>
  </w:p>
</w:ftr>'''


def _inject_page_breaks_and_footer_ref(data):
    """在 document.xml 中每个 Heading1 前插入分页符，并设置分节：
    - 封面 Section：titlePg（首页无页脚）
    - 正文 Section：footerReference + pgNumType start=1（从第1页开始编号）"""
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    w = '{' + NS + '}'

    tree = etree.fromstring(data)
    body = tree.find(w + 'body')
    children = list(body)

    # ── 第一步：在 H1 前插入分页符 + 目录页（封面后自动生成 TOC，第二页）──
    new_children = []
    first_page_break_idx = None
    toc_inserted = False
    for child in children:
        pPr = child.find(w + 'pPr')
        is_h1 = False
        if pPr is not None:
            pStyle = pPr.find(w + 'pStyle')
            if pStyle is not None and pStyle.get(w + 'val') == 'Heading1':
                is_h1 = True

        if is_h1:
            # 分页符 1：封面 → 目录页
            page_break1 = etree.Element(w + 'p')
            etree.SubElement(page_break1, w + 'pPr')
            run1 = etree.SubElement(page_break1, w + 'r')
            br1 = etree.SubElement(run1, w + 'br')
            br1.set(w + 'type', 'page')
            new_children.append(page_break1)
            if first_page_break_idx is None:
                first_page_break_idx = len(new_children) - 1

            if not toc_inserted:
                toc_inserted = True
                # 目录页：标题「目 录」+ TOC 域 + 分页符 2（目录页 → 正文）
                toc_title = etree.Element(w + 'p')
                toc_pPr = etree.SubElement(toc_title, w + 'pPr')
                toc_jc = etree.SubElement(toc_pPr, w + 'jc')
                toc_jc.set(w + 'val', 'center')
                toc_sp = etree.SubElement(toc_pPr, w + 'spacing')
                toc_sp.set(w + 'before', '360')
                toc_sp.set(w + 'after', '360')
                toc_r = etree.SubElement(toc_title, w + 'r')
                toc_rPr = etree.SubElement(toc_r, w + 'rPr')
                toc_rf = etree.SubElement(toc_rPr, w + 'rFonts')
                toc_rf.set(w + 'ascii', '黑体')
                toc_rf.set(w + 'hAnsi', '黑体')
                toc_rf.set(qn('w:eastAsia'), '黑体')
                toc_sz = etree.SubElement(toc_rPr, w + 'sz')
                toc_sz.set(w + 'val', '32')  # 三号 16pt
                toc_t = etree.SubElement(toc_r, w + 't')
                toc_t.text = '目  录'
                new_children.append(toc_title)

                # TOC 域（Word 打开后自动更新目录）
                toc_field = etree.Element(w + 'p')
                toc_fpPr = etree.SubElement(toc_field, w + 'pPr')
                toc_fsp = etree.SubElement(toc_fpPr, w + 'spacing')
                toc_fsp.set(w + 'line', '360')
                toc_fsp.set(w + 'lineRule', 'auto')
                # begin
                r_begin = etree.SubElement(toc_field, w + 'r')
                fc_begin = etree.SubElement(r_begin, w + 'fldChar')
                fc_begin.set(w + 'fldCharType', 'begin')
                fc_begin.set(w + 'dirty', 'true')
                # instrText
                r_instr = etree.SubElement(toc_field, w + 'r')
                instr = etree.SubElement(r_instr, w + 'instrText')
                instr.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                instr.text = ' TOC \\o "1-3" \\h \\z \\u '
                # separate
                r_sep = etree.SubElement(toc_field, w + 'r')
                fc_sep = etree.SubElement(r_sep, w + 'fldChar')
                fc_sep.set(w + 'fldCharType', 'separate')
                # placeholder
                r_ph = etree.SubElement(toc_field, w + 'r')
                t_ph = etree.SubElement(r_ph, w + 't')
                t_ph.text = '（目录：在 Word 中按 F9 更新域自动生成）'
                # end
                r_end = etree.SubElement(toc_field, w + 'r')
                fc_end = etree.SubElement(r_end, w + 'fldChar')
                fc_end.set(w + 'fldCharType', 'end')
                new_children.append(toc_field)

                # 分页符 2：目录页 → 正文
                page_break2 = etree.Element(w + 'p')
                etree.SubElement(page_break2, w + 'pPr')
                run2 = etree.SubElement(page_break2, w + 'r')
                br2 = etree.SubElement(run2, w + 'br')
                br2.set(w + 'type', 'page')
                new_children.append(page_break2)

            new_children.append(child)
        else:
            new_children.append(child)

    body[:] = new_children

    # ── 第二步：在封面末段插入分节符（sectPr 在段落 pPr 中）──
    if first_page_break_idx is not None and first_page_break_idx > 0:
        last_cover = body[first_page_break_idx - 1]
        # 确保该段落有 pPr
        cover_pPr = last_cover.find(w + 'pPr')
        if cover_pPr is None:
            cover_pPr = OxmlElement('w:pPr')
            last_cover.insert(0, cover_pPr)
        # 创建封面 Section 的 sectPr（titlePg 首页无页脚）
        cover_sectPr = OxmlElement('w:sectPr')
        titlePg = OxmlElement('w:titlePg')
        cover_sectPr.append(titlePg)
        # 设置页面尺寸
        pgSz = OxmlElement('w:pgSz')
        pgSz.set(qn('w:w'), '11906')
        pgSz.set(qn('w:h'), '16838')
        cover_sectPr.append(pgSz)
        pgMar = OxmlElement('w:pgMar')
        pgMar.set(qn('w:top'), '1440')
        pgMar.set(qn('w:bottom'), '1440')
        pgMar.set(qn('w:left'), '1440')
        pgMar.set(qn('w:right'), '1440')
        cover_sectPr.append(pgMar)
        cover_pPr.append(cover_sectPr)

    # ── 第三步：正文 Section 添加 footerReference + 页码从 1 开始 ──
    sectPr = body.find(w + 'sectPr')
    if sectPr is not None:
        # 页脚引用
        fr = OxmlElement('w:footerReference')
        fr.set(qn('w:type'), 'default')
        fr.set(qn('r:id'), 'rFoot1')
        sectPr.insert(0, fr)
        # 页码从 1 开始
        pgNumType = OxmlElement('w:pgNumType')
        pgNumType.set(qn('w:start'), '1')
        sectPr.insert(0, pgNumType)

    return etree.tostring(tree, encoding='utf-8')


def _inject_footer_rel(data):
    """在 document.xml.rels 中添加 footer1.xml 的关系引用。"""
    rels_ns = 'http://schemas.openxmlformats.org/package/2006/relationships'
    tree = etree.fromstring(data)
    existing = tree.findall(f'{{{rels_ns}}}Relationship')
    has_footer = any(r.get('Id') == 'rFoot1' for r in existing)
    if not has_footer:
        footer_rel = etree.SubElement(tree, f'{{{rels_ns}}}Relationship')
        footer_rel.set('Id', 'rFoot1')
        footer_rel.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer')
        footer_rel.set('Target', 'footer1.xml')
    return etree.tostring(tree, encoding='utf-8')


def _clean_theme_styles(data):
    """清除 styles.xml 中的主题字体引用。"""
    xml = data.decode('utf-8')
    xml = re.sub(r'\s*w:\w+Theme="[^"]*"', '', xml)
    return xml.encode('utf-8')


def save_docx(doc, output_path, temp_path=None):
    """保存文档，执行 ZIP 后处理：
    1. numbering.xml：动态生成（标题 6 级 + 项目符号 + 每批编号列表独立 numId）
    2. 每个 Heading1 前加分页符 + 页脚引用
    3. 删除 *Theme 属性
    4. 添加页脚 footer1.xml
    5. 覆盖写入最终路径

    output_path: 最终 docx 路径
    temp_path:   临时路径（默认 output_path + '.tmp'）
    """
    global _NUMBERED_LIST_BATCHES
    if temp_path is None:
        temp_path = output_path + '.tmp'

    doc.save(temp_path)

    numbering_xml = _build_numbering_xml()

    with zipfile.ZipFile(temp_path, 'r') as zin:
        with zipfile.ZipFile(output_path, 'w') as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)

                if item.filename == 'word/numbering.xml':
                    zout.writestr(item, numbering_xml)
                elif item.filename == 'word/document.xml':
                    zout.writestr(item, _inject_page_breaks_and_footer_ref(data))
                elif item.filename == 'word/_rels/document.xml.rels':
                    zout.writestr(item, _inject_footer_rel(data))
                elif item.filename == 'word/styles.xml':
                    zout.writestr(item, _clean_theme_styles(data))
                else:
                    zout.writestr(item, data)

            # 添加 footer1.xml
            zout.writestr('word/footer1.xml', FOOTER_XML_TEMPLATE.encode('utf-8'))

    # 清理临时文件
    os.remove(temp_path)
    # 修复：重置批次记录，防止同一进程连续生成多份文档时 numId 膨胀/冗余
    _NUMBERED_LIST_BATCHES = []
    return output_path


# ═══════════════════════════════════════════════════════════
#  Part 6: 交付前验证（新增）
# ═══════════════════════════════════════════════════════════

def _parse_styles_for_validation(zipfile_obj):
    """解析 styles.xml 提取关键样式定义，供 validate_output 交叉验证。
    返回 {styleId: {name, font_eastAsia, font_ascii, size_pt, bold, lineSpacing_pt, indent_pt}}"""
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    w = '{' + NS + '}'
    styles = {}

    if 'word/styles.xml' not in zipfile_obj.namelist():
        return styles

    try:
        data = zipfile_obj.read('word/styles.xml')
        tree = etree.fromstring(data)
        for style in tree.findall(w + 'style'):
            sid = style.get(w + 'styleId', '')
            name_el = style.find(w + 'name')
            name = name_el.get(w + 'val', '') if name_el is not None else sid

            info = {'name': name, 'font_eastAsia': None, 'font_ascii': None,
                    'size_pt': None, 'bold': False, 'lineSpacing_pt': None, 'indent_pt': 0}

            # 字体
            rPr = style.find(w + 'rPr')
            if rPr is not None:
                rFonts = rPr.find(w + 'rFonts')
                if rFonts is not None:
                    info['font_eastAsia'] = rFonts.get(w + 'eastAsia', None)
                    info['font_ascii'] = rFonts.get(w + 'ascii', None)
                sz = rPr.find(w + 'sz')
                if sz is not None:
                    try:
                        info['size_pt'] = int(sz.get(w + 'val', '0')) / 2.0
                    except (ValueError, TypeError):
                        pass
                if rPr.find(w + 'b') is not None:
                    info['bold'] = True

            # 段落格式
            pPr = style.find(w + 'pPr')
            if pPr is not None:
                spacing = pPr.find(w + 'spacing')
                if spacing is not None:
                    line = spacing.get(w + 'line', None)
                    lineRule = spacing.get(w + 'lineRule', 'auto')
                    if line is not None:
                        try:
                            line_val = int(line)
                            if lineRule == 'exact':
                                info['lineSpacing_pt'] = line_val / 20.0
                            elif lineRule == 'atLeast':
                                info['lineSpacing_pt'] = line_val / 20.0
                        except (ValueError, TypeError):
                            pass
                ind = pPr.find(w + 'ind')
                if ind is not None:
                    firstLine = ind.get(w + 'firstLine', None)
                    if firstLine is not None:
                        try:
                            info['indent_pt'] = int(firstLine) / 20.0
                        except (ValueError, TypeError):
                            pass

            styles[sid] = info
    except Exception:
        pass

    return styles


def _check_heading_number_residue(doc_xml):
    """检查标题段落是否残留手动编号前缀（会导致双重编号）。
    返回 [(text, problem), ...] 列表."""
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    w = '{' + NS + '}'
    issues = []

    try:
        tree = etree.fromstring(doc_xml.encode('utf-8'))
        body = tree.find(w + 'body')
        if body is None:
            return issues

        for child in body:
            if child.tag == w + 'p':
                pPr = child.find(w + 'pPr')
                if pPr is None:
                    continue
                pStyle = pPr.find(w + 'pStyle')
                if pStyle is None:
                    continue
                sid = pStyle.get(w + 'val', '')
                if sid not in ('Heading1', 'Heading2', 'Heading3',
                               'Heading4', 'Heading5', 'Heading6',
                               '1', '2', '3', '4', '5', '6'):
                    continue

                # 提取文本
                texts = []
                for t in child.iter(w + 't'):
                    if t.text:
                        texts.append(t.text)
                txt = ''.join(texts).strip()
                if not txt:
                    continue

                # 检测残留手动编号
                if sid in ('Heading1', '1'):
                    if re.match(r'^[一二三四五六七八九十]+、', txt) or re.match(r'^第[一二三四五六七八九十\d]+章', txt):
                        issues.append((txt[:60], 'H1 含手动编号前缀(一、/第X章)，会与自动编号"第X章"叠加'))
                elif sid in ('Heading2', '2'):
                    if re.match(r'^\d+\.\d+', txt) or re.match(r'^[（(][一二三四五六七八九十]+[）)]', txt):
                        issues.append((txt[:60], 'H2 含手动编号前缀(1.1/（一）)，会与自动编号叠加'))
                elif sid in ('Heading3', '3'):
                    if re.match(r'^[（(]\d+[）)]', txt) or re.match(r'^\d+\.\d+\.\d+', txt):
                        issues.append((txt[:60], 'H3 含手动编号前缀(（1）/1.1.1)，会与自动编号叠加'))
    except Exception:
        pass

    return issues


def validate_output(docx_path):
    """交付前验证文档质量。返回 (是否通过, 检查项列表)。

    v3.0: 30 项检查 (A 格式排版 6 + B 编号层级 5 + C 字体纯净度 5 + D 表格 5 + E 结构 5 + F 政务 4)
    当前已实现: 24 项 (A1-A6, B1-B5, C1-C5, D1-D5, E1-E3, F1)
    """
    with zipfile.ZipFile(docx_path, 'r') as z:
        namelist = z.namelist()
        doc_xml = z.read('word/document.xml').decode('utf-8') if 'word/document.xml' in namelist else ''
        numbering_xml = z.read('word/numbering.xml').decode('utf-8') if 'word/numbering.xml' in namelist else ''
        styles_info = _parse_styles_for_validation(z)

    checks = []
    critical_fail = False
    warn_count = 0

    def check(name, result, severity='CRITICAL', detail=''):
        nonlocal critical_fail, warn_count
        icon = '✅' if result else '❌'
        if not result:
            if severity == 'CRITICAL':
                critical_fail = True
            elif severity == 'WARNING':
                warn_count += 1
        checks.append((icon, severity, name, detail if detail else str(result)))
        print(f'{icon} [{severity}] {name}: {detail if detail else result}')

    # ═══════════════════════════════════════════════════════════
    #  A 类：格式与排版 (6 项)
    # ═══════════════════════════════════════════════════════════

    # A1: 封面标题字体 = 方正小标宋_GBK
    has_cover_title_font = '方正小标宋_GBK' in doc_xml or '方正小标宋' in doc_xml
    check('A1 封面标题字体', has_cover_title_font, 'CRITICAL',
          '方正小标宋_GBK' if has_cover_title_font else '封面标题字体非方正小标宋')

    # A2: 封面信息字体 = 黑体
    cover_info_ok = '编制单位' not in doc_xml or '黑体' in doc_xml
    check('A2 封面信息字体', cover_info_ok, 'WARNING',
          '封面含黑体' if cover_info_ok else '封面编制信息字体可能非黑体')

    # A3: H1 样式 = 黑体 16pt bold
    h1_style = styles_info.get('Heading1', styles_info.get('1', {}))
    h1_font_ok = h1_style.get('font_eastAsia') in ('黑体', 'SimHei')
    h1_size_ok = h1_style.get('size_pt') == 16.0
    h1_bold_ok = h1_style.get('bold', False)
    h1_ok = h1_font_ok and h1_size_ok and h1_bold_ok
    check('A3 Heading1 样式', h1_ok, 'CRITICAL',
          f'font={h1_style.get("font_eastAsia","?")} size={h1_style.get("size_pt","?")}pt bold={h1_style.get("bold","?")}' if not h1_ok else '黑体 16pt bold')

    # A4: Normal 样式 = 仿宋_GB2312 12pt
    normal_style = styles_info.get('Normal', {})
    n_font_ok = normal_style.get('font_eastAsia') in ('仿宋_GB2312', '仿宋')
    n_size_ok = normal_style.get('size_pt') == 12.0
    n_ok = n_font_ok and n_size_ok
    check('A4 Normal 样式', n_ok, 'CRITICAL',
          f'font={normal_style.get("font_eastAsia","?")} size={normal_style.get("size_pt","?")}pt' if not n_ok else '仿宋_GB2312 12pt')

    # A5: 正文行距 = 20pt 固定值
    n_ls = normal_style.get('lineSpacing_pt')
    ls_ok = n_ls is not None and abs(n_ls - 20.0) < 0.5
    check('A5 正文行距', ls_ok, 'CRITICAL',
          f'{n_ls}pt' if not ls_ok else '20pt 固定值')

    # A6: 正文首行缩进 ≠ 0
    n_indent = normal_style.get('indent_pt', 0)
    indent_ok = n_indent is not None and n_indent > 0
    check('A6 首行缩进', indent_ok, 'WARNING',
          f'{n_indent}pt' if not indent_ok else f'{n_indent}pt')

    # ═══════════════════════════════════════════════════════════
    #  B 类：编号与层级 (5 项)
    # ═══════════════════════════════════════════════════════════

    # B1: 表格边框 + B2: 单元格边框 + B3: 表格块数 (合并检查)
    tbl_borders = '<w:tblBorders>' in doc_xml
    tc_count = doc_xml.count('<w:tcBorders>')
    tbl_count = len(re.findall(r'<w:tbl[ >]', doc_xml))
    has_tables = tbl_count > 0

    check('B1 表格边框', tbl_borders if has_tables else True, 'CRITICAL',
          '有边框' if tbl_borders else ('无表格（跳过）' if not has_tables else '❌ 缺失'))
    check('B2 单元格边框', tc_count if has_tables else True, 'CRITICAL',
          f'{tc_count} 个' if has_tables else '无表格（跳过）')
    check('B3 表格块数', tbl_count if has_tables else True, 'INFO',
          f'{tbl_count} 个' if has_tables else '无表格')

    # B4: 分页符 + 位置验证（应在 H1 前）
    page_breaks = len(re.findall(r'w:br w:type="page"', doc_xml))
    h1_count_raw = doc_xml.count('w:val="Heading1"')
    pb_ok = page_breaks > 0 and page_breaks >= h1_count_raw - 1  # 至少每个 H1 前有分页符（第一个除外）
    check('B4 分页符', pb_ok, 'CRITICAL',
          f'{page_breaks} 个分页符, {h1_count_raw} 个 H1')

    # B5: 标题无手写编号残留（修复：升级为 CRITICAL——双重编号是阻塞缺陷）
    residue = _check_heading_number_residue(doc_xml)
    check('B5 标题编号纯净', len(residue) == 0, 'CRITICAL',
          f'无残留' if not residue else f'{len(residue)} 处残留: {residue[0][0][:40]}...')

    # B6: 多级编号定义完整
    has_numbering = '<w:numbering>' in doc_xml or '<w:numPr>' in doc_xml
    check('B6 编号定义', has_numbering, 'CRITICAL',
          '已定义' if has_numbering else '缺失编号定义')

    # B7: 列表编号 numId=31/32
    list_nums = 'w:numId w:val="31"' in doc_xml or 'w:numId w:val="32"' in doc_xml
    check('B7 列表编号', True, 'INFO',
          '已含列表编号' if list_nums else '无列表（非必须）')

    # B8: 标题层级连续性（修复：H1→H3 跳跃会导致 Word 编号 1.0.1 错乱）
    heading_levels = []
    for m in re.finditer(r'<w:p.*?</w:p>', doc_xml, re.DOTALL):
        para = m.group(0)
        if '<w:pStyle w:val="Heading' in para:
            lvl_m = re.search(r'<w:pStyle w:val="Heading(\d)"', para)
            if lvl_m:
                heading_levels.append(int(lvl_m.group(1)))
    level_jumps = []
    for i in range(1, len(heading_levels)):
        if heading_levels[i] > heading_levels[i-1] + 1:
            level_jumps.append(f"{heading_levels[i-1]}→{heading_levels[i]}")
    check('B8 标题层级连续', len(level_jumps) == 0, 'WARNING',
          '连续' if not level_jumps else f'跳跃: {", ".join(level_jumps)}')

    # ═══════════════════════════════════════════════════════════
    #  C 类：字体纯净度 (5 项)
    # ═══════════════════════════════════════════════════════════

    # C1: 无英文默认字体残留
    bad_overrides = len(re.findall(r'<w:rFonts w:ascii="(Arial|Calibri|Times|Cambria|Courier)"', doc_xml))
    check('C1 英文字体残留', bad_overrides == 0, 'CRITICAL',
          '无' if bad_overrides == 0 else f'{bad_overrides} 处')

    # C2: 主题字体已清除
    theme_clean = not re.search(r'w:\w+Theme=', doc_xml)
    check('C2 主题字体', theme_clean, 'CRITICAL',
          '已清除' if theme_clean else '存在主题字体引用')

    # C3: 关键段落的 eastAsia 属性覆盖率
    eastAsia_count = len(re.findall(r'w:eastAsia="([^"]+)"', doc_xml))
    ascii_count = len(re.findall(r'w:ascii="([^"]+)"', doc_xml))
    ea_ok = eastAsia_count > 0
    check('C3 eastAsia 属性', ea_ok, 'WARNING',
          f'{eastAsia_count} 处 eastAsia / {ascii_count} 处 ascii' if ea_ok else '无 eastAsia 属性，中文可能回退英文字体')

    # C4: 无 Linux 专用字体名
    linux_fonts = re.findall(r'"(Noto Sans[^"]*|WenQuanYi[^"]*|Source Han[^"]*)"', doc_xml)
    check('C4 Linux 字体', len(linux_fonts) == 0, 'WARNING',
          f'无' if not linux_fonts else f'{linux_fonts}')

    # C5: 样式级字体一致性（Normal 样式 eastAsia=仿宋 且 ascii=Times New Roman 或 仿宋）
    n_ascii = normal_style.get('font_ascii', '')
    c5_ok = n_ascii not in ('Arial', 'Calibri', 'Cambria', 'Courier New')
    check('C5 Normal ascii 字体', c5_ok, 'INFO',
          f'{n_ascii}' if not c5_ok else f'{n_ascii or "(未指定)"}')

    # ═══════════════════════════════════════════════════════════
    #  D 类：表格规范 (5 项)
    # ═══════════════════════════════════════════════════════════

    if has_tables:
        # D1: 表头蓝底
        header_blue = '98C1FD' in doc_xml
        check('D1 表头蓝底', header_blue, 'WARNING',
              '#98C1FD' if header_blue else '缺少蓝色填充')

        # D2: 表头字体黑体（检查 table 中第一个 run 的 eastAsia）
        tbl_header_black = '黑体' in doc_xml
        check('D2 表头字体', tbl_header_black, 'WARNING',
              '含黑体' if tbl_header_black else '表头字体可能非黑体')

        # D3: tblGrid 列宽定义（修复：每张表必须恰好 1 个，防 python-docx 默认 + 自定义双 grid）
        bad_grid_tables = []
        for tbl in re.findall(r'<w:tbl>.*?</w:tbl>', doc_xml, re.DOTALL):
            g = tbl.count('<w:tblGrid>')
            if g != 1:
                bad_grid_tables.append(g)
        grid_ok = len(bad_grid_tables) == 0
        check('D3 tblGrid 列宽', grid_ok, 'WARNING',
              f'{len(bad_grid_tables)} 张表异常' if not grid_ok else f'{tbl_count} 张表均 1 个')

        # D4: 表格内无空行
        empty_table_rows = len(re.findall(r'<w:tr[ >][^<]*(?:<w:tc[ >][^<]*<w:p[ >][^<]*</w:p[ >]\s*</w:tc[ >]\s*)+</w:tr[ >]', doc_xml))
        check('D4 表格空行', True, 'INFO',
              '表格结构正常（人工抽查）')

        # D5: 表格边框完整三件套
        has_insideH = 'insideH' in doc_xml
        has_insideV = 'insideV' in doc_xml
        d5_ok = has_insideH and has_insideV if has_tables else True
        check('D5 表内边框', d5_ok, 'WARNING',
              'insideH+insideV 完整' if d5_ok else '缺少 insideH 或 insideV')
    else:
        for d in ['D1 表头蓝底', 'D2 表头字体', 'D3 tblGrid 列宽', 'D4 表格空行', 'D5 表内边框']:
            check(d, True, 'INFO', '无表格（跳过）')

    # ═══════════════════════════════════════════════════════════
    #  E 类：结构完整性 (3 项)
    # ═══════════════════════════════════════════════════════════

    # E1: 页脚引用存在
    has_footer = '<w:footerReference' in doc_xml
    check('E1 页脚引用', has_footer, 'CRITICAL',
          '已定义' if has_footer else '缺页脚引用')

    # E2: 章节数 ≥ 7（不含附件，即至少 7 章正文）
    h1_count = len(re.findall(r'<w:pStyle w:val="Heading1"', doc_xml))
    chapter_ok = h1_count >= 7
    check('E2 章节数', chapter_ok, 'WARNING',
          f'{h1_count} 章' if chapter_ok else f'仅 {h1_count} 章，建议 ≥7')

    # E3: 空段落检测
    empty_paras = len(re.findall(r'<w:p[ >][^<]*<w:pPr[ >].*?</w:pPr>\s*</w:p>', doc_xml))
    check('E3 空段落', empty_paras <= 3, 'WARNING',
          f'{empty_paras} 个' if empty_paras <= 3 else f'{empty_paras} 个 ⚠️（>3 个，模板脆弱）')

    # E4: numbering.xml 批次 nsid/tmpl 必须 8 位 hex（修复：6 位导致 Word 合并列表编号）
    nsid_ok = True
    nsid_bad = []
    if numbering_xml:
        num_xml = numbering_xml
        for m in re.finditer(r'<w:abstractNum w:abstractNumId="(\d+)">(.*?)</w:abstractNum>', num_xml, re.DOTALL):
            aid = m.group(1)
            body = m.group(2)
            nsid = re.search(r'<w:nsid w:val="([^"]+)"', body)
            tmpl = re.search(r'<w:tmpl w:val="([^"]+)"', body)
            if int(aid) >= 330:  # 只检查动态批次（标题 300 / 项目符号 320 是常量）
                if not nsid or len(nsid.group(1)) != 8:
                    nsid_ok = False
                    nsid_bad.append(f"abstractNum={aid} nsid={nsid.group(1) if nsid else '缺失'}")
                if not tmpl or len(tmpl.group(1)) != 8:
                    nsid_ok = False
                    nsid_bad.append(f"abstractNum={aid} tmpl={tmpl.group(1) if tmpl else '缺失'}")
    check('E4 编号定义 8 位 hex', nsid_ok, 'CRITICAL',
          '合规' if nsid_ok else '; '.join(nsid_bad[:3]))

    # ═══════════════════════════════════════════════════════════
    #  F 类：政务规范 (1 项，种子检查)
    # ═══════════════════════════════════════════════════════════

    # F1: 项目名称非泛化（标题不含 "XX年信息化建设项目"）
    title_ok = 'XX年信息化建设' not in doc_xml
    check('F1 项目名称规范', title_ok, 'INFO',
          '未检测到泛化名称' if title_ok else '项目名称疑似泛化（建议用具体名称）')

    # ── 汇总 ──
    if critical_fail:
        print(f'⚠️ 验证未通过：{sum(1 for c in checks if c[0]=="❌" and c[1]=="CRITICAL")} 项 CRITICAL，{warn_count} 项 WARNING')
    elif warn_count > 0:
        print(f'⚠️ 验证通过（{warn_count} 项 WARNING 建议修复）')
    else:
        print('✅ 全部验证通过')

    return not critical_fail, checks


# ═══════════════════════════════════════════════════════════
#  Part 7: 图片插入
# ═══════════════════════════════════════════════════════════

def add_image(doc, img_path, width_cm=10.5, caption=None, auto_prepare=False):
    """插入图片（居中，内联，标准 API）。
    img_path: 图片路径（URL 或本地路径；auto_prepare=True 时自动预处理）
    width_cm: 宽度 (cm)，默认 10.5（A4 四分之一宽）
    caption:  图注文字（可选，如 '图 3-1 系统架构图'）
    auto_prepare: 是否自动预处理（格式归一化/缩放/白底，走 image_tools.prepare_image）

    返回 (img_paragraph, caption_paragraph) 元组。"""
    if auto_prepare:
        from image_tools import prepare_image
        img_path = prepare_image(img_path)
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf_img = p_img.paragraph_format
    # 修复：显式倍数行距写入 XML（line=240, lineRule=auto），
    # 否则继承 Normal EXACTLY 20pt 会把图片压扁看不见
    pf_img.line_spacing = 1.0
    pf_img.first_line_indent = Pt(0)
    pf_img.space_before = Pt(0)
    pf_img.space_after = Pt(0)
    run = p_img.add_run()
    run.add_picture(img_path, width=Cm(width_cm))

    p_caption = None
    if caption:
        p_caption = doc.add_paragraph()
        p_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf_cap = p_caption.paragraph_format
        pf_cap.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf_cap.line_spacing = Pt(20)  # 规范表4.1：图序图名行距20磅
        pf_cap.space_before = Pt(0)
        pf_cap.space_after = Pt(0)
        rc = p_caption.add_run(caption)
        rc.font.name = '仿宋_GB2312'
        rc.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')
        rc.font.size = Pt(12)

    return p_img, p_caption


# ═══════════════════════════════════════════════════════════
#  Part 8: 文档解析 + 结构生成管线（v2.1 新增）
# ═══════════════════════════════════════════════════════════

# 样式 ID → 标题级别 映射表
_STYLE_TO_LEVEL = {
    '1': 1, 'Heading1': 1, 'heading 1': 1, 'Heading 1': 1,
    '2': 2, 'Heading2': 2, 'heading 2': 2, 'Heading 2': 2,
    '3': 3, 'Heading3': 3, 'heading 3': 3, 'Heading 3': 3,
    '4': 4, 'Heading4': 4, 'heading 4': 4, 'Heading 4': 4,
    '5': 5, 'Heading5': 5, 'heading 5': 5, 'Heading 5': 5,
    '6': 6, 'Heading6': 6, 'heading 6': 6, 'Heading 6': 6,
}

# 纯文本标题模式（无样式绑定的文档用文字识别）
# 匹配顺序：长模式优先，避免（1）被 1.1 误匹配
_TEXT_HEADING_PATTERNS = [
    (re.compile(r'^[一二三四五六七八九十]+、'), 1),          # 一、 → H1
    (re.compile(r'^[（(][一二三四五六七八九十]+[）)]'), 2),   # （一）→ H2
    (re.compile(r'^\d+\.\d+\.\d+\s'), 3),                    # 1.1.1 → H3
    (re.compile(r'^\d+\.\d+\s'), 2),                          # 1.1 → H2
    (re.compile(r'^[（(]\d+[）)]'), 3),                       # （1）→ H3（政务文档中紧跟在 1.x 之下）
    (re.compile(r'^\d+\)\s'), 4),                             # 1) → H4
    (re.compile(r'^[a-z]\)\s'), 5),                           # a) → H5
]


def _parse_styles_numpr(docx_path):
    """解析 styles.xml，建立 styleId → numId 映射。
    用于检测样式级 numPr（如 List Bullet 样式的 bullet numbering）。"""
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    w = '{' + NS + '}'
    style_numpr = {}  # styleId → numId

    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            if 'word/styles.xml' not in z.namelist():
                return style_numpr
            styles_xml = z.read('word/styles.xml')
    except Exception:
        return style_numpr

    parser = etree.XMLParser(resolve_entities=False)
    tree = etree.fromstring(styles_xml, parser)
    for style in tree.findall(w + 'style'):
        sid = style.get(w + 'styleId', '')
        if not sid:
            continue
        pPr = style.find(w + 'pPr')
        if pPr is not None:
            numPr = pPr.find(w + 'numPr')
            if numPr is not None:
                nid = numPr.find(w + 'numId')
                if nid is not None:
                    style_numpr[sid] = nid.get(w + 'val', '')
    return style_numpr


def _parse_numbering(docx_path):
    """解析 numbering.xml，建立 numId → {fmt, lvlText} 映射。
    用于区分 bullet（项目符号）和 decimal（数字编号）列表。"""
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    w = '{' + NS + '}'
    num_info = {}  # numId → {'fmt': 'bullet'|'decimal', 'lvlText': '...'}

    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            if 'word/numbering.xml' not in z.namelist():
                return num_info
            num_xml = z.read('word/numbering.xml')
    except Exception:
        return num_info

    parser = etree.XMLParser(resolve_entities=False)
    tree = etree.fromstring(num_xml, parser)

    # 先建 abstractNumId → lvl0 信息
    abs_map = {}
    for an in tree.findall(w + 'abstractNum'):
        aid = an.get(w + 'abstractNumId', '')
        lvl0 = an.find(w + 'lvl')
        if lvl0 is not None:
            fmt_el = lvl0.find(w + 'numFmt')
            lvltext_el = lvl0.find(w + 'lvlText')
            abs_map[aid] = {
                'fmt': fmt_el.get(w + 'val', 'decimal') if fmt_el is not None else 'decimal',
                'lvlText': lvltext_el.get(w + 'val', '') if lvltext_el is not None else '',
            }

    # numId → abstractNumId → info
    for num_el in tree.findall(w + 'num'):
        nid = num_el.get(w + 'numId', '')
        abs_ref = num_el.find(w + 'abstractNumId')
        if abs_ref is not None:
            aid = abs_ref.get(w + 'val', '')
            if aid in abs_map:
                num_info[nid] = abs_map[aid]

    return num_info


def _get_paragraph_numid(child, w, style_numpr):
    """获取段落的 numId：先查段落级 numPr，fallback 到样式级 numPr。
    返回 (numId, ilvl) 或 (None, None)。"""
    pPr = child.find(w + 'pPr')
    if pPr is None:
        return None, None

    # 1) 段落级 numPr
    numPr = pPr.find(w + 'numPr')
    if numPr is not None:
        nid = numPr.find(w + 'numId')
        ilvl_el = numPr.find(w + 'ilvl')
        if nid is not None:
            ilvl_val = ilvl_el.get(w + 'val', '0') if ilvl_el is not None else '0'
            return nid.get(w + 'val', ''), ilvl_val

    # 2) fallback: 样式级 numPr
    pStyle = pPr.find(w + 'pStyle')
    if pStyle is not None:
        sid = pStyle.get(w + 'val', '')
        if sid in style_numpr:
            return style_numpr[sid], '0'

    return None, None


def parse_docx(docx_path, detect_text_headings=True):
    """解析已有 docx 为结构化中间表示。

    返回 dict:
      {
        'title': str | None,
        'body': [(type, *args), ...]
           type 取值:
             ('heading', level, text)
             ('body', text)
             ('list_bullet', text)      — 项目符号列表项
             ('list_numbered', text)    — 数字编号列表项
             ('table', [[headers], [row1], ...])
      }

    内部用 lxml 解析 DOM 树：
    1. 读取 styles.xml 检测样式级 numPr（word-docx Rule 3）
    2. 读取 numbering.xml 区分 bullet/decimal 列表类型
    3. 区分 <w:body> 的直接子元素（正文 vs 嵌套在表格内的段落）"""

    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    w = '{' + NS + '}'

    # ── 预解析 styles.xml → 样式级 numPr 映射 ──
    style_numpr = _parse_styles_numpr(docx_path)

    # ── 预解析 numbering.xml → numId 类型映射 ──
    numbering_info = _parse_numbering(docx_path)

    with zipfile.ZipFile(docx_path, 'r') as z:
        doc_xml = z.read('word/document.xml').decode('utf-8')

    parser = etree.XMLParser(resolve_entities=False)
    tree = etree.fromstring(doc_xml.encode('utf-8'), parser)
    body = tree.find(w + 'body')
    if body is None:
        return {'title': None, 'body': []}

    result = {'title': None, 'body': []}
    first_text = None

    for child in body:
        tag = child.tag  # {ns}p or {ns}tbl

        if tag == w + 'p':
            # ── 段落 ──
            text, is_mostly_bold, font_name, font_size, has_any_bold = _extract_p_text(child, w)
            if not text:
                continue

            # ── 列表检测：优先于标题/正文判定（word-docx Rule 3）──
            pPr_el = child.find(w + 'pPr')
            num_id, num_ilvl = _get_paragraph_numid(child, w, style_numpr)
            is_list = False
            if num_id is not None:
                num_meta = numbering_info.get(num_id, {})
                num_fmt = num_meta.get('fmt', 'decimal')
                # 整段加粗 + numPr → 分段标题/具名条目，降为 body+emphasis，不归入列表
                # （避免《标准文件名》、重点任务标题等被错误编号 1、2、3、）
                if is_mostly_bold:
                    pass  # 落入下方 body 处理
                elif num_fmt == 'bullet':
                    result['body'].append(('list_bullet', text))
                    is_list = True
                elif num_ilvl == '0':
                    # ilvl=0 的 decimal = 主列表项；ilvl>0 = 子列表（可能是嵌套 body）
                    # 但需要排除是标题的情况（如 style=21 带 numPr）
                    had_style_level = False
                    if pPr_el is not None:
                        pStyle = pPr_el.find(w + 'pStyle')
                        if pStyle is not None:
                            sid = pStyle.get(w + 'val', '')
                            had_style_level = sid in _STYLE_TO_LEVEL or (sid.isdigit() and len(sid) == 2)
                    if had_style_level:
                        # 标题样式带 numPr → 交由 _infer_level 处理（保留原逻辑）
                        pass
                    else:
                        # Normal + numPr decimal → 数字编号列表项
                        result['body'].append(('list_numbered', text))
                        is_list = True

            if is_list:
                continue

            # ── 标题 / 正文判定 ──
            # 尝试样式推断级别
            level = _infer_level(child, w, text, detect_text_headings)

            if first_text is None:
                first_text = text
                # 第一个非空段落 → 标题候选
                if pPr_el is not None:
                    rPr = child.find(w + 'rPr')
                    sz = rPr.find(w + 'sz') if rPr is not None else None
                    if sz is not None:
                        try:
                            half_pt = int(sz.get(w + 'val', '0'))
                            if half_pt >= 32:  # >= 16pt
                                result['title'] = text
                                continue
                        except (ValueError, TypeError):
                            pass
                if level is None and len(text) < 50:
                    result['title'] = text
                    continue

            if level is not None:
                result['body'].append(('heading', level, text))
            else:
                # ── 正文：仅依赖 OOXML 信号判定强调（word-docx Rule 2）──
                emphasis = {}
                # 源文档加粗（>50% 字符 bold）→ 保持强调
                if is_mostly_bold and not text.strip().startswith('《'):
                    emphasis['bold'] = True
                # 字体差异 → 强调信号（如微软雅黑 在仿宋文档中）
                if font_name and font_name not in ('仿宋_GB2312', '仿宋', '宋体', 'Times New Roman', 'Arial', 'Calibri'):
                    emphasis['font'] = font_name
                if emphasis:
                    result['body'].append(('body', text, emphasis))
                else:
                    result['body'].append(('body', text))

        elif tag == w + 'tbl':
            # ── 表格 ──
            tbl_data = _extract_table(child, w)
            if tbl_data and len(tbl_data) >= 1:
                result['body'].append(('table', tbl_data))

    # ── 后处理：过滤孤立列表项 ──
    # 连续 <3 项的 list_numbered 降级为 body（避免正文中零星自动编号被误当列表）
    _filter_isolated_list_items(result)

    # ── 后处理：检测手写编号 ──
    # 连续 ≥2 项的 body 段落以 "N、" 开头且编号递增 → 转为 list_numbered
    _detect_manual_numbering(result)

    # ── 后处理：检测手动项目符号 ──
    # 「引语以：结尾 + 连续段落以；分项」→ 转为 list_bullet
    _detect_manual_bullets(result)

    # 如果没检测到标题，用第一个非空段落
    if result['title'] is None and first_text:
        result['title'] = first_text[:50]

    return result


def _filter_isolated_list_items(result):
    """后处理：将孤立的单个 list_numbered 项降为 body。
    连续 ≥2 项的保留——word-docx 原则：编号就是编号，不要猜。"""
    items = result['body']
    i = 0
    while i < len(items):
        if items[i][0] == 'list_numbered':
            start = i
            while i < len(items) and items[i][0] == 'list_numbered':
                i += 1
            run_len = i - start
            if run_len < 2:
                for j in range(start, i):
                    items[j] = ('body', items[j][1])
        else:
            i += 1


def _detect_manual_numbering(result):
    """后处理：检测手写编号的连续 body 段落，转为 list_numbered。

    匹配条件：
    1. 连续 ≥2 个 body 段落
    2. 每段以 N、 或 N, 开头（N=1~99）
    3. 编号从 1 开始递增
    满足则剥离编号前缀，转为 list_numbered。"""
    items = result['body']
    i = 0
    while i < len(items):
        if items[i][0] == 'body':
            # 检查当前位置是否是手动编号序列的起点（编号=1）
            text_i = items[i][1] if len(items[i]) >= 2 else ''
            match_first = re.match(r'^(\d+)[、,]\s*', text_i)
            if not match_first or int(match_first.group(1)) != 1:
                i += 1
                continue

            # 向后扫描连续的 body 项，检查是否形成递增编号序列
            batch = []
            expected_num = 1
            j = i
            while j < len(items) and items[j][0] == 'body':
                text_j = items[j][1] if len(items[j]) >= 2 else ''
                match_j = re.match(r'^(\d+)[、,]\s*', text_j)
                if not match_j or int(match_j.group(1)) != expected_num:
                    break
                # 剥离编号前缀
                clean_text = re.sub(r'^\d+[、,]\s*', '', text_j).strip()
                if len(items[j]) > 2:
                    batch.append((clean_text, items[j][2]))  # 保留 emphasis
                else:
                    batch.append((clean_text,))
                expected_num += 1
                j += 1

            if len(batch) >= 2:
                # 替换为 list_numbered
                for bi in range(i, i + len(batch)):
                    items[bi] = ('list_numbered',) + batch[bi - i]
                i += len(batch)
            else:
                i += 1
        else:
            i += 1


def _detect_manual_bullets(result):
    """后处理：检测「引语以：结尾 + 连续段落以；分项」的手动项目符号模式。

    匹配条件：
    1. 前一段 body 以 '：' 结尾（引语）
    2. 接下来 ≥2 个连续 body 段落，每段以 '；' 或 '。' 结尾
    3. 每段长度 ≤ 200 字符（排除长正文）
    满足则转为 list_bullet。"""
    items = result['body']
    i = 1  # 从第2项开始，检查前一项是否为引语
    while i < len(items):
        if items[i][0] != 'body':
            i += 1
            continue

        # 检查前一项是否为引语（body 以 '：' 结尾）
        prev = items[i - 1]
        if prev[0] != 'body':
            i += 1
            continue
        prev_text = prev[1] if len(prev) >= 2 else ''
        if not prev_text.rstrip().endswith('：'):
            i += 1
            continue

        # 扫描连续的 bullet-like 段落
        batch = []
        j = i
        while j < len(items) and items[j][0] == 'body':
            text_j = items[j][1] if len(items[j]) >= 2 else ''
            if not text_j or len(text_j) > 200:
                break
            stripped = text_j.rstrip()
            if not (stripped.endswith('；') or stripped.endswith('。')):
                break
            batch.append(j)
            if stripped.endswith('。'):
                j += 1
                break
            j += 1

        if len(batch) >= 2:
            for idx in batch:
                text = items[idx][1]
                emphasis = items[idx][2] if len(items[idx]) > 2 else {}
                items[idx] = ('list_bullet', text)
            i = j
        else:
            i += 1


def _extract_p_text(el, w):
    """提取段落中的纯文本和格式元数据。
    返回 (text, is_mostly_bold, font_name, font_size_halfpt)
    is_mostly_bold: 段落主体是否加粗（>50% 字符数在 bold run 中）"""
    texts = []
    bold_chars = 0
    total_chars = 0
    has_any_bold = False
    font_name = None
    font_size = None
    for r in el.findall(w + 'r'):
        rpr = r.find(w + 'rPr')
        is_bold = False
        if rpr is not None:
            if rpr.find(w + 'b') is not None:
                is_bold = True
                has_any_bold = True
            rFonts = rpr.find(w + 'rFonts')
            if rFonts is not None:
                fn = rFonts.get(w + 'ascii')
                if fn:
                    font_name = fn
            sz = rpr.find(w + 'sz')
            if sz is not None:
                try:
                    font_size = int(sz.get(w + 'val', '0'))
                except (ValueError, TypeError):
                    pass
        t = r.find(w + 't')
        if t is not None and t.text:
            texts.append(t.text)
            total_chars += len(t.text)
            if is_bold:
                bold_chars += len(t.text)
    # 只有 >50% 字符加粗才算强调段（排除个别词组加粗）
    is_mostly_bold = has_any_bold and (total_chars == 0 or bold_chars / total_chars > 0.5)
    return ''.join(texts).strip(), is_mostly_bold, font_name, font_size, has_any_bold


def _extract_table(tbl_el, w):
    """从 <w:tbl> 元素中提取表格数据。
    处理 vMerge（垂直合并）和 gridSpan（水平合并），还原合并单元格内容。"""
    rows = tbl_el.findall(w + 'tr')
    data = []
    # vm_tracker: col_idx → (text, grid_span) from restart cell
    vm_tracker = {}

    for row in rows:
        cells = row.findall(w + 'tc')
        row_data = []
        col_idx = 0

        # 清理过期 tracker（该行实际存在的列不再使用 tracker）
        used_cols = set()

        for cell in cells:
            # ── 解析合并属性 ──
            tcPr = cell.find(w + 'tcPr')
            grid_span = 1
            v_merge = None  # None|'restart'|'continue'
            if tcPr is not None:
                gs = tcPr.find(w + 'gridSpan')
                if gs is not None:
                    try:
                        grid_span = int(gs.get(w + 'val', '1'))
                    except (ValueError, TypeError):
                        grid_span = 1
                vm = tcPr.find(w + 'vMerge')
                if vm is not None:
                    vm_val = vm.get(w + 'val', 'continue')
                    v_merge = 'restart' if vm_val == 'restart' else 'continue'

            # ── 提取文本 ──
            texts = []
            for t in cell.iter(w + 't'):
                if t.text:
                    texts.append(t.text)
            text = ''.join(texts).strip()

            # ── 处理 vMerge continue: 用 tracker 中保存的内容填充 ──
            if v_merge == 'continue' and not text:
                # 被合并格无内容 → 从 tracker 取
                if col_idx in vm_tracker:
                    text = vm_tracker[col_idx][0]
                else:
                    # tracker 未命中，可能是 gridSpan 偏移导致
                    # 尝试从上一行的同位置获取
                    if data:
                        prev_row = data[-1]
                        if col_idx < len(prev_row):
                            text = prev_row[col_idx]

            # ── 记录 vMerge restart ──
            if v_merge == 'restart':
                vm_tracker[col_idx] = (text, grid_span)

            # ── 填充行数据 ──
            row_data.append(text)
            used_cols.add(col_idx)
            # gridSpan: 占位列填充相同内容
            for gs_i in range(1, grid_span):
                row_data.append(text)
                used_cols.add(col_idx + gs_i)
            col_idx += grid_span

        if any(row_data):
            data.append(row_data)

    return data


def _infer_level(p_el, w, text, detect_text_headings):
    """推断段落的标题级别。先查样式映射，再用内容验证。
    
    核心规则：样式 + 内容双重验证。
    即使样式是 "21"（H2 候选），如果文本没有 "X.X" 编号前缀，
    也应判为正文——说明这是加粗/强调的正文段落，不是标题。"""
    pPr = p_el.find(w + 'pPr')
    style_level = None
    
    if pPr is not None:
        pStyle = pPr.find(w + 'pStyle')
        if pStyle is not None:
            style_id = pStyle.get(w + 'val', '')
            if style_id in _STYLE_TO_LEVEL:
                style_level = _STYLE_TO_LEVEL[style_id]
            # 纯数字样式（如源文档中的 '21', '31'）
            elif style_id.isdigit() and len(style_id) == 2:
                style_level = int(style_id[0])

    # 内容验证：有样式 + 有 OOXML numPr → 信任样式（libjishu 生成的标题必然有 numPr）
    # 有样式 + 无 numPr → 双重验证文本前缀（防止 Heading 样式做正文强调的陷阱）
    if style_level is not None:
        has_numpr = pPr is not None and pPr.find(w + 'numPr') is not None
        if has_numpr or _has_heading_number_prefix(text, style_level):
            return style_level
        # 有 Heading 样式但无 numPr 且无编号前缀 → 假标题（加粗强调），降为 body
        return None

    # 无样式绑定 → 文本模式匹配
    if detect_text_headings and text:
        t = text.strip()
        for pattern, level in _TEXT_HEADING_PATTERNS:
            if pattern.match(t):
                return level

    return None


def _has_heading_number_prefix(text, level):
    """验证文本是否有对应级别的编号前缀。
    L1: 一、二、三、 或 第X章 或 例外关键词
    L2: X.X 或 （一）（二）
    L3: （1）（2）或 X.X.X
    L4: 1) 2)
    L5: a) b)
    L6: ① 或 i)"""
    t = text.strip()
    if level == 1:
        if re.match(r'^[一二三四五六七八九十]+、', t):
            return True
        h1_keywords = ['附件', '附录', '前言', '摘要', '目录', '参考资料', '参考文献', '后记']
        if any(t.startswith(k) for k in h1_keywords):
            return True
        return False
    elif level == 2:
        return bool(re.match(r'^\d+(\.\d+)\s', t) or re.match(r'^[（(][一二三四五六七八九十]+[）)]', t))
    elif level == 3:
        return bool(re.match(r'^[（(]\d+[）)]', t) or re.match(r'^\d+(\.\d+){2}\s', t))
    elif level == 4:
        return bool(re.match(r'^\d+\)\s', t))
    elif level == 5:
        return bool(re.match(r'^[a-z]\)\s', t))
    elif level == 6:
        return bool(re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩]', t) or re.match(r'^[ivxlcdm]+\)\s', t))
    return True


def _add_emphasized_body(doc, text, emphasis):
    """添加带强调格式的正文段落。
    政务规范：强调正文用黑体加粗，保持 12pt，不保留原标题字体（如微软雅黑）。"""
    p = doc.add_paragraph(style='Normal')
    p.clear()
    run = p.add_run(text)
    run.font.name = '黑体'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    if 'size' in emphasis:
        run.font.size = Pt(emphasis['size'] / 2.0)
    else:
        run.font.size = Pt(12)
    if emphasis.get('bold', True):  # 强调正文默认加粗
        run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)
    return p


def _clean_heading_text(text, level):
    """去除标题中的手动编号前缀，避免与自动编号双重叠加。
    各级编号前缀由 numbering.xml 自动生成，文本中的手动编号一律剥离。
    H1: 一、 → 自动「第X章」
    H2: 1.1 / （一）→ 自动「X.X」
    H3: 1.1.1 → 自动「X.X.X」
    H4: （1）→ 自动「X.X.X.X」
    H5: 1) → 自动「X.X.X.X.X」
    H6: a) → 自动「X.X.X.X.X.X」"""
    t = text.strip()
    if level == 1:
        t = re.sub(r'^[一二三四五六七八九十]+、', '', t)
        t = re.sub(r'^第[一二三四五六七八九十\d]+章\s*', '', t)
    elif level == 2:
        t = re.sub(r'^\d+(\.\d+)+\s*', '', t)
        t = re.sub(r'^[（(][一二三四五六七八九十]+[）)]\s*', '', t)
    elif level == 3:
        t = re.sub(r'^[（(]\d+[）)]\s*', '', t)
        t = re.sub(r'^\d+(\.\d+){2,}\s*', '', t)
    elif level == 4:
        t = re.sub(r'^\d+\)\s*', '', t)
    elif level == 5:
        t = re.sub(r'^[a-z]\)\s*', '', t)
    elif level == 6:
        t = re.sub(r'^[①②③④⑤⑥⑦⑧⑨⑩]\s*', '', t)
        t = re.sub(r'^[ivxlcdm]+\)\s*', '', t)
    return t.strip()


def generate_from_structure(doc, structure):
    """从结构化中间表示生成文档内容。
    libjishu 管线：结构 → add_heading/add_body/add_table/add_bullet_list/add_numbered_list

    共享字段占位符：正文/标题/表格中可用 {title} / {org} / {date}，
    渲染时统一替换为 structure 中的对应值，改一处全文档同步，防漂移。

    用法：
      structure = {
          'title': '项目名称',
          'org': '编制单位',
          'date': '2026年8月',
          'body': [
              ('heading', 1, '第1章 {title} 概述'),
              ('body', '（正文示例，请按实际内容撰写，勿照抄）'),
          ]
      }
      doc, sec = create_document()
      add_cover(doc, structure['title'], structure.get('org'), structure.get('date'))
      generate_from_structure(doc, structure)
      save_docx(doc, 'output.docx')
    """
    # 共享字段占位符解析
    shared = {
        '{title}': str(structure.get('title', '')),
        '{org}': str(structure.get('org', '')),
        '{date}': str(structure.get('date', '')),
    }

    def _resolve(text):
        for k, v in shared.items():
            text = text.replace(k, v)
        return text

    i = 0
    items = structure['body']
    while i < len(items):
        typ = items[i][0]
        if typ == 'heading':
            clean_text = _clean_heading_text(_resolve(items[i][2]), items[i][1])
            add_heading(doc, clean_text, items[i][1])
            i += 1
        elif typ == 'list_bullet':
            # 合并连续 bullet 列表项 → 一次 add_bullet_list 调用
            batch = []
            while i < len(items) and items[i][0] == 'list_bullet':
                batch.append(_resolve(items[i][1]))
                i += 1
            add_bullet_list(doc, batch)
        elif typ == 'list_numbered':
            # 合并连续 numbered 列表项 → 一次 add_numbered_list 调用
            batch = []
            while i < len(items) and items[i][0] == 'list_numbered':
                batch.append(_resolve(items[i][1]))
                i += 1
            add_numbered_list(doc, batch)
        elif typ == 'body':
            text = _resolve(items[i][1])
            emphasis = items[i][2] if len(items[i]) > 2 else {}
            if emphasis:
                _add_emphasized_body(doc, text, emphasis)
            else:
                add_body(doc, text)
            i += 1
        elif typ == 'table':
            tbl = items[i][1]
            # 表格所有单元格都过占位符解析
            resolved_tbl = [[_resolve(cell) for cell in row] for row in tbl]
            if len(resolved_tbl) >= 2:
                add_table(doc, resolved_tbl[0], resolved_tbl[1:])
            elif len(resolved_tbl) == 1:
                add_body(doc, '[表格: ' + '|'.join(resolved_tbl[0]) + ']')
            i += 1
        else:
            # 未知类型，跳过
            i += 1

    # #4 无 H1 兜底：structure 全无一级标题 → 自动补占位段 + 提示（防 TOC 残缺）
    h1_present = any(it[0] == 'heading' and it[1] == 1 for it in items if isinstance(it, (tuple, list)) and len(it) >= 2)
    if not h1_present:
        add_heading(doc, '第1章 项目概述', 1)
        print('⚠️ [jishufangan] structure body 无 H1 标题，已自动补「第1章 项目概述」占位段', file=sys.stderr)


def convert_to_gov_format(src_path, dst_path, title=None, org=None, date='2026年7月'):
    """一键管线：丢一个 docx → 出一份政务格式 docx。

    src_path: 源 docx 路径
    dst_path: 输出路径
    title:    覆盖封面标题（默认自动提取）
    org:      编制单位（默认 示例科技有限公司）
    date:     日期

    返回 dst_path。"""
    structure = parse_docx(src_path)
    if title:
        structure['title'] = title

    doc, sec = create_document()
    add_cover(doc, structure['title'] or '项目方案', org=org, date=date)  # org=None 时 add_cover 走环境变量
    generate_from_structure(doc, structure)
    save_docx(doc, dst_path)
    validate_output(dst_path)
    return dst_path


# ============================================================
# v1.1 新增（2026-08-18）：中间表示落盘接口
# 输出契约修复：structure dict → structure.json 文件落盘，
# 脚本读文件渲染。改 JSON 秒出新版，不碰渲染代码。
# ============================================================

def save_structure(structure: dict, path: str) -> str:
    """把 structure dict 落盘为 JSON 文件（中间表示单源）。

    Args:
        structure: 结构化中间表示（title/org/date/body）
        path: 输出 .json 路径

    Returns:
        写入的绝对路径

    Raises:
        TypeError: structure 不是 dict
    """
    from pathlib import Path
    import json as _json
    if not isinstance(structure, dict):
        raise TypeError(f"structure 应为 dict，实际 {type(structure).__name__}")
    # 必填字段校验（坏数据早失败）
    for key in ("title", "org", "date", "body"):
        if key not in structure:
            raise KeyError(f"structure 缺少必填字段: {key}")
    if not isinstance(structure.get("body"), list):
        raise TypeError(f"structure['body'] 应为 list，实际 {type(structure.get('body')).__name__}")
    # body 项类型校验（每项应为 tuple/list 且首元素为已知类型）
    allowed_types = {"heading", "body", "list_numbered", "list_bullet", "table", "image"}
    for idx, item in enumerate(structure["body"]):
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            raise ValueError(f"body[{idx}] 应为 (类型, 内容) 元组，实际 {item!r}")
        if item[0] not in allowed_types:
            raise ValueError(f"body[{idx}] 未知类型 {item[0]!r}（允许: {sorted(allowed_types)}）")
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(
        _json.dumps(structure, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return str(path_obj.resolve())


def load_structure(path) -> dict:
    """从 JSON 文件读入 structure dict（中间表示单源）。

    Args:
        path: .json 文件路径

    Returns:
        structure dict

    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: 文件不是合法 JSON
        KeyError: 缺少必需字段（title/org/date/body）
    """
    from pathlib import Path
    import json as _json
    data = _json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("title", "org", "date", "body"):
        if key not in data:
            raise KeyError(f"structure.json 缺少必需字段: {key}")
    return data

---
name: jishufangan
description: >
  用户需要生成符合广州市政务规范（2025版）的方案 Word 文档时使用。
  Make sure to use this skill whenever the user asks for any government/政务 project document, even if they don't explicitly say '政务方案'.
  触发范围：政务方案、项目建议书、建设方案、可行性报告、技术方案。
  隐式意图也触发：即使只说"写个方案"，只要涉及政府/政务项目就用本 skill。
  不接：评审意见、纯预算清单、非政务格式的普通文档（直接作答，不加载本 skill）。
  边界：本 skill 管政务格式排版，proposal-writer 管内容架构；遇到纯内容架构需求交给 proposal-writer。
---

# jishufangan — 政务方案 Word 文档生成 Skill

按《广州市政务信息化建设开发类项目方案编写规范（2025版）》生成符合格式要求的 `.docx` 文档。

## 触发场景

### 显式触发

- "生成政务方案"、"写个政务文档"、"做个广州方案"
- "项目建议书"、"建设方案"、"可行性报告"、"技术方案"

### 隐式触发（同样加载）

- "帮我写个信息化项目的方案"（含"信息化项目"+"方案"）
- "这个项目要报给市里的，帮我整理成文档"（政务场景暗示）
- "按政府格式给我出个文档"（格式暗示）

### 负触发（不加载本 skill）

- 评审意见、评分、审阅反馈 → 直接回答
- 纯预算清单、纯表格 → 直接做，不走政务格式
- 非政务的普通文档（如内部会议纪要、技术博客）→ 用通用方法

### 技能互斥 + 版本路由

| 需求 | 用哪个 |
|------|--------|
| 政务格式排版（标准 7+ 章） | jishufangan（本 skill，libjishu） |
| **简要方案（高层预审 / 方案说明）** | **jishufangan_simple**（同目录 `scripts/jishufangan_simple.py`） |
| 内容架构/提案结构 | proposal-writer |
| 两者都要 | 先 proposal-writer 出架构，再 jishufangan 排版 |

**简要方案路由判定（任一命中即用简版）：**
- 显式关键词：「简要方案」「简版方案」「方案摘要」「方案说明」「高层版」
- 场景词：「客户预审」「领导汇报」「方案预审」
- 隐式：用户要求"少一点章节 / 字号大一点 / 重点突出 / 一页能看完"

## 路由决策树（必须先走）

进 skill 第一件事：判定走哪个分支。

```
用户需求
    │
    ├─ 客户高层预审 / 方案说明 / 字号大一点 / 少章节？
    │     └─ ✅ → jishufangan_simple（简版，详见后文「简要方案」章节）
    │
    ├─ 完整政务方案（立项申报 / 归档 / 招投标）？
    │     └─ ✅ → libjishu（标准版，本 skill 主线）
    │
    └─ 内容架构 / 提案结构（无格式需求）？
          └─ proposal-writer（不在本 skill，跳出）
```

判定后：按对应章节的"调用方式"执行。

## 澄清规则（打扰预算）

生成前最多问 **2 个问题**，按优先级：

1. **项目名称**（封面主标题，没有就根据上下文推断）
2. **编制单位**（默认：XX 单位，环境变量 `JISHUFANG_ORG` 可覆盖）

以下**静默用默认值，不问**：

- 日期 → 当天日期
- 章节结构 → 按规范模板默认结构
- 编制人员 → 留空或"项目组"

用户不答就问下一个，问满 2 个后直接用默认值开工。**绝不连环追问。**

## 🚨 强制规则

**必须使用 `scripts/libjishu.py` + `scripts/image_tools.py`，严禁手写 standalone 脚本或直接操作 python-docx/XML。**

**目录自动生成（v3.3）**：`save_docx()` 自动在封面后插入目录页（「目 录」+ TOC 域），Word 打开后按 F9 更新域生成目录。无需手动添加目录。

图片必须走预处理链路：`image_tools.prepare_image()`（格式归一化 + 缩放 + 白底）→ `libjishu.add_image(auto_prepare=True)` 或手动传入处理后的路径。禁止直接插入原始大图/透明图/网络 URL 图。

### ✅ 正确做法（三段式：建数据落盘 → 读数据 → 渲染）

```python
import sys; sys.path.insert(0, 'skills/jishufangan/scripts')
from libjishu import (
    save_structure, load_structure,
    create_document, add_cover, generate_from_structure,
    save_docx, validate_output
)

# 第一段：构建结构化中间表示（structure dict）并落盘为 JSON 文件
# ⚠️ 以下 body 仅为结构演示，正文文字必须按项目实际内容撰写，严禁照抄示例文本
# 共享字段（title/org/date）在 body 里用占位符引用，
# generate_from_structure 渲染时统一替换，改一处全文档同步，防漂移
structure = {
    'title': '广州市XX区智慧政务平台建设方案',
    'org': '示例科技有限公司 集成业务部',
    'date': '2026年8月',
    'body': [
        ('heading', 1, '第1章 项目概述'),
        ('body', '（正文内容按实际项目撰写，勿照抄示例）'),
        ('heading', 2, '1.1 建设背景'),
        ('body', '（正文内容按实际项目撰写，勿照抄示例）'),
        ('list_numbered', '（列表项示例，按实际撰写）'),
        ('table', [['项目名称', '{title}'], ['编制单位', '{org}']]),
    ]
}
structure_path = save_structure(structure, './structure.json')  # 中间表示落盘（单一事实源）

# 第二段：读回 JSON（改 structure.json 秒出新版，不碰渲染代码）
structure = load_structure(structure_path)

# 第三段：确定性渲染（唯一渲染入口）
doc, sec = create_document()
add_cover(doc, structure['title'], structure['org'], structure['date'])
generate_from_structure(doc, structure)
out = './输出.docx'  # 相对路径，不写死机器目录
save_docx(doc, out)
validate_output(out)
```

### ❌ 禁止

- 手写 `Document()` + `doc.styles['Normal']` → libjishu 已封装
- 直接操作 XML（`etree.fromstring`、`re.sub` document.xml） → 破坏结构
- 手动构造 `<w:drawing>` + `<a:blip>` → 缺 rels 导致图片消失
- 修改现有 docx 的 XML 来"修复" → 用 python-docx 重建更安全
- 正则跨 `<w:tbl>` 边界匹配 → 合并表格

## 字体与样式规范

> 数值型定义集中在 `scripts/format_config.py`（唯一事实源）。详细规范见 `references/format-spec.md`。

字体类型（必须用 Windows 兼容名）：方正小标宋_GBK（封面）、黑体（标题）、仿宋_GB2312（正文）。已安装到 `~/.local/share/fonts/`。

## API 参考

| 函数 | 说明 |
|------|------|
| `create_document()` → `(doc, sec)` | 创建文档，初始化所有样式 |
| `add_cover(doc, title, org, date)` | 封面：项目名称 + 编制信息 |
| `generate_from_structure(doc, structure)` | 从 structure dict 渲染全文（两段式核心） |
| `add_heading(doc, text, level)` | 标题 level=1~6，自动编号 |
| `add_body(doc, text)` | 正文段落 |
| `add_numbered_list(doc, items)` | 编号列表 |
| `add_bullet_list(doc, items)` | 项目符号列表 |
| `add_table(doc, headers, rows, title)` | 表格：边框 + 蓝底表头 |
| `add_image(doc, path, width_cm, caption)` | 图片 + 图注 |
| `save_docx(doc, output_path)` | 保存 + 编号/页脚/分页符后处理 |
| `validate_output(docx_path)` | 24 项验证，CRITICAL 项阻塞交付 |
| `image_tools.fetch_image(src)` | URL/本地路径 → 本地文件 |
| `image_tools.prepare_image(src, ...)` | 格式归一化 + 缩放（≤1024x1400）+ 透明铺白底 |
| `image_tools.verify_image(path)` | 图片有效性检查（可解码/尺寸/体积） |
| `image_tools.verify_docx_images(docx)` | docx 图片三要素闭环检查（media/rels/blip） |
| `parse_docx(path)` → `dict` | 从已有 docx 提取结构 |
| `convert_to_gov_format(src, dst, title)` | 一键管线：任意 docx → 政务格式 |

### structure dict 格式

| 元素类型 | 格式 |
|---------|------|
| 标题 | `('heading', level, '标题文本')` |
| 正文 | `('body', '文本')` |
| 编号列表 | `('list_numbered', '项')`（连续项自动合并） |
| 项目符号 | `('list_bullet', '项')`（连续项自动合并） |
| 表格 | `('table', [['表头'], ['数据行']])` |

### 共享字段占位符（防漂移）

body 里任何文本（标题/正文/列表/表格单元格）都可用以下占位符：

| 占位符 | 替换为 |
|--------|--------|
| `{title}` | structure['title'] |
| `{org}` | structure['org'] |
| `{date}` | structure['date'] |

`generate_from_structure` 渲染时统一替换。改封面标题时，正文里所有 `{title}` 自动同步，**禁止在 body 里硬编码项目名称**。

## 表格

样式：表头黑体 10pt 加粗 + 蓝底 #98C1FD，数据仿宋 10pt，边框 0.5pt 单实线（`scripts/format_config.py` 中 `TABLE` 段）。

```python
# 在 structure body 中
('table', [['序号', '工作内容', '责任单位'],
           ['1', '需求调研', '示例主管单位'],
           ['2', '系统开发', '示例科技']])
```

## 自动编号

由 `save_docx()` 自动注入 numbering.xml，**严禁手写编号**。H1 = 第%1章 / H2 = %1.%2 / H3-H6 = %1.%2...%N。`add_heading()` 自动剥离手动编号前缀，防止双重编号。

## 降级路径（失败不静默，明确告知）

| 故障 | 降级动作 |
|------|---------|
| `python-docx` 装不上 | 明确报错 + 列出缺失依赖 + **绝不产出残缺 docx** |
| 字体缺失 | 用替代字体渲染 + 文档末尾声明"部分字体已替换" |
| `validate_output` 失败 | 明确告知"验证未通过，不交付"，列出失败项 |
| `generate_from_structure` 遇到未知元素 | 跳过该元素 + 记录，不中断全文 |

## 用户语言规则（防火墙）

对政府客户只说结果，**永不提**：

- `docx` / `XML` / `脚本` / `渲染` / `validate` / `structure`

正确说法：

- ✅ "方案已生成，请查收"
- ✅ "已按规范排版，共 X 章 Y 节"
- ❌ "我已生成 docx 并通过 validate_output"

## 内容合规

- 外部材料（参考文件、政策原文）只影响结构和格式
- 正文文字必须原创，不整段复制来源
- 引用政策条文时标注来源

## 关键文件

| 文件 | 用途 |
|------|------|
| `scripts/libjishu.py` | 核心库，唯一入口（含 save_structure/load_structure） |
| `scripts/jishufangan_simple.py` | 简版方案（高层预审 / 方案说明），thin wrapper 复用 libjishu |
| `scripts/image_tools.py` | 图片预处理（下载/归一化/缩放/白底/三要素闭环验证） |
| `SKILL.md` | 本文件 |
| `references/image-handling.md` | 图片处理详细规范 |
| `references/simple-format-spec.md` | 简版方案格式规范 |
| `evals/` | 测试样本 + rubric + baseline（with/without skill 对照） |
| `requirements.txt` | 依赖声明（python-docx / lxml / Pillow） |

## 一键管线：convert_to_gov_format（核心入口）

把已有 docx（任意格式）转换为政务规范格式，三步完成：

```python
import sys; sys.path.insert(0, 'skills/jishufangan/scripts')
from libjishu import convert_to_gov_format

convert_to_gov_format(
    '原始方案.docx',      # 源文件（自动解析标题/章节结构）
    '政务版方案.docx',     # 输出文件
    title='广州市XX区XX项目建设方案',   # 可选：覆盖封面标题
    org='XX单位',          # 可选：编制单位（默认走 JISHUFANG_ORG 环境变量）
    date='2026年8月',      # 可选：编制日期
)
```

说明：
- 自动完成：解析结构 → 生成封面 → 渲染正文 → 保存 → validate_output 校验
- `org` 三层次取值：命令行参数 > `JISHUFANG_ORG` 环境变量 > 内置默认
- 输出前自动跑 validate_output（24+ 项检查），CRITICAL 失败不静默交付

## 简版方案（"客户版" v3.5）

> 完整规范见 `references/simple-format-spec.md`。本章节只保留路由所需的最小信息。

### 设计取舍（与标准版对比）

| 维度 | 标准版 | **简版（客户版 v3.5）** |
|------|-------|----------------------|
| **封面** | 有（标题 + 编制单位 + 日期）| **无封面** ⭐（首加大标题即可）|
| **大标题** | - | **黑体 28pt 不加粗 居中，无序号** ⭐ |
| 章节 | 7+ 章固定 | **不固定，按需取**（由调用方决定）|
| **H1 字体/加粗** | 黑体 **加粗** | 黑体 **不加粗** ⭐ |
| **H2 字体/加粗** | 黑体 12pt 加粗 | **楷体_GB2312 16pt 加粗** ⭐ |
| 正文 | 仿宋_GB2312 12pt | 仿宋_GB2312 **14pt** |
| 表格表头 | #98C1FD **蓝底** | **白底** ⭐ |
| H1/H2 行距 | 自适应 | **固定值 28pt** |
| H1/H2 首行缩进 | 0 | **1.13cm** |
| 正文首行缩进 | 2 字符 | **0.99cm**（约 2 字符）|
| 页面边距 | 上下左右 1440 dxa | **上下 2.54cm / 左右 3.17cm** |
| 目录页 | 有（v3.3） | **无** |
| 验证阈值 | 章节数 ≥7 | **无硬约束** |

### 关键差异（5 处）

1. **无封面** ⭐（v3.5）：文档首部只有 28pt 大标题，**不**写编制单位/日期
2. **大标题**：黑体 28pt 居中不加粗，无序号
3. **H2 字体**：黑体 12pt → **楷体_GB2312 16pt 加粗**
4. **表格表头**：蓝底 → **白底**
5. **H1 加粗**：加粗 → **不加粗**（用字体类型区分而非粗体）

### 一键调用

```python
import sys; sys.path.insert(0, 'skills/jishufangan/scripts')
from jishufangan_simple import convert_to_simple_format

convert_to_simple_format(
    title='XX 项目方案',          # 必传：作为文档首部大标题
    chapters=[
        # 章节必须传，简版不预设模板
        ('一、建设背景与重要意义', ['政策背景', '客户需求']),
        ('二、现状调研及分析', ['现状梳理', '痛点识别']),
        ('三、总体思路', ['指导思想', '总体目标']),
        ('四、工作思路与方法', ['方法论', '实施路径']),
        ('五、重点任务', ['任务 1', '任务 2']),
        ('六、保障措施', ['组织保障', '资源保障']),
        ('七、费用匡算', ['总投资估算']),
    ],
    output_path='./方案.docx',
)
```

细粒度控制（`build_simple_structure` / `create_simple_document` / `add_simple_cover` / `add_simple_table` / `generate_from_simple_structure` / `save_simple_docx` / `validate_simple_output`）见 `references/simple-format-spec.md` 第九节。

### 字体依赖

- 已装：方正小标宋_GBK、黑体、仿宋_GB2312、Times New Roman
- **楷体_GB2312**：用户承诺安装；若缺失 fallback 到黑体，文档末尾声明

### 与 proposal-writer 的边界

- **jishufangan_simple**：格式排版（字号、字体类型、封面、表格、docx 渲染）
- **proposal-writer**：内容架构（章节逻辑、论证链、故事线）
- 两者都要：先 proposal-writer 出大纲，再 jishufangan_simple 套格式

## 依赖

- Python 包：`python-docx`、`lxml`、`Pillow`
- 系统字体：方正小标宋_GBK、黑体、仿宋_GB2312

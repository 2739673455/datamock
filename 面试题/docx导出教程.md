# Markdown 按文档模板导出 Word 教程
本文用于把 Markdown 文档按照 `文档模板.docx` 的要求导出为 Word 文档，适用于 `面试题/` 目录下的项目面试题、串讲稿和专题文档。

## 1. 模板文件
模板文件路径：

```bash
面试题/文档模板.docx
```

输出 Word 必须以该文件作为样式参考。

## 2. 模板样式
`文档模板.docx` 中常用样式如下：

| 用途         | 样式 ID | 样式名称     |
| ------------ | ------- | ------------ |
| 文档主标题   | `af4`   | 文档主标题   |
| 作者副标题   | `af6`   | 次标题       |
| 版本号       | `af8`   | 版本号       |
| 一级标题     | `a`     | 一级标题     |
| 二级标题     | `a0`    | 二级标题     |
| 三级标题     | `a1`    | 三级标题     |
| 四级标题     | `a2`    | 四级标题     |
| 五级标题     | `a3`    | 半括号标题   |
| 正文         | `afc`   | 文档正文样式 |
| 无序参数列表 | `a5`    | 参数列表样式 |
| 有序步骤列表 | `a4`    | 圆括号标题   |

## 3. 标题层级映射
Markdown 标题层级必须保持不变，只替换为模板对应样式。

| Markdown 标题 | Word 样式 |
| ------------- | --------- |
| `#`           | `a`       |
| `##`          | `a0`      |
| `###`         | `a1`      |
| `####`        | `a2`      |
| `#####`       | `a3`      |

如果 Markdown 正文从 `##` 开始，Word 正文也必须从二级标题样式 `a0` 开始，不能提升为一级标题。

## 4. 文档开头
文档标题、作者和版本号使用普通文本，不使用 Markdown 标题。

推荐格式：

```markdown
归因与舆情项目面试题

（作者：尚硅谷研究院）

版本：V1.0
```

导出后样式映射为：

| 内容     | Word 样式 |
| -------- | --------- |
| 文档标题 | `af4`     |
| 作者     | `af6`     |
| 版本号   | `af8`     |

## 5. 列表样式
无序列表使用模板参数列表样式 `a5`。

```markdown
- 参数一
- 参数二
- 参数三
```

有序步骤列表使用模板圆括号标题样式 `a4`。

```markdown
1. 第一步
2. 第二步
3. 第三步
```

有序列表每一组单独从 1 开始。

## 6. 基础导出命令
先用 Pandoc 生成基础 Word 文件：

```bash
pandoc /tmp/input.md \
  --from=markdown \
  --reference-doc=面试题/文档模板.docx \
  --resource-path=面试题 \
  -o /tmp/output.base.docx
```

`--reference-doc` 只负责带入模板样式，不保证 Markdown 标题和列表自动落到模板自定义样式上。

## 7. 后处理规则
基础 Word 文件生成后，需要检查并修正 `word/document.xml` 中的段落样式。

推荐映射：

| Pandoc 默认样式      | 目标模板样式 |
| -------------------- | ------------ |
| `Title` 或文档第一段 | `af4`        |
| 作者段               | `af6`        |
| 版本段               | `af8`        |
| `1`                  | `a`          |
| `2`                  | `a0`         |
| `3`                  | `a1`         |
| `4`                  | `a2`         |
| `FirstParagraph`     | `afc`        |
| `BodyText`           | `afc`        |
| `Compact` 无序列表   | `a5`         |
| `Compact` 有序列表   | `a4`         |

Markdown 标题已经带有 `5.1.1` 这类手写编号时，标题样式不能再启用 Word 自动标题编号，否则会出现双编号。

## 8. 命名空间要求
后处理 docx 时必须保留 Office OpenXML 命名空间前缀。

重点检查文件：

```bash
word/document.xml
word/styles.xml
word/numbering.xml
```

`styles.xml` 和 `numbering.xml` 中如果存在 `mc:Ignorable="w14 w15 w16se w16cid w16 w16cex w16sdtdh"`，根节点必须声明这些前缀。

正确示例：

```xml
xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"
xmlns:w16se="http://schemas.microsoft.com/office/word/2015/wordml/symex"
xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid"
xmlns:w16="http://schemas.microsoft.com/office/word/2018/wordml"
xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex"
xmlns:w16sdtdh="http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash"
```

`numbering.xml` 如果 `mc:Ignorable` 中包含 `wp14`，根节点还必须声明：

```xml
xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
```

## 9. 验证命令
检查 docx 压缩包结构：

```bash
unzip -t 面试题/输出文件.docx
```

检查核心 XML 是否可解析：

```bash
python3 - <<'PY'
from zipfile import ZipFile
import xml.etree.ElementTree as ET

path = '面试题/输出文件.docx'
parts = [
    'word/document.xml',
    'word/styles.xml',
    'word/numbering.xml',
    '[Content_Types].xml',
    'word/_rels/document.xml.rels',
]

with ZipFile(path) as z:
    for part in parts:
        ET.fromstring(z.read(part))
        print(part, 'OK')
PY
```

检查 `mc:Ignorable` 引用的前缀是否都已声明：

```bash
python3 - <<'PY'
from zipfile import ZipFile
import re

path = '面试题/输出文件.docx'
parts = ['word/styles.xml', 'word/numbering.xml']

with ZipFile(path) as z:
    for part in parts:
        data = z.read(part).decode('utf-8')
        root = re.search(r'<w:[^>]+>', data).group(0)
        declared = set(re.findall(r'xmlns:([A-Za-z_][\w.-]*)=', root))
        ignorable = re.search(r'mc:Ignorable="([^"]+)"', root)
        missing = []
        if ignorable:
            missing = [p for p in ignorable.group(1).split() if p not in declared]
        print(part, missing)
PY
```

检查标题和列表是否落到模板样式：

```bash
python3 - <<'PY'
from zipfile import ZipFile
import xml.etree.ElementTree as ET

path = '面试题/输出文件.docx'
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{%s}' % ns['w']
bad = {}

with ZipFile(path) as z:
    root = ET.fromstring(z.read('word/document.xml'))

for p in root.findall('.//w:p', ns):
    text = ''.join(t.text or '' for t in p.findall('.//w:t', ns)).strip()
    if not text:
        continue
    style_el = p.find('./w:pPr/w:pStyle', ns)
    style = style_el.attrib.get(W + 'val') if style_el is not None else ''
    if style in ['FirstParagraph', 'BodyText', 'Compact', '1', '2', '3', '4']:
        bad[style] = bad.get(style, 0) + 1

print(bad)
PY
```

结果中不应再出现 `FirstParagraph`、`BodyText`、`Compact`、`1`、`2`、`3`、`4`。

## 10. 内容反查
用 Pandoc 反向读取 Word，检查正文内容和标题文字：

```bash
pandoc 面试题/输出文件.docx -t markdown --wrap=none | sed -n '1,80p'
```

该检查只能确认内容可读，不能替代 Word 样式和命名空间检查。

## 11. 常见陷阱
`--reference-doc` 不会自动把所有标题映射到模板自定义样式。

Pandoc 默认生成的标题样式可能是 `1`、`2`、`3`、`4`，不等同于模板里的 `a`、`a0`、`a1`、`a2`。

Pandoc 默认生成的列表样式可能是 `Compact`，不等同于模板里的 `a5` 和 `a4`。

Markdown 已有手写编号时，不能再启用 Word 标题自动编号。

只执行 `unzip -t` 不能证明 Word 一定能打开。

只用 XML 解析器验证不能证明 Word 一定能打开。

使用 Python 标准库 `xml.etree.ElementTree` 重写整个 XML 时，容易把 `mc`、`w14`、`w15` 等前缀改成 `ns1`、`ns2`，需要恢复根节点命名空间声明。

`mc:Ignorable` 中出现的每个前缀都必须在当前 XML 根节点声明。

`document.xml`、`styles.xml`、`numbering.xml` 都需要单独检查。

Word 报“发现无法读取的内容”时，优先检查 `styles.xml` 和 `numbering.xml` 的命名空间声明。

## 12. 交付清单
交付前必须完成以下检查：

1. `unzip -t` 无错误
2. 核心 XML 可解析
3. `mc:Ignorable` 前缀声明完整
4. 标题样式为模板样式
5. 正文样式为 `afc`
6. 无序列表样式为 `a5`
7. 有序列表样式为 `a4`
8. 不存在 `Compact`、`BodyText`、`FirstParagraph`、`1`、`2`、`3`、`4`
9. Markdown 反查内容完整
10. Word 本地打开无恢复提示

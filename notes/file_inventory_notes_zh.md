# Step 1 File Inventory 说明

本文档记录当前 Step 1 `file_inventory` 的本地实现。Step 1 的目标是：输入一个 site 文件夹，自动生成 `site_inventory.partial.json`，记录这个文件夹里有哪些源文件、文件格式、基础可读性、文件名线索和推荐 parser。

这一阶段只做文件夹级盘点，不抽取 MAPEM facts，不解析 CAD 几何，不读取 PDF/DOCX 表格内容，也不输出 `junction_type`、`controller_type`、`stream_count`、`site_level_hints`、`manual_questions` 等后续语义字段。

## 1. 创建和修改的文件

### 1.1 核心实现文件

位置：

```text
src/mapemgen/ingestion/inventory.py
```

作用：

- 实现 Step 1 file inventory 的主要逻辑。
- 提供 `build_site_inventory(site_folder, site_id, site_name="", dataset="") -> dict`。
- 递归扫描输入文件夹中的所有文件。
- 为每个文件生成 `source_files` 条目。
- 汇总文件数量、文件类型数量、可读文件数量和不可读文件数量。
- 根据文件扩展名推荐第一版 parser。
- 根据文件名关键词生成 `filename_hints`。
- 对 ZIP 文件只检查压缩包文件列表，不解压，不解析 DWG 内容。

主要函数：

```text
build_site_inventory(...)
```

这是外部调用入口。它接收 site 文件夹路径和 site metadata，返回一个可直接写成 JSON 的 dict。

```text
_iter_files(folder)
```

递归扫描文件夹，返回所有普通文件。当前使用 `Path.rglob("*")`。

```text
_build_source_file(path)
```

为单个文件生成 inventory 条目，包括：

- `file_path`
- `file_type`
- `file_size_bytes`
- `filename_hints`
- `readable_status`
- `parser_to_use`
- `notes`

```text
_file_type(path)
```

读取文件扩展名，并统一转成小写。例如 `.8TX` 会变成 `8tx`。

```text
_filename_hints(path)
```

根据文件名关键词生成提示。当前支持：

| 文件名关键词 | 生成 hint |
| --- | --- |
| `Spec`, `2500Config`, `Configuration` | `possible configuration file` |
| `Drawing`, `AsBuilt`, `DetailedDesign` | `possible drawing / layout file` |
| `UTCForm` | `possible UTC form` |
| `SCOOTDets` | `possible SCOOT detector data` |
| `RAMData` | `possible RAM / override data` |
| `MOVA` | `possible MOVA/control logic data` |

如果 ZIP 文件的文件列表中包含 `.dwg` 成员，还会额外加：

```text
possible CAD package
```

这里的意思是：这个 ZIP 可能是 CAD 图纸包。当前只扫描 ZIP 的文件名列表，不解压 ZIP，也不解析 DWG 内容。

```text
_readability(path, file_type)
```

判断文件基础可读性。当前状态包括：

| 状态 | 含义 |
| --- | --- |
| `text_readable` | 文本类文件可以作为文本/字节文件打开，例如 `.txt`、`.8tx` |
| `archive_readable` | ZIP 文件可以被 Python 标准库打开并读取目录表 |
| `available_not_directly_readable` | 文件存在，但 Step 1 不直接解析内容，例如 `.pdf`、`.docx`、`.dwg`、`.dxf`、`.mova` |
| `available_unknown_format` | 文件存在，但扩展名没有对应 parser |
| `unreadable` | 文件无法打开，或 ZIP 损坏/不可读 |

```text
_zip_readability(path)
```

检查 ZIP 能否打开并读取成员列表。

```text
_zip_contains_extension(path, ".dwg")
```

检查标准 ZIP 文件的成员名里是否有 `.dwg` 文件。它不会递归打开嵌套 ZIP，也不会判断 DWG 内容是否有效。

### 1.2 CLI 修改文件

位置：

```text
src/mapemgen/cli.py
```

具体添加内容：

- 在文件顶部新增导入：

```python
from mapemgen.ingestion.inventory import build_site_inventory
```

- 在 `build_parser()` 中新增 `inventory` 子命令。
- 新增 5 个命令行参数：
  - `--site-folder`
  - `--out-dir`
  - `--site-id`
  - `--site-name`
  - `--dataset`
- 在 `main()` 中新增 `if args.command == "inventory"` 分支。
- 该分支调用 `build_site_inventory(...)` 生成 inventory dict。
- 使用项目已有的 `write_json(...)` 写出 `site_inventory.partial.json`。
- 执行完成后返回 exit code `0`。

新增命令：

```bash
mapemgen inventory --site-folder <path> --out-dir <path> --site-id <id> --site-name <name> --dataset <dataset>
```

参数含义：

| 参数 | 是否必填 | 含义 |
| --- | --- | --- |
| `--site-folder` | 是 | 要扫描的 site 文件夹路径 |
| `--out-dir` | 是 | inventory JSON 输出目录 |
| `--site-id` | 是 | site id，例如 `1003`、`397L` |
| `--site-name` | 否 | site name；不提供时默认使用文件夹名 |
| `--dataset` | 否 | 数据来源或 local authority，例如 `DCIS/Bathnes`、`Leeds` |

CLI 执行流程：

1. 解析命令行参数。
2. 如果命令是 `inventory`，调用 `build_site_inventory(...)`。
3. 使用现有 `write_json(...)` 写出 JSON。
4. 输出文件固定为：

```text
<out-dir>/site_inventory.partial.json
```

原有命令 `validate` 和 `generate` 没有改变。

### 1.3 测试文件

位置：

```text
tests/test_inventory.py
```

作用：

- 验证 Step 1 file inventory 的核心行为。
- 使用 synthetic files，不依赖 confidential raw data。
- 测试临时文件写在 `outputs/` 下，因为 `outputs/` 已在 `.gitignore` 中。

当前测试覆盖：

1. `build_site_inventory(...)` 能扫描 `.txt`、`.8TX`、`.zip`、`.mova`、`.bin`、`.docx`。
2. 文件类型统计正确。
3. `.8TX` 会统一为 `8tx`。
4. `source_files` 按路径排序，保证输出稳定。
5. parser routing 正确。
6. readability status 正确。
7. `RAMData`、`MOVA`、`UTCForm`、`Spec`、`Drawing` 能生成对应 hints。
8. ZIP 里如果有 `.dwg` 成员，会生成 `possible CAD package`。
9. 输出中没有 Step 2 语义字段：
   - `junction_type`
   - `controller_type`
   - `stream_count`
   - `site_level_hints`
   - `manual_questions`
10. CLI 能写出 `site_inventory.partial.json`。

## 2. Parser routing 第一版规则

当前 parser routing 先硬编码在：

```text
src/mapemgen/ingestion/inventory.py
```

映射如下：

| 文件类型 | 推荐 parser |
| --- | --- |
| `pdf` | `pdf_parser` |
| `docx` | `docx_parser` |
| `dwg` | `cad_parser_after_conversion` |
| `dxf` | `cad_parser` |
| `zip` | `zip_inventory_parser` |
| `txt` | `ram_text_parser` |
| `8tx` | `ram_text_parser` |
| `mova` | `mova_availability_recorder` |
| `geojson` | `gis_parser` |
| `json` | `gis_parser` |
| `osm` | `gis_parser` |
| `gpkg` | `gis_parser` |
| `shp` | `gis_parser` |
| unknown extension | `manual_review` |

后续如果规则变多，可以迁移到 `configs/` 下的配置文件。

## 3. 整体流程

Step 1 的整体流程是：

```text
site_folder_path
        |
        v
递归扫描所有文件
        |
        v
对每个文件读取扩展名、大小、文件名关键词
        |
        v
判断基础可读性
        |
        v
按扩展名推荐 parser
        |
        v
统计 total_files / file_type_counts / readable_files / unreadable_files
        |
        v
写出 site_inventory.partial.json
```

Step 1 不做：

- 不解析 PDF 表格。
- 不解析 DOCX 内容。
- 不转换 DWG/DXF。
- 不抽取 lane、stop line、signal head。
- 不判断 phase、stage、stream。
- 不生成 MAPEM field evidence。

## 4. 功能使用方法和产出位置

### 4.1 命令行使用方法

在项目根目录下运行时，推荐使用下面这个模板。尖括号里的内容需要用户按自己的 site 手动填写：

```powershell
cd <项目根目录>
$env:PYTHONPATH='src'; python -m mapemgen.cli inventory `
  --site-folder <要扫描的site文件夹路径> `
  --site-id <site_id> `
  --site-name "<site_name，可选>" `
  --dataset "<数据集或local authority，可选>"
```

`--out-dir` 可以不填。不填时，程序会自动使用输入 site 文件夹名作为输出文件夹名。

例如输入文件夹是：

```text
local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge
```

默认产出位置就是：

```text
outputs/1003_LondonRdClevelandBridge/site_inventory.partial.json
```

产出文件名由程序自动确定，固定为 `site_inventory.partial.json`。

例如：

```powershell
cd C:\Users\leovo\Desktop\GDP
$env:PYTHONPATH='src'; python -m mapemgen.cli inventory `
  --site-folder local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge `
  --site-id 1003 `
  --site-name "London Rd Cleveland Bridge" `
  --dataset "DCIS/Bathnes"
```

如果当前环境已经把 `mapemgen` 安装成命令行工具，也可以使用下面这个模板：

```bash
mapemgen inventory \
  --site-folder <site_folder_path> \
  --site-id <site_id> \
  --site-name "<site_name_optional>" \
  --dataset "<dataset_optional>"
```

如果用户想指定自己的输出文件夹，也可以额外加：

```powershell
--out-dir <自定义inventory输出文件夹>
```

最小必填参数是：

```powershell
cd <项目根目录>
$env:PYTHONPATH='src'; python -m mapemgen.cli inventory `
  --site-folder <要扫描的site文件夹路径> `
  --site-id <site_id>
```

如果不提供 `--site-name`，程序会使用 site 文件夹名作为 `site_name`。如果不提供 `--dataset`，`local_authority_or_dataset` 会是空字符串。如果不提供 `--out-dir`，程序会输出到 `outputs/<输入site文件夹名>/site_inventory.partial.json`。

### 4.2 Python 代码中直接调用

也可以在 Python 代码中直接调用：

```python
from mapemgen.ingestion.inventory import build_site_inventory

inventory = build_site_inventory(
    "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge",
    site_id="1003",
    site_name="London Rd Cleveland Bridge",
    dataset="DCIS/Bathnes",
)
```

这个函数只返回 Python dict，不负责写文件。如果要写出 JSON，可以使用项目已有的 `write_json(...)`：

```python
from mapemgen.io import write_json

write_json("outputs/1003/site_inventory.partial.json", inventory)
```

## 5. 示例输出

示例：

```json
{
  "site_id": "1003",
  "site_name": "London Rd Cleveland Bridge",
  "local_authority_or_dataset": "DCIS/Bathnes",
  "input_folder_path": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge",
  "inventory_summary": {
    "total_files": 3,
    "file_type_counts": {
      "8tx": 1,
      "txt": 1,
      "zip": 1
    },
    "readable_files": 3,
    "unreadable_files": 0
  },
  "source_files": [
    {
      "file_path": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/1003_RAMData_Jan26.8tx",
      "file_type": "8tx",
      "file_size_bytes": 12345,
      "filename_hints": ["possible RAM / override data"],
      "readable_status": "text_readable",
      "parser_to_use": "ram_text_parser",
      "notes": ""
    },
    {
      "file_path": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/T1003 Cleveland Place - Standard.zip",
      "file_type": "zip",
      "file_size_bytes": 67890,
      "filename_hints": ["possible CAD package"],
      "readable_status": "archive_readable",
      "parser_to_use": "zip_inventory_parser",
      "notes": ""
    }
  ]
}
```

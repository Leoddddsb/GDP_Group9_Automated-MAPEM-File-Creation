# Step 2 按文件格式抽取 Facts 设计

## 目标

实现 MAPEM pipeline 的 Step 2：递归扫描完整 site 文件夹，将每个源文件交给对应
格式的解析器，并输出统一的 `extracted_facts.partial.json`。Step 2 和 Step 1
生成的 `site_inventory.partial.json` 相互独立。

首版负责抽取 MAPEM 相关候选 facts 和证据来源。它不负责把候选 facts 匹配到
最终 MAPEM 字段，也不负责 evidence fusion。对于扫描版 PDF 页面，它可以执行
可选 OCR/CV，并把结果记录为低置信度候选 facts。

## 架构

采用统一抽取调度器和独立格式解析器。调度器递归扫描完整 site 文件夹，根据文件
类型选择 parser，捕获单个文件的解析错误，并按照稳定路径顺序为每个源文件生成
一条结果。

每个 parser 遵循相同的概念接口：

```python
def extract_<format>_facts(path: str | Path) -> list[dict]:
    ...
```

每个 fact 包含：

```json
{
  "fact_type": "phase_label",
  "value": "A",
  "evidence_location": "site-folder/forms/1062_UTCForm_Jan24.docx -> table 2 row 4",
  "confidence": 0.9
}
```

`evidence_location` 是 provenance chain。调度器会在每个 fact 前面加入从 site
文件夹中扫描到的源文件路径。parser 再追加对应格式的内部位置，例如 page、line、
paragraph、table row、CAD entity、GIS feature 或 ZIP member。

示例：

```text
site-folder/reports/config.pdf -> page 1 line 16
site-folder/packages/drawings.zip -> archive member xref/OS-TOPO.dwg -> modelspace
```

该信息会与文件级 `source_file` 字段存在部分重复，这是有意保留的设计：当 fact
脱离外层 wrapper 被单独查看、筛选或复制时，仍然能够追溯完整来源。

### 置信度定义

`confidence` 是范围为 `0.0` 到 `1.0` 的规则型 evidence-strength 分数。它不是
经过统计校准的概率，也不表示候选内容已经被接受为最终 MAPEM 字段。Step 2 使用
该分数描述 parser 观察或推导 fact 的依据有多直接。后续 evidence-fusion 步骤仍需
解决冲突、比较独立来源，并判断候选内容是否可用。

分数区间含义：

| 区间 | 含义 |
| --- | --- |
| `1.0` | 确定性观察结果或 workflow 状态，例如 ZIP member、不安全路径拒绝结果、文件大小、PDF 缺少文本或必须通过 MOVA Tools 导出 |
| `0.85` 到 `0.95` | 从字段、tag、已解析 CAD 结构或精确 metadata pattern 直接读取的强结构化证据 |
| `0.70` 到 `0.80` | 仍需语义解释的结构化候选，例如 geometry、table row、PDF 图片页特征、CAD label 或文件名分类 |
| `0.60` 到 `0.69` | 基于 keyword 或派生近似值的启发式候选 |
| 低于 `0.60` | 来自图片识别或 OCR 的弱候选，需要其他来源佐证或人工复核 |

当前默认值：

| Fact 来源 | Confidence | 原因 |
| --- | --- | --- |
| TXT、DOCX 或 PDF keyword candidate | `0.65` | keyword 可以定位相关文本行，但不能完整解释语义 |
| 精确 site description、SCN 或 IP pattern | `0.90` | 从明确 metadata pattern 中解析 |
| DOCX 或 PDF table row | `0.80` | 可以直接抽取行内容，但 column 语义仍可能需要匹配 |
| PDF 图片页特征摘要 | `0.80` | 页面尺寸和嵌入图片 bbox 是直接观察结果，但还没有识别出道路语义 |
| PDF vector page 摘要 | `0.85` | vector drawing object 数量直接从 PDF 页面读取 |
| PDF vector line、curve 或 rectangle candidate | `0.70` 到 `0.75` | geometry 直接来自 PDF drawing objects，但还没有分类为道路语义 |
| PDF drawing semantic candidate | `0.40` 到 `0.45` | 从 drawing geometry 派生的低置信度 road marking、lane line、stop line、crossing、arrow 或 signal-head symbol candidate |
| PDF OCR 文本候选 | `0.55` | 文本来自渲染后的页面像素，弱于原生 PDF 文本 |
| PDF CV 线段候选 | `0.50` | 线段来自像素检测，还没有分类为 lane、marking、stop line 或图纸噪声 |
| ZIP member 或被拒绝的不安全 member | `1.00` | 直接观察 archive 内容 |
| ZIP DWG 文件名分类 | `0.80` 到 `0.85` | 根据路径层级或文件名提示推导 |
| CAD layer names 或 entity counts | `0.95` | 直接读取已解析 DXF 结构 |
| CAD geometry、label 或 block candidate | `0.70` 到 `0.80` | 直接抽取结构，但 MAPEM 语义尚未确定 |
| CAD coordinate bounds | `0.90` | 根据抽取 geometry 确定性计算 |
| GIS road name | `0.85` | 直接读取 GIS property 或 OSM tag |
| GIS geometry | `0.75` | 直接读取 geometry，但仍需执行语义匹配 |
| GIS coordinate bounds | `0.90` | 根据源 geometry 确定性计算 |
| GIS junction centre candidate | `0.60` | 使用 geometry bounds 中心点作为近似值 |
| MOVA 导出要求和文件大小 | `1.00` | 表示直接 workflow 状态和文件 metadata，不是已经解码的 MOVA 控制 facts |

从 ZIP member 递归抽取的 facts 保留内部 parser 分配的 confidence。DWG 文件通过
ODA File Converter 转换后，使用与 DXF 相同的 confidence 规则。

调度器生成文件级输出：

```json
{
  "site_id": "1062",
  "source_files": [
    {
      "source_file": "1062_UTCForm_Jan24.docx",
      "file_type": "docx",
      "parser": "docx_parser",
      "status": "parsed",
      "extracted_facts": []
    }
  ]
}
```

## 不同文件格式保留的数据

Step 2 保留抽取后的 facts 和 provenance，不会复制一份原始文件。下表说明当前
parsers 会保留的数据。候选 facts 采用保守策略；Step 3 再把它们匹配、去重并融合
为 MAPEM 字段。

| 文件格式 | 扫描的数据 | 在 `extracted_facts.partial.json` 中保留的数据 | 保留原因 |
| --- | --- | --- | --- |
| TXT、8TX | 解码后的非空文本行 | phase、stage、stream、intergreen、detector、I/O allocation、SCOOT、timing、override 和 control keyword candidates；精确匹配的 site description、SCN 和 IP | Controller 和 RAM reports 通常以文本形式提供控制信息 |
| PDF | 可抽取的页面文本、tables、页面级图片对象、vector drawing objects，以及含图片页面的渲染像素 | keyword 和 metadata candidates；完整的非空 table rows；无文本页面输出 `needs_future_recognition`；有图片对象的页面输出 `pdf_image_page_candidate`；OCR 文本候选；CV 线段候选；`pdf_vector_page_candidate`；vector line、curve 和 rectangle candidates；低置信度 drawing semantic candidates | 配置报告、时序表和图纸可能同时包含文本表格、raster images 和 vector drawing geometry |
| DOCX | Paragraph 文本和 tables | keyword 和 metadata candidates；完整的非空 table rows | UTC forms 和辅助说明包含结构化站点与控制信息 |
| DXF | Modelspace entities、layers、geometry、文本和 block inserts | layer names；entity counts；line 和 polyline geometry candidates；text labels；block references；coordinate bounds | CAD 结构为后续 lane、stop line、crossing 和 signal head 识别提供证据 |
| DWG | 使用 ODA File Converter 转换为 DXF 后，按照 DXF 扫描 | 与 DXF 相同的 facts | DWG 是二进制格式；ODA 转换后 Python parser 才能读取 CAD 结构 |
| GeoJSON、JSON | GIS features、properties 和 coordinates | road-name candidates；geometry candidates；coordinate bounds；使用 bounds 中心点近似计算的 junction candidate | GIS 数据提供道路名称和地图 geometry |
| OSM | Nodes、ways 和 way tags | road-name candidates；coordinate bounds；使用 bounds 中心点近似计算的 junction candidate | OSM 数据提供参考道路名称和 coordinates |
| Shapefile、GeoPackage | 通过 Fiona 读取 GIS features、properties 和 coordinates | road-name candidates；geometry candidates；coordinate bounds；使用 bounds 中心点近似计算的 junction candidate | 结构化 GIS 文件提供空间参考证据 |
| ZIP | Archive paths 和支持递归解析的内部 members | archive-member facts；被拒绝的不安全 paths；nested parseable-file availability；root 和 xref DWG candidates；topographic drawing availability；递归抽取的内部 facts | ZIP 是容器；保留 member chain 可以追溯原始来源 |
| MOVA | 文件路径、外部工具配置和文件大小 | `mova_tools_manual_export_required`；file-size metadata | `.mova` 是专有二进制 dataset；完整控制 facts 必须来自 MOVA Tools 导出的文件 |
| 不支持的扩展名 | 文件路径和扩展名 | 文件级 `status: "unsupported"`，不输出 extracted facts | 保留文件可见性供人工检查，不猜测文件内容 |

每条保留的 fact 都包含 `evidence_location` chain。例如从 ZIP 内 DWG 抽取的 CAD
fact 会保留 ZIP 路径、archive-member 路径和 modelspace entity 位置。

### 抽取噪声控制

在 assignment 或 MAPEM matching 之前，extraction 阶段会先执行保守过滤：

| 噪声来源 | 规则 |
| --- | --- |
| 空 CAD 文本 | `TEXT` 和 `MTEXT` 中为空或只有空白字符的内容，不输出为 `cad_text_label` |
| 非本站点 CAD 文件 | 文件名前缀带有 site id，但和 `--site-id` 不一致的 CAD 文件，输出 `status: "skipped"` 和 `skip_reason: "non_site_cad_source"` |
| Topographic CAD | 类似 `OS-TOPO.dwg` 的文件只保留 CAD metadata 和 bounds；不会从 standalone topo 文件输出密集 drawing geometry 和 labels |
| ZIP / standalone CAD 重复 | 如果同名 CAD 文件既存在于 site 文件夹中，又存在于 ZIP 内部，优先使用 standalone 文件；ZIP member 输出 `duplicate_archive_member_skipped`，不再递归抽取重复 CAD facts |
| PDF semantic drawing candidates | PDF vector/CV semantic facts 保持低置信度 candidates；Step 2 不把它们提升为最终 road semantics |

这样可以避免 topographic 背景图、其他站点图纸和重复压缩包成员污染后续 lane-level
evidence，同时保留必要 provenance 供人工检查。

### 结构化 movement mapping facts

部分 controller config 和 UTC 文档会显式描述 phase letters、SCOOT links、stages
和交通流 movement 的关系。Step 2 现在会把这些关系抽成结构化 facts，让 adapter
可以先通过 `movement_ref` 路由 `signalGroup`，再把 movement 解析到具体 lane。

| Fact name | 来源模式 | 含义 |
| --- | --- | --- |
| `phase_movement_mapping_from_controller_config` | Controller config 的 `Phase Type and Conditions`，例如 `A LONDON ROAD INBOUND AHEAD` | 把 controller phase 映射到 movement description、road name、direction、maneuver 和 `movement_ref` |
| `scoot_link_movement_from_utc_form` | UTC form 的 `Link SCN | Link Description` table | 把 SCOOT link letter/SCN 映射到 movement description 和 `movement_ref` |
| `phase_scoot_link_mapping_from_utc_form` | UTC form 的 `Controller Phase Letter | SCOOT Link Letter` table | 把 controller phase letter 映射到 SCOOT link ref；如果可用，也带上对应 `movement_ref` |
| `scoot_link_stage_mapping_from_utc_form` | UTC form 的 `Link Letter | ... | UTC Green Stage No's` table | 把 SCOOT link ref 映射到 UTC green stage numbers |

这些 facts 故意输出 `movement_ref`、`phase_ref`、`scoot_link_ref` 和 `stage_refs`，
不直接输出 `lane_ref`。`lane_ref` 是 geometry assignment 之后生成的内部 ID，所以
后续 adapter/matching 应使用 road name、direction、maneuver、CAD labels 和 geometry
context，把 movement semantics 再连接到已分配的 lanes。

### 为后续 MAPEM 匹配准备的 Fact Names

`extracted_facts.partial.json` 中最终输出的 `fact_type` 应尽量使用
`configs/MAPEM Dictionary.xlsx` 的 `Fact` sheet 中 `Fact Name` 列。这样可以为
Step 3 做准备，但当前还没有实现 MAPEM field matching。

Parser 应该直接输出字典中的 fact name。例如：

```json
{
  "fact_type": "phase_label_from_ram_8tx"
}
```

暂时无法安全对应到字典的 facts 会继续保留当前 parser-level 名称，等 matcher
rules 明确后再改。抽取输出不额外增加旧名称映射层。

## 组件

### 抽取调度器

新增 `src/mapemgen/ingestion/facts.py`。

职责：

- 校验 site 文件夹路径
- 递归扫描所有嵌套源文件
- 根据文件类型分发 parser
- 保留完整源文件路径和内部位置 provenance，并保证输出顺序稳定
- 单个文件损坏或格式异常时记录 `parser_error`
- 缺少必要依赖时抛出包含安装提示的错误

新增 CLI 命令：

```powershell
python -m mapemgen.cli extract `
  --site-folder <site-folder> `
  --site-id <site-id> `
  --out-dir <output-folder>
```

固定输出文件名为 `extracted_facts.partial.json`。

### TXT 和 8TX Parser

新增 `src/mapemgen/ingestion/ram_text.py`。

使用少量编码回退选项读取文本，保留非空源文本行，并抽取以下候选 facts：

- RAM override 行
- phase labels
- stages
- streams
- intergreens
- detectors
- I/O allocation

parser 使用行号记录证据位置。它不会声称已经完整解释每一种厂商报告。

### ZIP Parser

新增 `src/mapemgen/ingestion/zip_packages.py`。

读取压缩包成员列表，并递归解析支持的内部成员。输出：

- archive member facts
- root DWG candidates
- xref DWG candidates
- OS 或 topographic drawing availability
- 压缩包内可解析文件的 availability facts

支持的内部成员会逐个复制到临时文件，通过相同的格式 dispatcher 解析，并在解析后
逐个删除临时文件。嵌套 ZIP 会递归解析。`evidence_location` 会保留压缩包成员路径。

出于安全考虑，parser 会拒绝绝对路径、包含 `..` 的 path traversal、超过 100 MB
的成员，以及超过五层的 ZIP 嵌套。

### DOCX Parser

新增 `src/mapemgen/ingestion/docx_tables.py`。

使用 `python-docx` 读取段落和表格。输出以下候选 facts：

- site description 和 metadata
- SCN
- IP address
- phase labels
- stages
- streams
- SCOOT links
- timing 和 intergreen values

证据位置使用段落编号或 table row 和 cell 坐标。

### PDF Parser

实现 `src/mapemgen/ingestion/pdf_tables.py`。

使用 `pdfplumber` 读取可抽取的页面文本和表格。输出：

- 与控制信息有关的页面文本候选
- phase、stage、stream、detector 和 timing candidates
- 包含页码和 table 位置的 table row facts
- 页面没有可用文本时，输出 `needs_future_recognition`
- 只要页面包含嵌入图片对象，就输出 `pdf_image_page_candidate`，包含页面尺寸、
  嵌入图片数量和图片 bbox
- 对含图片页面输出 `pdf_ocr_text_candidate` 和 OCR keyword candidates
- 对含图片页面输出 `pdf_cv_line_candidate`，表示从渲染图片中检测到的线段
- 对 vector PDF drawing objects 输出 `pdf_vector_page_candidate`、
  `pdf_vector_line_candidate`、`pdf_vector_curve_candidate` 和
  `pdf_vector_rect_candidate`
- 输出低置信度 drawing semantic candidates，例如
  `road_marking_candidate_from_pdf_vector`、`lane_line_candidate_from_pdf_vector`、
  `stop_line_candidate_from_pdf_vector`、`crossing_candidate_from_pdf_vector`、
  `arrow_candidate_from_pdf_vector`、`signal_head_symbol_candidate_from_pdf_vector`、
  `road_marking_candidate_from_pdf_cv` 和 `lane_line_candidate_from_pdf_cv`

Step 2 对任何包含图片对象的 PDF 页面执行 OCR/CV，即使同一页也有可抽取文本或
表格。如果含图片页面需要识别但缺少 OCR/CV packages，程序会直接报错。
Vector PDF drawing objects 直接从 PDF 页面结构读取，不需要 OCR/CV packages。

### PDF OCR 和 Computer Vision 实施方案

很多 local authority 可能只提供 PDF 作为最后 fallback。对于这类站点，扫描图纸
不可能一次性稳定抽取成最终 MAPEM 字段，应该采用 feature extraction 加空间过滤：

1. 如果有 CAD，优先使用 CAD。DWG/DXF geometry 是 lane、stop line、road marking
   和 signal head 位置的优先来源。
2. 使用 GIS/OSM/Ordnance Survey geometry 作为粗过滤。road name、junction bounds
   和近似 centre point 可以缩小候选区域，剔除 unrelated clusters 或 secondary
   drawing information。
3. 把包含嵌入图片对象的 PDF 页面转换成图片。`needs_future_recognition` 表示该页
   缺少可抽取文本；`pdf_image_page_candidate` 表示该页包含图片对象，需要进入 OCR/CV。
4. 对 title block、notes、labels、phase/stage tables 和 road labels 的裁剪区域执行
   OCR。OCR 结果先作为文本候选，置信度低于原生 PDF 文本，除非被 CAD/GIS 佐证。
5. 对 drawing regions 执行 computer vision 和 vector-geometry heuristics，生成
   road markings、lane lines、arrows、stop lines、crossings 和 signal-head symbols
   的低置信度 candidates。识别结果先保留为 candidate facts，等待后续和 CAD/GIS
   context 匹配。
6. Step 2 只给初始保守置信度。CAD-confirmed geometry、OCR corroboration 和 GIS
   spatial filtering 不在 Step 2 完成，而是 Step 3 / evidence-fusion 的职责。
7. 对 vector PDF，直接读取 `pdfplumber` page 结构里的 drawing objects。lines、
   curves 和 rects 会先作为 vector candidates 保存，后续再和 CAD/GIS context 匹配。

这个方案让 PDF fallback 可用，但不会假设扫描图纸可以直接生成最终 MAPEM 字段。
当前 Step 2 会记录图片页、OCR 文本候选和原始 CV 线段候选；后续 matching/fusion
再判断它们是否能支持 MAPEM 字段。

#### 当前图像识别过程

当前实现位于 `src/mapemgen/ingestion/pdf_cv.py`。它是 PDF 图纸 fallback 的
规则型识别流程，不是训练好的 object-detection 模型。

目标：

- CAD 不存在时，尽量保留 PDF 图纸里的可用 evidence
- 区分“直接观察到的 geometry”和“推断出来的 road semantics”
- 所有推断出的 semantic features 都标记为需要后续 CAD/GIS context match

路径 A：vector PDF objects

1. 从 `pdfplumber` 读取 `page.lines`、`page.curves` 和 `page.rects`。
2. 输出原始 vector facts：`pdf_vector_page_candidate`、
   `pdf_vector_line_candidate`、`pdf_vector_curve_candidate` 和
   `pdf_vector_rect_candidate`。
3. 保留 PDF 坐标，例如 `x0`、`top`、`x1`、`bottom`、`width`、`height`
   和 `linewidth`。
4. 使用简单 geometry 规则生成低置信度 semantic candidates：lane line、stop line、
   crossing、arrow、road marking 和 signal-head symbol。
5. 不把明显的页面边框、整页线段、整页矩形或普通装饰曲线提升为道路语义候选。
   这些对象只保留为 raw vector facts。

路径 B：raster image pages

1. 使用 `pymupdf` / `fitz` 把 PDF page 渲染成像素图片。
2. 使用 `pytesseract` 执行 OCR，并把非空文本输出为 `pdf_ocr_text_candidate`。
3. 扫描 OCR 文本中的控制相关 keywords，例如 `phase`、`stage`、`detector`、
   `timing` 和 `control`。
4. 使用 OpenCV 对渲染后的像素做线段检测：
   grayscale -> Otsu threshold -> morphology close -> Canny edges ->
   probabilistic Hough lines。
5. 把检测到的原始像素线段输出为 `pdf_cv_line_candidate`。
6. 从这些线段派生低置信度 semantic candidates，例如
   `road_marking_candidate_from_pdf_cv`、`lane_line_candidate_from_pdf_cv` 和
   `stop_line_candidate_from_pdf_cv`。

输出规则：

- vector geometry 比 pixel CV 更强，因为它来自 PDF drawing structure
- OCR text 比原生 PDF text 弱，因为它来自渲染后的 pixels
- CV line detection 只能说明“发现了类似线段的形状”，不能证明它就是 road marking
- semantic drawing candidates 都包含 `requires_context_match: true`
- 不确定时，保留 raw geometry，但不输出推断出来的 semantic candidate

### DXF 和 DWG Parser

实现 `src/mapemgen/ingestion/cad.py`。

使用 `ezdxf` 解析 DXF。输出：

- layer names
- entity counts
- coordinate bounds
- line 和 polyline geometry candidates
- 带 insertion-point 坐标的 text labels；如果 CAD entity 暴露了坐标，就保留在
  payload 里
- 带 insertion-point 坐标的 block references；如果 CAD entity 暴露了坐标，就保留在
  payload 里
- CAD movement-label candidates；当文本包含 `inbound ahead`、`WB left`、
  `right turn` 这类 movement / maneuver 信息时，输出结构化 `movement_ref`
- CAD arrow-block candidates；当 block name 暗示 arrow、turn 或 lane direction
  时，作为空间候选保留
- 根据可配置 layer-name 和 text-label 规则生成 lane、stop line、crossing 和
  signal-head candidates

对于 DWG 输入，通过 `ezdxf.addons.odafc` 调用 ODA File Converter，创建临时
DXF，再执行相同的 DXF parser。站点 inventory 中存在 `.dwg` 时，ODA File
Converter 是必须安装的运行时依赖。未安装时，抽取任务直接停止并输出清晰错误。

CAD text 和 block 坐标是上游关键数据。assignment 不能只靠 phase table 推断
`movement_ref -> lane_ref`；它需要靠近 lane geometry 的 spatial movement label、
arrow block 或 lane label。 因此 `cad_text_label`、`cad_block_reference`、
`cad_movement_label_candidate` 和 `cad_arrow_block_candidate` 会在 CAD entity 提供
insertion point 时保留 modelspace 坐标。

CAD block/text 语义规则配置在 `configs/cad_symbol_semantics.json`。parser 扫描 CAD
entities 前会读取这个表。也可以用 `CAD_SYMBOL_RULES_PATH` 指向另一份本地 JSON 规则表。

当前 starter rules：

| CAD symbol/text 规则 | 输出 fact | 含义 |
| --- | --- | --- |
| Block name `HD*`，例如 `HD084` 或 `HD001S` | `cad_signal_head_candidate` | 带 modelspace 坐标的 signal-head candidate |
| Block name `HD003P` 或 `HD004P` | `cad_arrow_block_candidate` | 根据 block definition 几何识别的 directional signal-arrow candidate；保留为 `requires_context_match` |
| Block name `pole` | `cad_pole_candidate` | 带 modelspace 坐标的 pole/post candidate |
| Block name `tactpblk` | `cad_pedestrian_facility_candidate` | tactile paving 或 pedestrian crossing facility candidate |
| Block name 包含 `arrow`、`left` 或 `right` | `cad_arrow_block_candidate` | directional arrow candidate |
| Text 包含 `LEFT`、`RIGHT`、`AHEAD`、`WB`、`EB`、`NB`、`SB`、`INBOUND` 或 `OUTBOUND` | `cad_movement_label_candidate` | 带派生 `movement_ref` 的 movement label |
| Text `KEEP CLEAR` | `cad_lane_use_label_candidate` | lane-use 或 road-marking label |

### GIS Parser

实现 `src/mapemgen/ingestion/gis.py`。

支持：

- GeoJSON 和 `.json`
- OSM XML
- Shapefile `.shp`
- GeoPackage `.gpkg`

GeoJSON 和 OSM 使用 Python 标准库读取。Shapefile 和 GeoPackage 使用
`fiona`。输出：

- road-name candidates
- geometry candidates
- coordinate bounds
- intersection reference-point candidates

必须安装所需 GIS 库。缺少依赖时直接报错，不输出 warning，也不静默降级。

### MOVA Parser

新增 `src/mapemgen/ingestion/mova.py`。

`.mova` 是官方 MOVA Tools 使用的专有二进制 dataset 格式。完整抽取必须把 MOVA
Tools 作为外部转换边界，类似 DWG 抽取使用 ODA File Converter：

```text
.mova 二进制 dataset
        |
        v
官方 MOVA Tools 导出
        |
        v
导出的文本 / report 文件
        |
        v
Python parser
        |
        v
detector、control、phase、stage、stream、timing 和 plan facts
```

必须使用外部工具，原因是仓库内样本属于不透明二进制文件，二进制 schema 没有公开，
自行猜测 byte offset 会产生不可靠的 MAPEM evidence。TRL 将 MOVA Tools 描述为
创建、编辑和转换 MOVA dataset 文件的官方程序。

Python 集成需要读取 `MOVA_TOOLS_PATH` 环境变量，该变量指向已安装的 MOVA Tools
可执行文件。启用自动导出前，必须根据实际安装版本确认导出命令。如果该版本只提供
GUI 导出，则需要先手动导出文件，再把导出文件放入 site 文件夹供 Python parser
处理。

## 依赖策略

把 Python parser 所需依赖加入 `pyproject.toml`。

Python packages 是普通项目依赖。ODA File Converter 和 MOVA Tools 是外部程序，
需要在 README 中说明安装要求。

错误处理规则：

| 情况 | 行为 |
| --- | --- |
| 缺少必要 Python package | 停止任务，并输出可操作的安装提示 |
| 遇到 `.dwg`，但没有安装 ODA File Converter | 停止任务，并输出可操作的安装提示 |
| 遇到 `.mova`，但没有安装 MOVA Tools | 停止完整 MOVA 抽取，并输出可操作的安装提示 |
| 单个源文件损坏或格式异常 | 记录文件级 `parser_error`，继续处理其他文件 |
| PDF 页面没有可抽取文本 | 输出 `needs_future_recognition` |
| PDF 页面包含图片对象 | 输出 `pdf_image_page_candidate`，执行 OCR/CV，并要求安装可选 `cv` packages |
| PDF 页面包含 vector drawing objects | 输出 `pdf_vector_page_candidate` 和 vector drawing candidates，不需要 OCR/CV packages |
| MOVA Tools 版本没有已确认的 CLI 导出命令 | 使用 MOVA Tools 手动导出，再解析导出文件 |

## 安装方法

### Python 环境

打开 PowerShell，把 `<project-root>` 替换为本机项目根目录的绝对路径。项目根目录
是包含 `pyproject.toml`、`README.md`、`src/` 和 `tests/` 的文件夹。

Windows 环境建议使用 Python 3.13。Fiona 当前提供 CPython 3.13 的 Windows wheel，
但没有 CPython 3.14 的 Windows wheel。使用 Python 3.14 时，pip 会尝试在本机编译
Fiona，并额外要求安装 GDAL 开发环境。

通用模板：

```powershell
cd "<project-root>"
py -3.13 -m venv mapem313
.\mapem313\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

当前电脑上的示例：

```powershell
cd C:\Users\leovo\Desktop\GDP
py -3.13 -m venv mapem313
.\mapem313\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

`mapem313` 是这个项目专属的 Python 虚拟环境。以后这个仓库需要新增 Python package
时，都应该先激活该环境，再执行安装命令。每次重新打开 PowerShell 后，需要再次
激活：

```powershell
cd "<project-root>"
.\mapem313\Scripts\Activate.ps1
```

当前电脑上的示例：

```powershell
cd C:\Users\leovo\Desktop\GDP
.\mapem313\Scripts\Activate.ps1
```

`python -m pip install -e .` 会安装 `pyproject.toml` 中声明的依赖：

| Package | 用途 |
| --- | --- |
| `python-docx` | 读取 DOCX 段落和表格 |
| `pdfplumber` | 读取 PDF 文本和表格 |
| `ezdxf` | 解析 DXF，并提供 DWG 转换调用边界 |
| `fiona` | 解析 Shapefile 和 GeoPackage |
| `pyproj` | 把 British National Grid 坐标转换为 WGS84 |

TXT、8TX、ZIP、GeoJSON、JSON 和 OSM 抽取使用 Python 标准库，不需要额外安装
parser package。完整 MOVA 抽取还需要下文说明的外部 MOVA Tools 应用程序。

如果不安装整个项目，也可以显式安装 parser packages：

```powershell
python -m pip install "python-docx>=1.1" "pdfplumber>=0.11" "ezdxf>=1.3" "fiona>=1.10" "pyproj>=3.7"
```

扫描版 PDF 图纸 OCR/CV 使用可选依赖：

```powershell
python -m pip install -e ".[cv]"
```

这会安装 `opencv-python`、`pytesseract` 和 `pymupdf`。其中 `pytesseract`
还需要本机额外安装 Tesseract OCR 可执行程序后才能真正运行 OCR。当 Step 2 遇到
包含图片对象、必须从像素识别的 PDF 页面时，这些 packages 是必需的。

### 安装用于 DWG 的 ODA File Converter

DWG 不能只依赖纯 Python package 完成解码。需要在本机安装
[ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)。
代码通过 `ezdxf.addons.odafc` 调用该工具。

激活虚拟环境后，先检查 `ezdxf` 使用的默认安装路径：

```powershell
python -c "from ezdxf.addons import odafc; print(odafc.is_installed())"
```

如果 ODA File Converter 安装在其他文件夹，需要显式设置 `ezdxf` 配置项
`odafc-addon.win_exec_path`。把 `<path-to-ODAFileConverter.exe>` 替换为实际的
可执行文件路径：

```powershell
python -c "import ezdxf; from ezdxf.addons import odafc; ezdxf.options.set('odafc-addon', 'win_exec_path', r'<path-to-ODAFileConverter.exe>'); print(odafc.is_installed())"
```

例如，可执行文件保存在 `E:\ODA` 时：

```powershell
python -c "import ezdxf; from ezdxf.addons import odafc; ezdxf.options.set('odafc-addon', 'win_exec_path', r'E:\ODA\ODAFileConverter.exe'); print(odafc.is_installed())"
```

上面的 Python 赋值只对该条检查命令有效。运行 `mapemgen extract` 前，需要在同一个
PowerShell 会话中设置 `ODAFC_PATH`：

```powershell
$env:ODAFC_PATH="E:\ODA\ODAFileConverter.exe"
python -m mapemgen.cli extract `
  --site-folder "<site-folder>" `
  --site-id "<site-id>" `
  --out-dir "<output-folder>"
```

成功时，命令必须输出：

```text
True
```

如果 site 文件夹包含 `.dwg`，但是本机没有安装 ODA File Converter，抽取任务
会直接停止，并输出可操作的错误信息。

### 用于 MOVA datasets 的 MOVA Tools

从 TRL Software 安装官方
[MOVA Tools](https://trlsoftware.com/products/traffic-control/mova/mova-downloads/)。
Python 不能可靠地直接解码 `.mova` 二进制 dataset，因为其二进制 schema 属于专有
格式，并未公开。MOVA Tools 是创建、编辑和转换这些 datasets 的官方程序。

安装后，把 `<path-to-MOVATools.exe>` 替换为实际可执行文件路径：

```powershell
Test-Path "<path-to-MOVATools.exe>"
$env:MOVA_TOOLS_PATH="<path-to-MOVATools.exe>"
```

示例路径：

```powershell
Test-Path "E:\MOVA Tools\MOVATools.exe"
$env:MOVA_TOOLS_PATH="E:\MOVA Tools\MOVATools.exe"
```

`Test-Path` 必须输出：

```text
True
```

注意：MOVA Tools 官方下载页面没有公开说明命令行导出参数。需要根据实际安装版本
确认它提供的导出选项。如果该版本只支持 GUI 导出，则先在 MOVA Tools 中打开
`.mova` 文件，导出可用的文本或 report 文件，再把导出文件放入同一个 site 文件夹，
最后运行 `mapemgen extract`。

## 数据流

```text
site folder
        |
        v
facts extraction coordinator
        |
        +-- TXT / 8TX parser
        +-- ZIP parser
        +-- DOCX parser
        +-- PDF parser
        +-- DXF parser
        +-- DWG -> ODA File Converter -> DXF parser
        +-- GIS parser
        +-- MOVA -> 官方 MOVA Tools 导出 -> exported-file parser
        |
        v
extracted_facts.partial.json
        |
        v
geometry and semantic scope assignment
        |
        v
geometry_assignments.partial.json
```

## 几何和语义关系分配

Scope assignment 是 parser 之后、MAPEM field matching 之前的一步。它不选择
MAPEM field，不生成 `SiteModel`，也不决定最终 lane connectivity。它只负责给
抽取出来的 facts 增加归属关系，避免多车道站点里所有证据混成一个扁平 fact 池。

这一阶段处理两类关系：

| 关系 | 适用 facts | 输出 |
| --- | --- | --- |
| 几何关系 | lane lines、stop lines、crossings、road markings、signal-head symbols、CAD/GIS/PDF drawing geometry | `target_scope.intersection_ref`；如果同一坐标空间内能找到最近 lane，则增加 `target_scope.lane_ref` |
| 语义关系 | phase labels、stage relationships、detector labels、signal-group labels、road names、control/timing labels | `target_scope.intersection_ref`，以及直接可见的 `phase_ref`、`stage_ref`、`detector_ref`、`signal_group_ref`、`approach_ref` 或 `label_ref` |

重要：非几何 facts 不会被强行分配到某条 lane。例如 `Phase A` 会被分配到
site intersection 和 `phase_A`；只有后续 matching/fusion 找到可靠 movement 或
geometry context，把这个 phase 和某条 lane 连接起来时，才会产生 lane-level 关系。

输入：

```text
extracted_facts.partial.json
```

输出：

```text
geometry_assignments.partial.json
```

运行命令：

```powershell
python -m mapemgen.cli assign-geometry `
  --input "outputs/1003_LondonRdClevelandBridge/extracted_facts.partial.json" `
  --out-dir "outputs/1003_LondonRdClevelandBridge"
```

输出内容：

| 字段 | 含义 |
| --- | --- |
| `intersections[]` | 从 junction-centre facts 推断出的 intersection refs；如果没有 centre，就创建默认 site intersection |
| `lanes[]` | 从 lane-like geometry facts 创建的稳定 `lane_ref` |
| `assigned_facts[]` | 带 `target_scope.intersection_ref` 和可能的 `target_scope.lane_ref` 的 geometry facts |
| `semantic_assignments[]` | 带 intersection-level scope 和直接 semantic refs 的非几何 facts，例如 `phase_ref`、`stage_ref`、`detector_ref` 或 `approach_ref` |
| `movement_lane_mappings[]` | 保守的 `movement_ref -> lane_ref` 映射；只有 lane source label 明确暴露 movement 时才自动连接，未匹配的 movement 会保留 `requires_context_match: true` |
| `geometry_summary` | centroid、bounds、coordinate space，以及 PDF page reference |

几何分配示例：

```json
{
  "fact_id": "fact_00123",
  "fact_name": "stop_line_from_cad",
  "target_scope": {
    "intersection_ref": "intersection_1",
    "lane_ref": "lane_3"
  },
  "assignment_method": "nearest_lane_centroid",
  "distance_to_lane": 1.7
}
```

语义分配示例：

```json
{
  "fact_id": "fact_00456",
  "fact_name": "phase_label_from_controller_config",
  "target_scope": {
    "intersection_ref": "intersection_1",
    "lane_ref": null,
    "phase_ref": "phase_A"
  },
  "assignment_method": "semantic_reference_extraction",
  "assignment_basis": "direct_text_reference"
}
```

movement 到 lane 的映射示例：

```json
{
  "movement_ref": "movement_london_road_inbound_ahead",
  "movement_text": "London Road inbound ahead",
  "phase_refs": ["phase_A"],
  "lane_ref": "lane_3",
  "intersection_ref": "intersection_1",
  "assignment_method": "lane_label_movement_match",
  "requires_context_match": false
}
```

未匹配的 movement 示例：

```json
{
  "movement_ref": "movement_cleveland_bridge_right",
  "movement_text": "Cleveland Bridge right",
  "phase_refs": ["phase_B"],
  "lane_ref": null,
  "intersection_ref": null,
  "assignment_method": "needs_context_match",
  "requires_context_match": true,
  "unmatched_reason": "no_lane_movement_label"
}
```

规则：

- CAD 和 GIS geometry 可以按最近 geometry centroid 分配。
- Lane 定义使用最高优先级的可用来源：先用 CAD，其次 Ordnance Survey，最后才是
  PDF fallback。如果 PDF fallback 因为产生过多泛化 clusters 被抑制，directional CAD
  signal-arrow blocks 可以作为最后 fallback 创建低置信度 lane proxies。低优先级的
  lane-like facts 仍然作为 evidence 保留，但当更强来源已存在时，不再额外创建 lanes。
- 如果 PDF 是唯一 lane 来源，相似的 PDF lane-line segments 会先聚类为 lane
  corridors，避免一个 vector segment 生成一条 lane。
- PDF 页面坐标只会分配给同一个 PDF 文件、同一页里的 lane，不会和 CAD modelspace
  或 GIS coordinates 混合。
- phase、stage、detector、signal-group、road-name 和 label facts 只有在文本中直接
  出现具体编号或名称时，才会产生对应 semantic ref。
- `Phases, Stages and Streams` 这类泛化标题只保留 intersection scope，不会被提升成
  某一个具体 `phase_ref` 或 `stage_ref`。
- 非几何 facts 保持 `lane_ref: null`，除非存在可靠 geometry anchor。这样避免把一个
  phase 或 label 错误分配给最近的一条 lane。
- phase 到 movement 的 facts 可以通过 `movement_lane_mappings[]` 连接到 lane；
  前提是 assignment 能从 lane source facts 里读到匹配的 `movement_ref`、
  `movement_text`、lane label 或 road-name label。
- 带坐标的 CAD movement label 也可以在被 assignment 分配到最近 lane 后生成
  `movement_lane_mappings[]`；这类映射使用
  `assignment_method: "cad_movement_label_nearest_lane"`。
- Directional CAD signal-arrow lane proxies 只会匹配方向一致的 turn movement，例如
  `right_turn` 或 `left_turn`；这类映射使用
  `assignment_method: "cad_signal_arrow_direction_match"`，并且仍然保留
  `requires_context_match: true`，因为 proxy 不是完整 lane geometry。
- 如果 assignment 仍然看不到 structured movement 属于哪条真实 lane，它会创建
  `semantic_movement_lane_proxy`，让该 movement 仍然拥有稳定 `lane_ref`。这类映射使用
  `assignment_method: "semantic_movement_lane_proxy"`，并且始终保留
  `requires_context_match: true`，因为 proxy 来自 movement 语义，不是直接观测到的
  lane geometry。
- 无法转换成 point、bounds 或 centroid 的 facts 保持 unassigned。
- Raw geometry 仍然保留；assignment 只增加 scope，不删除或改写 parser facts。
- 后续 matching/fusion 仍然需要决定哪些 assigned facts 填入 `laneSet[].nodeList`、
  `connectsTo` 或 `signalGroup` 等 MAPEM fields。

## 测试

使用 synthetic、非机密 fixtures 添加以下测试：

- coordinator dispatch 和稳定输出顺序
- CLI 输出路径
- TXT 和 8TX keyword candidates
- ZIP 成员分类，并确认不会解压
- DOCX 段落和表格
- PDF 文本页、表格和图片页待后续识别记录
- DXF layers、entities、labels、coordinate bounds 和 geometry candidates
- 使用 mock 验证 DWG ODA 调用边界
- GeoJSON、JSON、OSM、Shapefile 和 GeoPackage 解析
- 必要依赖缺失错误
- MOVA Tools 配置和 exported-file parsing
- 单个损坏文件输出 `parser_error`，同时继续处理其他文件

测试只能使用 `outputs/` 或临时测试目录下生成的 synthetic fixtures。禁止提交机密
原始数据。

## 不在 Step 2 范围内

Step 2 不负责：

- 把 OCR/CV 输出直接当作最终 MAPEM geometry 或 signal semantics
- 不通过 MOVA Tools，直接解码或 reverse-engineer MOVA 专有二进制格式
- 将 facts 匹配到 MAPEM 字段
- evidence fusion 和 `SiteModel` 生成
- MAPEM JSON 或 ASN.1 输出生成

## 使用方法

这是 Step 2 的直接操作流程：先做 EDA/source-data inspection，再从完整 site 文件夹
抽取 facts，最后执行几何关系和语义关系分配。

### 模板：EDA、抽取、关系分配

尖括号中的内容需要替换：

| 占位符 | 应该填写什么 |
| --- | --- |
| `<project-root>` | 本机项目根目录的绝对路径 |
| `<venv-path>` | 虚拟环境激活脚本路径，例如 `.\mapem313\Scripts\Activate.ps1` |
| `<site-folder>` | 某一个交通信号站点全部文件所在的文件夹路径；程序会递归扫描嵌套文件夹 |
| `<site-id>` | 写入输出文件的站点编号 |
| `<site-name>` | EDA inventory 中使用的可读站点名称 |
| `<dataset>` | EDA inventory 中使用的数据来源或 local authority |
| `<output-folder>` | 写入 JSON 输出的目标文件夹 |
| `<path-to-ODAFileConverter.exe>` | 只有 site 文件夹包含 `.dwg` 时才需要；填写真实 ODA 可执行文件路径 |

```powershell
cd "<project-root>"
<venv-path>
$env:PYTHONPATH='src'

# 只有存在 DWG 文件时才需要。
$env:ODAFC_PATH="<path-to-ODAFileConverter.exe>"

# EDA / source-data inspection。它是可选检查，不作为 Step 2 的输入。
python -m mapemgen.cli inventory `
  --site-folder "<site-folder>" `
  --site-id "<site-id>" `
  --site-name "<site-name>" `
  --dataset "<dataset>" `
  --out-dir "<output-folder>"

# 从完整 site 文件夹抽取 facts。
python -m mapemgen.cli extract `
  --site-folder "<site-folder>" `
  --site-id "<site-id>" `
  --out-dir "<output-folder>"

# 为后续 MAPEM matching 分配几何关系和语义关系。
python -m mapemgen.cli assign-geometry `
  --input "<output-folder>\extracted_facts.partial.json" `
  --out-dir "<output-folder>"
```

预期输出：

| 输出文件 | 用途 |
| --- | --- |
| `site_inventory.partial.json` | 可选 EDA 输出，用于查看 site 文件夹里有哪些文件 |
| `extracted_facts.partial.json` | 所有 parser 从源文件抽取出的 facts |
| `geometry_assignments.partial.json` | 几何分配和语义分配结果，供后续 matching 使用 |

### 示例：1003 London Road Cleveland Bridge

```powershell
cd C:\Users\leovo\Desktop\GDP
.\mapem313\Scripts\Activate.ps1
$env:PYTHONPATH='src'
$env:ODAFC_PATH="E:\ODA\ODAFileConverter.exe"

python -m mapemgen.cli inventory `
  --site-folder "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge" `
  --site-id "1003" `
  --site-name "London Rd Cleveland Bridge" `
  --dataset "DCIS/Bathnes" `
  --out-dir "outputs/1003_LondonRdClevelandBridge"

python -m mapemgen.cli extract `
  --site-folder "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge" `
  --site-id "1003" `
  --out-dir "outputs/1003_LondonRdClevelandBridge"

python -m mapemgen.cli assign-geometry `
  --input "outputs/1003_LondonRdClevelandBridge/extracted_facts.partial.json" `
  --out-dir "outputs/1003_LondonRdClevelandBridge"
```

缩略 `extracted_facts.partial.json` 示例：

```json
{
  "site_id": "1003",
  "source_files": [
    {
      "source_file": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/1003_2500Config_Mar24.pdf",
      "file_type": "pdf",
      "parser": "pdf_parser",
      "status": "parsed",
      "extracted_facts": [
        {
          "fact_name": "phase_label_from_controller_config",
          "payload": {
            "value": "Phase A"
          },
          "evidence_location": "local_data/other_site_data/DCIS/1003_LondonRdClevelandBridge/1003_2500Config_Mar24.pdf -> page 1 line 16",
          "confidence": 0.65
        }
      ]
    }
  ]
}
```

缩略 `geometry_assignments.partial.json` 示例：

```json
{
  "site_id": "1003",
  "lanes": [
    {
      "lane_ref": "lane_1",
      "intersection_ref": "intersection_1",
      "source_fact_name": "lane_geometry_candidate_from_cad"
    }
  ],
  "assigned_facts": [
    {
      "fact_name": "stop_line_from_cad",
      "target_scope": {
        "intersection_ref": "intersection_1",
        "lane_ref": "lane_1"
      },
      "assignment_method": "nearest_lane_centroid"
    }
  ],
  "semantic_assignments": [
    {
      "fact_name": "phase_label_from_controller_config",
      "target_scope": {
        "intersection_ref": "intersection_1",
        "lane_ref": null,
        "phase_ref": "phase_A"
      },
      "assignment_method": "semantic_reference_extraction"
    }
  ],
  "movement_lane_mappings": [
    {
      "movement_ref": "movement_london_road_inbound_ahead",
      "phase_refs": ["phase_A"],
      "lane_ref": "lane_1",
      "intersection_ref": "intersection_1",
      "assignment_method": "lane_label_movement_match",
      "requires_context_match": false
    }
  ]
}
```

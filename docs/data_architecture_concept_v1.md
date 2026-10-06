# Droplet Vision 数据架构构想 v1.0

Droplet Vision Data Architecture Concept v1.0

- Version: 1.0
- Status: Architecture baseline / concept
- Source: External project design note
- Scope: Human Ground Truth, AI Prediction, Scientific Measurement and provenance
- Implementation status: Mixed — some components already implemented, others are future architecture

本文整理自外部设计笔记《Droplet Vision 数据架构构想 v1.0》（原文日期：2026-10-05），保留其数据边界、存储建议和演进方向。下文的目标架构及 JSON 结构示例不等于当前软件已经实现的接口；已实现组件与未来工作见末尾实施状态表。

[标注内容方案 v1.0](annotation_labeling_scheme_v1.md) 是类别及操作性定义的 single source of truth，回答“标什么？”。本文件回答“这些数据如何组织、存储、流转以及与 AI 共存？”，不重新定义标签语义。

## 核心边界与总体结构

**Ground Truth ≠ Prediction ≠ Measurement。** 三类数据必须分开存储，不能全部塞进一个巨大 JSON。

| 数据层 | 职责 | 架构建议 |
| --- | --- | --- |
| Raw Cine | 不可变的原始影像来源 | 只读引用，不重编码，不写入标注、预测或测量 |
| Human AnnotationDocument | 稀疏、可审核、可追溯的人工标注主数据 | 一个 Cine 一个 JSON，保存历史及当前有效记录 |
| AI Prediction Store | 模型自动输出及置信度 | 按模型、推理运行、Cine 分开，使用分块 JSONL |
| Measurement Store | 从几何、状态等计算的派生科学量 | 按分析运行保存表格，推荐 Parquet，可用 CSV |
| Annotation Queue | 人工工作的任务与进度管理 | 引用 Cine/frame 和标注文档，不代替 Ground Truth |

Human AnnotationDocument 是人工标注的主文档，也保存未审核记录和历史；并非其中每条记录都已经通过 Ground Truth 确认。审核状态与 active view 仍须明确区分。

[Portable Review Package](portable_review_package.md) 是 raw frame 子集与人工标注快照的运输/协作格式，不是第四个 canonical 科研数据层。返回结果合并为 Reviewed 候选；原 Manual 历史、Prediction 与 Measurement 边界保持不变。

```text
Raw Cine
|
+-- Annotation Queue
|
+-- Human AnnotationDocument
|   +-- Object annotations
|   +-- Frame states
|   +-- Quality flags
|   +-- History / provenance
|
+-- AI Prediction Store
|   +-- Object predictions / confidence
|   +-- Frame-state probabilities
|   +-- Model provenance
|
+-- Measurement Store
    +-- Parent geometry / cavity metrics
    +-- Daughter-droplet metrics
    +-- State time series / derived quantities
```

这些层通过 `cine_id`、`frame_index`、`raw_time64` 关联。`relative_cine_path` 用于引用源文件，不复制 Cine；时间含义见 [Timing and TIME64](#timing-and-time64)。

## Raw Cine 与身份

原始 Cine 不修改、不重编码、不承载 annotation、prediction 或 measurement。建议身份信息包含 `cine_id`、`filename`、`file_size_bytes`、`frame_count`、`width`、`height`、`dtype`；可选保存 `mtime_ns`、相机序列号和相机/固件/软件版本。需要更强身份验证时可增加 SHA-256，但不要求每次打开 Cine 都计算整文件哈希。

源文件身份、记录身份、类别和运行版本不能混用：

| 标识 | 含义 |
| --- | --- |
| `cine_id`、`frame_index`、`raw_time64` | 影像、帧位置及原始时间来源 |
| `annotation_id` | 一条 Object 历史记录的唯一 ID |
| `prediction_id` | 一条原始模型预测的 ID |
| `frame_state_record_id` / `record_id` | 一条 Frame State 历史记录的 ID |
| `label_id`、`state_id` | 类别或现象的稳定机器 ID |
| `instance_name` | 可选人工可读名称，不是 tracking ID |
| `model_id`、`model_run_id` | 模型及一次推理运行 |
| `analysis_run_id` | 一次可追溯的测量分析运行 |

## AnnotationDocument

**AnnotationDocument 是 Human Ground Truth 的 canonical source。** 一个 Cine 对应一个人工主文档；多个 Queue frame 共享它。ViewerSession 只保存 UI 工作状态，不替代该主文档。

文档组织 Cine identity、annotation scheme、Object 历史和 active IDs、Frame State 历史和 active pointers，以及创建/修改时间、审核来源和派生关系等 provenance。

采用 sparse annotation：即使 Cine 有数万帧，也只保存真正标注过的帧，不为每帧生成空记录。文档中的 `scheme_id` 和版本说明当时使用哪套标注定义；stable ID 含义发生实质变化时必须升级方案版本，不能静默改义。

### 概念 JSON 与当前实现的区别

以下为原文总体示例的精简版本，字段用于表达数据关系，**不是当前 loader 的可直接导入模板**。

```json
{
  "schema_version": 2,
  "document_id": "annotation-doc-example",
  "cine": {
    "cine_id": "sample",
    "filename": "sample.cine",
    "file_size_bytes": 123456789,
    "frame_count": 32196,
    "width": 256,
    "height": 256,
    "dtype": "uint8"
  },
  "annotation_scheme": {
    "scheme_id": "droplet_annotation_scheme_v1",
    "version": "1.0"
  },
  "object_records": [
    {
      "annotation_id": "object-A",
      "cine_id": "sample",
      "frame_index": 15460,
      "label_id": "parent_droplet",
      "geometry_type": "polygon",
      "geometry": {"points": [[101.2, 53.8], [115.5, 49.1], [132.7, 57.4]]},
      "attributes": {"instance_name": "Parent_01"},
      "raw_time64": 7146562368093756099,
      "relative_timestamp_s": 1.905445,
      "source": "manual",
      "review_status": "unreviewed",
      "created_at": "2026-10-05T00:00:00Z",
      "updated_at": "2026-10-05T00:00:00Z",
      "derived_from": null
    }
  ],
  "active_annotation_ids": ["object-A"],
  "frame_state_records": [
    {
      "record_id": "state-A",
      "cine_id": "sample",
      "frame_index": 15460,
      "raw_time64": 7146562368093756099,
      "relative_timestamp_s": 1.905445,
      "state_ids": ["nucleation", "bubble_growth"],
      "uncertain": false,
      "notes": "",
      "source": "manual",
      "review_status": "unreviewed",
      "created_at": "2026-10-05T00:00:00Z",
      "updated_at": "2026-10-05T00:00:00Z",
      "derived_from": null
    }
  ],
  "active_frame_state_records": {"15460": "state-A"}
}
```

原文示意 `schema_version: 2`、`object_records`、`annotation_scheme`、顶层 `uncertain`。当前 [Annotation architecture](annotation_architecture.md) 描述的实现仍为 schema v1，使用 `records`；v1.3 工作区扩展使用 `scheme` 和 `quality.uncertain`，Object 时间 provenance 位于 `attributes`。本概念文档不启动 schema 升级或字段迁移。

向后兼容以保留既有记录及含义为基础。当前 v1.3 文档约定新增 Frame State 字段可选：旧 v1 文件缺少它们时加载为空状态历史。原文未给出完整 v2 迁移协议，因此本文件不另设迁移规则；实际格式和兼容行为以实现文档为准。

## Object Annotation 与 raw coordinates

Object 回答“图里有什么，以及在哪里”。v1 的六个 stable IDs 为：

```text
parent_droplet
internal_cavity_candidate
daughter_droplet
flame
soot
support_structure
```

具体含义及几何推荐只由 [标注内容方案](annotation_labeling_scheme_v1.md#2-第一层object-annotation) 定义。中文 `display_name` 不改变 `label_id`；内部可见结构使用 `internal_cavity_candidate`，不凭光学外观自动宣称其物理身份。

Polygon 是有序二维点列 `P1 -> P2 -> ... -> Pn -> P1`。所有几何坐标始终对应原始图像：`origin = top-left`、`x = column`、`y = row`。Zoom、pan、Ref90、Manual 和 Auto 不改变 geometry。

`label_id` 表示类别，`annotation_id` 表示唯一历史记录，`instance_name` 是可选名称，如 `Parent_01`、`Cavity_02`、`Daughter_03`。名称不要求唯一，不是 tracking ID，不能据此断言跨帧是同一个物理对象。

## Frame State 与 Quality

Frame State 是 frame-level multi-label data，回答“这一帧正在发生什么”；它不是空间对象，不伪装为 Polygon/BBox，也不混入 Object AnnotationStore。

v1 的十个 state IDs 为：

```text
simple_evaporation
nucleation
puffing
micro_explosion
burning
boiling
sooting
secondary_breakup
bubble_growth
oscillation_deformation
```

FrameStateRecord 保存 `state_ids`、独立的 `uncertain`、`notes`、Cine/frame、TIME64、来源/审核状态、时间戳和 `derived_from`。`uncertain` 是质量标记，绝不能加入物理 `state_ids`。状态可多选，组合的操作性规则仍以标注内容方案为准。

同一 frame 可以同时有一个 parent、多个 cavity、多个 daughter 的 Object records，及一条当前有效的 Frame State record。状态的历史数组独立保留；例如 `active_frame_state_records` 中 `"15460": "state-B"` 指向该帧当前版本。

## Immutable history 与 active view

人工修改遵循 **immutable records + active pointer**：

```text
Record A --edit--> Record B --edit--> Record C
                  derived_from=A    derived_from=B

历史保留 A、B、C；当前 active 指向 C。
```

Object 用 `active_annotation_ids` 表示当前有效记录；Frame State 按帧指向当前版本。Delete 只取消 active，不物理销毁历史。Undo/Redo 恢复 active view，不抹去已产生的旧版本。

该设计支持审核、溯源、Undo/Redo、模型与人工修正比较，以及可重复研究。历史保留不等于所有版本都参与最终训练；导出只选当前有效且经过相应确认的 Ground Truth。

## AI Prediction Store

AI predictions 是独立模型输出，不能自动写入 Human Ground Truth。目标存储结构按模型、运行和 Cine 组织：

```text
outputs/predictions/
└── <model_id>/
    └── <model_run_id>/
        └── <cine_id>/
            ├── manifest.json
            ├── objects_000000_004999.jsonl
            ├── objects_005000_009999.jsonl
            └── ...
```

完整 Cine 可含数万帧，每帧多个对象和状态概率。单个巨大 JSON 加载成本高、追加困难、不利于流式或局部访问，文件损坏影响范围也大。原文建议 JSONL + chunking：每行独立 JSON，可逐行读取/追加，按 chunk 限制处理范围。此建议不等于现已实现随机访问索引或容错服务。

一行 prediction 的结构性示例（为便于阅读展开）：

```json
{
  "frame_index": 15460,
  "raw_time64": 7146562368093756099,
  "objects": [
    {
      "prediction_id": "pred-001",
      "label_id": "parent_droplet",
      "geometry_type": "polygon",
      "geometry": {"points": [[101.2, 53.8], [115.5, 49.1], [132.7, 57.4]]},
      "confidence": 0.94,
      "model_id": "yolo_seg_v1"
    }
  ],
  "state_probabilities": {"nucleation": 0.91, "bubble_growth": 0.78}
}
```

示例概率与模型名称仅演示结构；Frame State probabilities 仍属 Prediction，不是人工标签。**Model confidence ≠ scientific confidence**，不能将模型分数当作物理测量置信区间。YOLO 推理 TXT 可以是中间格式，不应作为长期 Prediction Store 的唯一格式。

### Model provenance

每次推理必须能回答“哪个模型、哪版权重、什么 preprocessing 和 inference settings 产生了这一结果？”

| 信息 | 原文建议字段 |
| --- | --- |
| 模型及运行 | `model_id`、`model_version`、`model_run_id` |
| 权重身份 | weights hash，例如 `weights_sha256` |
| 预处理 | `preprocessing_preset`，例如 `preprocessing.preset_id` |
| 推理设置 | `inference_parameters`，如 confidence / IoU thresholds |
| 执行来源 | `software_version`、`created_at` |
| 标签兼容 | `trained_annotation_scheme` 中的方案 ID 和版本 |

模型 manifest 记录训练时的 annotation scheme，避免把基于 v1 标签训练的输出按 v2 语义解释。Ref90 可作为未来模型预处理候选，但必须显式记录用途与 preset；当前 UI 显示设置不能静默成为训练参数。

## Viewer 同屏比较与 Human Review

目标是同一 frame 同时加载 Prediction、Manual、Reviewed、Ground Truth，必要时再叠加 Measurement Overlay。它们使用共同的 raw image coordinates，因此可比较 AI 与人工边界。

Prediction 默认只读，保留原 confidence 和 model provenance。Manual 是人工独立绘制；Reviewed 是审核或修正后的结果；Ground Truth 是最终确认用于训练/评估的数据。已有图层基础不代表完整模型导入与审核工作流已经完成。

```text
AI Prediction -> Prediction Layer -> Human Review
                                     +-- Accept
                                     +-- Edit
                                     +-- Reject
                                          |
                                          v
                                    Reviewed Layer
                                          |
                                  确认有效结果为 Ground Truth
```

- Accept：生成 `review_status = accepted` 的派生 reviewed record，不直接把模型来源改成人工。
- Edit：生成 `source = manual`、`review_status = edited` 的新记录，`derived_from` 指向原 prediction。
- Reject：保留原 prediction，另外记录拒绝结果，不把被拒绝对象升级为有效 Ground Truth。

原 prediction 的 geometry、confidence、model ID 必须保持不变。保留原始与修正结果后，未来才可研究 IoU、Dice、边界误差、Precision/Recall、False Positive/Negative 和各类别失败案例。

Viewer 已显示当前人工文档路径、保存/未保存状态，并提供复制路径、打开文件夹入口。未来接入 Prediction Store 后，还应显示对应 model/run 来源；这部分仍属于架构目标。

## Measurement Store

**Measurement ≠ Annotation。** Polygon 是几何记录；面积、周长、等效直径、圆度、空腔占比和子液滴数量是派生量，不将大批测量值塞回 AnnotationRecord。原始状态概率属于 Prediction；引用它们形成的分析时间序列也应保留来源。

建议按分析运行输出：

```text
outputs/measurements/<analysis_run_id>/<cine_id>.parquet
```

表格适合筛选、分组、统计、回归和时序分析，可支持 DataFrame / DuckDB 工作流。原文推荐 Parquet，也允许 CSV；这不是当前新增依赖或已提供 measurement backend 的声明。

| 类别 | 建议列 |
| --- | --- |
| 帧与时间 | `frame_index`、`raw_time64`、`relative_timestamp_s` |
| 父液滴 | `parent_area_px2`、`parent_perimeter_px`、`parent_equivalent_diameter_px`、`parent_circularity` |
| 空腔 | `cavity_count`、`cavity_total_area_px2`、`cavity_fraction` |
| 子液滴 | `daughter_count`、`daughter_total_area_px2` |
| 其他区域 | `flame_area_px2`、`soot_area_px2` |

完成 pixel/mm calibration 后才增加面积 mm²、等效直径 mm 等列。原文还提出最小 cavity-to-parent-boundary distance 可作为 shell thickness proxy 的研究方向，不能直接当作真实三维壳厚。

### 科学量边界与 analysis provenance

```text
2D equivalent diameter: D_eq = 2 * sqrt(A / pi)
Circularity:             C = 4 * pi * A / P^2
Cavity fraction:             sum(cavity_area) / parent_area
```

`A` 为二维面积，`P` 为周长。圆度可靠性依赖分割边界质量。二维等效直径不是 true 3D diameter；明显非球形液滴的二维 mask 不能直接给出真实 3D volume / surface area。只有明确且验证过的近球形假设下，才讨论 sphere-equivalent volume / surface area，并记录该假设。

每个 measurement run 必须有 `analysis_run_id`，保留 source prediction run 或 source Ground Truth version、calibration version、measurement code version。测量应能重新计算并解释差异，不能只留下没有来源的结果表。

## Timing and TIME64

科学时间来自 **raw TIME64**，重要记录保留 `frame_index`、`raw_time64`、`relative_timestamp_s`、`timing_status`。遵守现有 [timing policy](timing_policy.md)：

```text
delta_t_s = (raw_TIME64_i - raw_TIME64_reference) / 2^32
```

先做整数减法，再转浮点。不得静默以 `frame_index / header_fps` 替代正式科学时间。缺失或非单调时间戳需要复核；TIME64-derived 时间仍须携带原有 timing status，不能因使用 TIME64 就自动宣称 validated。

现有政策中的 header 8146 fps 与 timestamp-derived 约 4073.32 fps 差异仍为 `TIMING_MISMATCH_UNRESOLVED`；此处沿用政策，不作新的原因判断或实验验证。

Ground Truth v1 不强制人工标注 `NUCLEATION_ONSET`、`PUFFING_ONSET`、`MICRO_EXPLOSION_ONSET`、`IGNITION_ONSET`。未来可结合 Object trajectory/changes、Frame State probabilities、temporal smoothing/persistence 和 TIME64 推断 `t_nuc`、`t_puff`、`t_ME`、`t_ign`，仍须遵守科学时间的验证边界。

## Dataset Export 与 Annotation Queue

### Dataset Export

```text
AnnotationDocument
    -> active Ground Truth records
    -> Dataset Exporter
    -> images/ + labels/ + dataset.yaml
```

AnnotationDocument 是 canonical human annotation source；YOLO segmentation dataset 只是 derived training representation。训练代码不必直接处理复杂历史，原文档仍保留。YOLO TXT 难以完整表达 history、TIME64、review provenance、notes、Frame State、uncertain 和 instance metadata，不能反过来成为唯一 Ground Truth。

### Annotation Queue

Queue 是 work management layer：

```text
Queue Item -> Open Cine/frame -> Human annotation
           -> AnnotationDocument -> Mark Done
```

Queue status 不能替代 annotation data，也不构成 Ground Truth 审核结论。具体当前实现见 [Frame Sampling and Annotation Queue](frame_sampling_queue.md)。

## Display 与 scientific data 分离

Raw display、Photometric Normalization (Ref90)、Manual enhancement、Auto contrast、zoom、pan 和 overlay colors 属于显示。Raw pixels、geometry、label/state IDs、TIME64、confidence 和 measurement values 属于数据；显示不得修改这些数据。

Ref90 可服务人工观察，也可作为未来显式配置的模型预处理候选，两种用途必须分别记录。Ground Truth geometry 始终基于 raw image coordinates；scientific grayscale intensity 始终使用 raw pixels。相关边界见 [image preprocessing policy](image_preprocessing_policy.md)。

## 推荐目录、规模与数据库政策

原文推荐的长期布局如下，其中 predictions / measurements 为架构目标：

```text
droplet--vision/
├── configs/
│   ├── annotations/
│   ├── photometry/
│   └── sampling/
├── docs/
├── outputs/
│   ├── annotations/<cine>.annotations.json
│   ├── annotation_queues/
│   ├── predictions/<model_id>/<model_run_id>/<cine_id>/
│   │   ├── manifest.json
│   │   └── objects_<range>.jsonl
│   ├── measurements/<analysis_run_id>/<cine_id>.parquet
│   └── viewer_smoke/
└── src/
```

大数据输出保持 Git ignored。以上是逻辑组织建议，不覆盖现有 Queue 关联文档的具体保存路径。

当前阶段不需要数据库：稀疏人工 JSON 便携、可读、易调试，预测通过 chunked JSONL 控制规模，measurement 用 CSV / Parquet 便于分析。这是分阶段存储选择，不代表后两类 Store 已实现。

未来达到 hundreds of Cine、millions of frames、many model runs 时，可考虑 Parquet、DuckDB、SQLite、object storage 等扩展。只有大量并发用户、跨机器协作、百万级对象查询、复杂搜索、大量 run 管理或服务器端 annotation platform 等需求出现时，才评估数据库，包括 SQLite、PostgreSQL、DuckDB；当前工作站不依赖这些系统。

## 后续数据流与 Active Learning

下面是原文的未来工作流，不是当前已具备的端到端自动流程：

```text
Raw Cine -> Sampling -> Queue -> Human Annotation -> AnnotationDocument
                                                       |
                                      +----------------+---------------+
                                      v                                v
                               Dataset Export                    Validation Set
                                      |
                                Model Training
                                      |
                                Prediction Store
                                      |
                                Viewer / Review
                                      |
                              Accept / Edit / Reject
                                      |
                              Reviewed / Ground Truth
                                      |
                                Model Retraining

Prediction / Ground Truth -> Scientific Measurement -> Measurement Store
                          -> Transient Analysis -> Paper Figures / Statistics
```

Active Learning 可从 Initial GT 训练 Model v1，在更多 Cine 上运行，挑选低置信度、模型/人工分歧、稀有状态、复杂破碎等 hard cases，送回 Annotation Queue 经人工审核，形成 More GT 再训练 Model v2。自动选帧不等于自动确认物理现象。

架构围绕 Cine、Frame、Object、State、Prediction、Review、Measurement、Provenance，而不是某个模型。YOLO、U-Net 或未来模型可以替换，Human Ground Truth 不应因此推倒重来。

## 当前实现状态与未来目标

本节区分当前源码已实现的工作流与未来目标；Implemented 不等同于发布版本保证。操作入口见 [文档索引](README.md)，具体数据结构见 [Annotation architecture](annotation_architecture.md)。本文件继续作为整体数据架构的唯一规范来源。

| 状态 | 组件 | 依据与边界 |
| --- | --- | --- |
| Current foundation | Cine Reader、raw frame / TIME64、Viewer 与 Ref90 显示 | [Cine Reader](cine_reader.md)、[Viewer](cine_viewer.md)；显示与原始数据分离 |
| Current foundation | AnnotationDocument、Object Annotation、append-only history、active IDs、Undo/Redo、atomic save | [Annotation architecture](annotation_architecture.md)、[Editor](annotation_editor.md) |
| Current foundation | Annotation Queue、可复现采样与进度管理 | [Sampling / Queue](frame_sampling_queue.md)；不自动判定物理事件 |
| Current foundation | Viewer layers、派生人工/Reviewed record 的基础能力 | 原 prediction 不被覆盖；不代表完成实际模型导入和完整审核流程 |
| Implemented | Frame State 历史与 active pointers、独立 Quality/Notes、Scheme snapshot、可选 instance name 操作 | [Editor](annotation_editor.md)；旧 v1 文件兼容加载 |
| Implemented v1 | Portable Review Package：稀疏 raw PNG、离线审核、返回候选导入与对象冲突处理 | [Review workflow](portable_review_package.md)；不自动覆盖原人工数据或升级 Ground Truth；返回 Frame State 保留为历史候选 |
| Future / planned | Prediction Import / Store、实际模型输出接入与模型审核流程 | 图层和人工离线审核基础不等于模型系统已完成 |
| Future / planned | Dataset Export、YOLO-seg baseline、完整 inference integration、Active Learning | 原文后续方向，不由本次文档任务实现 |
| Future / planned | Measurement Store、analysis provenance 执行链与时序事件推断 | 本文规范派生数据边界，不声明已提供测量功能 |

## 冻结的核心结论

1. Cine 是 immutable source，不写入标注、预测或测量。
2. 一个 Cine 对应一个 Human AnnotationDocument。
3. Human Ground Truth 使用 sparse JSON，保留审核与来源。
4. Object 与 Frame State 分开存储，Quality 独立于物理 state。
5. Geometry 使用 raw image coordinates，显示不改变 Ground Truth。
6. Annotation history 不原地覆盖，active view 决定当前有效版本。
7. Prediction 与 Human Ground Truth 分开，模型输出不能伪装成人工事实。
8. Prediction 按 model/run/Cine 组织。
9. 大规模 Prediction 优先采用分块、流式 JSONL，不用一个巨大 JSON。
10. AI 与人工 annotation 可在共同 raw coordinates 下同屏比较。
11. Human correction 创建 derived record，保留原 prediction。
12. Measurement 与 annotation/prediction 分开，优先表格型存储。
13. YOLO dataset 是派生训练格式，不是 canonical Ground Truth。
14. TIME64 是 scientific timing source，保留 timing status，不用 nominal-FPS 替代。
15. 每个模型结果必须保存 model provenance。
16. 每个 measurement run 必须保存 analysis provenance。
17. 当前阶段不需要数据库。
18. Ground Truth schema 不绑定单一模型，允许模型迭代和 measurement 重算。

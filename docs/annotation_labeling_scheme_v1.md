# Droplet Vision 标注内容方案 v1.0

Droplet Annotation Labeling Scheme v1.0

- Version: 1.0
- Status: Approved baseline
- Scope: Object annotation + frame-level phenomenon/state annotation + quality flag
- Event onset annotation: Not included in v1.0

本文件是正式标注内容的 single source of truth，定义 Droplet Annotation Scheme v1.0。它记录已经确认的标注方案，不表示所有相关软件功能已经实现。本轮规范不修改 taxonomy JSON、annotation JSON schema 或 UI；Frame State、质量标记和可选实例名称的后续软件支持应以本规范为依据。

## 1. 总体原则：两层标注 + 独立质量标记

1. **Object Annotation**：回答“图里有什么”，记录具有空间位置和几何形状的可见对象。
2. **Frame Phenomenon / State Annotation**：回答“这一帧正在发生什么”，记录当前整帧的现象或状态。
3. **Quality Flag**：回答“这个人工判断是否存在明显不确定性”，独立记录判断质量。

Object 与 State 必须分离。禁止以 `puffing_parent_droplet`、`micro_explosion_droplet` 等 object + state 复合类别代替两层标注。

Frame State 必须支持多选，不要求所有状态彼此互斥。Stable ID 永远使用英文机器 ID；中文仅作为 display name，不改变记录中的 stable ID。v1.0 冻结以下标签的语义，并不把未来可扩展 taxonomy 封闭为永远不可增加的列表。

## 2. 第一层：Object Annotation

### Object 总表

| Stable ID | 中文名称 | 主要几何类型 |
|---|---|---|
| `parent_droplet` | 父液滴 | Polygon |
| `internal_cavity_candidate` | 内部空腔候选区 | Polygon |
| `daughter_droplet` | 子液滴 | Polygon / Point |
| `flame` | 火焰 | Polygon |
| `soot` | 烟炱 | Polygon |
| `support_structure` | 支撑结构 | Polygon / BBox |

### `parent_droplet` — 父液滴

含义：当前仍属于主体液滴的可见整体区域。

推荐 Polygon 或 Magic Wand → Polygon。主要服务于后续 YOLO-seg、instance segmentation 和 geometry analysis。

### `internal_cavity_candidate` — 内部空腔候选区

含义：父液滴内部可以辨识的空腔、气泡样或明显内部光学结构。

推荐 Polygon 或 Magic Wand → Polygon。**不要直接命名为 bubble。** 高速背光图像中的内部亮／暗区域可能受到以下因素影响：

- vapor cavity/bubble；
- refraction（折射）；
- optical path length（光程）；
- focus（对焦）；
- droplet thickness（液滴厚度）；
- illumination（照明）。

Object 层只描述可见结构，不自动声明其物理身份；亮区或暗区本身不足以证明 bubble 或 liquid。

### `daughter_droplet` — 子液滴

含义：已经与父液滴主体明显分离、可独立辨识的液滴或碎片。

推荐 Polygon。极小且轮廓不足以可靠描绘时可以使用 Point；正式实例分割数据优先使用 Polygon，不能把一个 Point 当作已有可靠分割轮廓。

### `flame` — 火焰

含义：图像中可辨识的可见火焰区域。推荐 Polygon。

`flame` 是 spatial object；`burning` 是 frame state。二者不是同一个概念，也不具有强制等价关系。

### `soot` — 烟炱

含义：图像中可辨识的烟炱、黑烟或明显颗粒云区域。推荐 Polygon。

`soot` 是 spatial object；`sooting` 是 frame state。前者记录烟炱在哪里，后者记录是否正在表现烟炱生成行为。

### `support_structure` — 支撑结构

含义：热电偶、支撑丝、悬挂结构或其他可能干扰视觉识别的固定实验结构。

推荐 Polygon / BBox。标注目的是避免模型将实验结构误识别为液滴或碎片。

## 3. 第二层：Frame Phenomenon / State

Frame State 作用于整个当前 frame，不具有 polygon geometry，支持多选，不要求彼此互斥。涉及出现、增长、持续活动或破碎过程的判断应结合相邻帧证据；证据不足时使用独立质量标记，而不是从单帧亮暗自动推断物理现象。

### Frame State 总表

| Stable ID | 中文名称 | 类型 |
|---|---|---|
| `simple_evaporation` | 单纯 / 稳定蒸发 | 核心现象 |
| `nucleation` | 成核（Nucleation） | 核心现象 |
| `puffing` | Puffing | 核心现象 |
| `micro_explosion` | 微爆（Micro-explosion） | 核心现象 |
| `burning` | 燃烧（Burning） | 核心现象 |
| `boiling` | 沸腾（Boiling） | 核心现象 |
| `sooting` | 烟炱生成（Sooting） | 核心现象 |
| `secondary_breakup` | 二次破碎（Secondary breakup） | 核心现象 |
| `bubble_growth` | 气泡 / 空腔生长 | 动态状态 |
| `oscillation_deformation` | 振荡 / 变形 | 动态状态 |

### `simple_evaporation` — 单纯 / 稳定蒸发

当前液滴主要表现为平稳蒸发、尺寸缓慢变化，没有明显复杂内部现象或破碎现象。

不使用普通 `evaporation` 作为 v1 state ID：evaporation 几乎贯穿液滴整个寿命，可能同时存在 evaporation + nucleation、evaporation + puffing、evaporation + burning，因此作为训练标签区分度较低。

v1 使用 `simple_evaporation` 表达没有明显 nucleation、puffing、micro-explosion 等复杂行为的稳定蒸发阶段。

### `nucleation` — 成核（Nucleation）

液滴内部出现明显的新空腔、气泡样结构形成现象。典型证据包括：新的内部 cavity 出现、新的 bubble-like structure、明显内部相界面形成。

可以同时存在 Object `internal_cavity_candidate` 与 State `nucleation`；前者描述结构，后者记录对形成现象的人工判断。

### `puffing` — Puffing

内部气泡或压力局部释放，造成局部喷射或少量物质／子液滴脱离，但父液滴主体仍基本保留。

典型表现是少量 daughter droplets、局部破裂、局部喷射，parent body 没有瞬间整体崩解。必须与 `micro_explosion` 区分。

### `micro_explosion` — 微爆（Micro-explosion）

父液滴发生快速、剧烈、整体性的破碎。典型表现包括：

- parent integrity 快速丧失；
- 短时间产生大量 daughter droplets；
- 多方向快速扩散；
- 破碎程度明显高于普通 puffing。

### `burning` — 燃烧（Burning）

当前液滴或其蒸气处于明确燃烧阶段。可能伴随 Object `flame`，但不能把 `flame == burning` 作为强制等价关系。

### `boiling` — 沸腾（Boiling）

液滴内部存在持续、剧烈的气泡活动，整体表现出类似沸腾的动态状态。可能包括 multiple cavities、rapid bubble motion、repeated expansion/collapse、highly unstable internal dynamics。

不能仅仅因为存在一个 cavity 就标记 `boiling`。

### `sooting` — 烟炱生成（Sooting）

当前阶段存在明显烟炱生成行为。`soot` 回答“烟炱在哪里”（Object），`sooting` 回答“是否正在表现烟炱生成行为”（State）。不能仅凭已有 soot object 自动赋予生成状态。

### `secondary_breakup` — 二次破碎（Secondary breakup）

已经由 parent 产生的 daughter/sub-droplet 进一步破裂成更小的液滴。

必须区分 parent 首次整体破碎与 daughter droplet 再次破碎；后者才是 `secondary_breakup`。

### `bubble_growth` — 气泡 / 空腔生长

类型：Dynamic state（动态状态）。已经存在的 internal cavity / bubble-like region 在相邻帧中明显增大。

这是 temporal concept，不应只看一张孤立静态图判断。人工判断应结合 previous frame、current frame、next frame。此状态名称不改变 Object 层使用 `internal_cavity_candidate` 的证据边界。

### `oscillation_deformation` — 振荡 / 变形

类型：Dynamic state（动态状态）。父液滴发生明显 oscillation、shaking、stretching、flattening、twisting 或 irregular deformation，但不要求已经发生 breakup。

可以与 `nucleation`、`bubble_growth`、`puffing` 等状态同时存在。

## 4. 独立 Quality Flag

唯一质量标记 stable ID：`uncertain`。中文：不确定（Uncertain）。

**`uncertain` 不是物理现象，也不属于 Frame State table。** 它是 annotation quality flag：标注者倾向某个判断，但认为图像证据不足，需要后续复核。

例如：

```text
Frame States:
- nucleation
- bubble_growth

Quality:
uncertain = true
```

未来 UI 建议如下，仅为规范建议，不表示本轮新增软件功能：

```text
判定质量
[ ] 不确定（Uncertain）
备注：[...]
```

`notes` 是补充解释的自由文本，不是第二个 quality flag。

## 5. 暂不加入 v1

以下 ID 的状态均为 **NOT INCLUDED IN V1**，不属于 v1 正式 training labels：

| Reserved ID | v1 状态 |
|---|---|
| `ignition` | NOT INCLUDED IN V1 |
| `auto_ignition` | NOT INCLUDED IN V1 |
| `bursting` | NOT INCLUDED IN V1 |

### Ignition / auto-ignition

Ignition 更接近一个 event onset，而不是持续时间较长的普通 Frame State。未来可以通过 flame first stable appearance + burning state + temporal continuity + TIME64 推导 ignition timing。v1 不要求人工逐帧标 ignition onset，也不加入 `auto_ignition`。

### Bursting

原稿中出现过 bursting，但当前尚无足够明确、稳定的操作性判据区分 bursting、puffing、micro_explosion。在定义稳定前，`bursting` 不进入正式 v1 training labels；未来可升级 taxonomy/version 后加入。

## 6. 多标签规则

明确允许以下组合：

- `nucleation` + `bubble_growth`；
- `nucleation` + `bubble_growth` + `oscillation_deformation`；
- `puffing` + `oscillation_deformation`；
- `micro_explosion` + `secondary_breakup`；
- `burning` + `sooting`。

`simple_evaporation` 通常不应与 `nucleation`、`puffing`、`micro_explosion` 共同勾选。一旦出现明显复杂现象，原则上取消 `simple_evaporation`。多选表示各状态分别有证据支持，不表示出现一个状态就自动添加其他状态。

## 7. 典型案例

### Case A — 稳定蒸发

Objects:

- `parent_droplet`

States:

- `simple_evaporation`

### Case B — 成核

Objects:

- `parent_droplet`
- `internal_cavity_candidate`

States:

- `nucleation`

### Case C — cavity growth

Objects:

- `parent_droplet`
- `internal_cavity_candidate`

States:

- `nucleation`
- `bubble_growth`

该组合用于同时有形成与增长证据的情形；增长应结合相邻帧判断。

### Case D — Puffing

Objects:

- `parent_droplet`
- `internal_cavity_candidate`
- `daughter_droplet`

States:

- `puffing`
- `oscillation_deformation`

### Case E — Micro-explosion

Objects:

- `parent_droplet`（only if still identifiable）
- `daughter_droplet` × N

States:

- `micro_explosion`

如果 daughter droplets 又继续破碎，States 为 `micro_explosion` + `secondary_breakup`。

### Case F — Burning

Objects:

- `parent_droplet`
- `flame`

States:

- `burning`

如果还有明显 soot，并有烟炱生成行为证据，Objects 增加 `soot`，States 为 `burning` + `sooting`。

## 8. Instance Naming

未来 Object annotation 支持可选 `instance_name`，例如：

```text
Parent_01
Cavity_01
Cavity_02
Daughter_01
Daughter_02
Flame_01
Soot_01
```

三个字段必须区分：

| 字段 | 含义 |
|---|---|
| `label_id` | 类别的稳定机器 ID |
| `annotation_id` | 系统唯一记录 ID |
| `instance_name` | 人工可读、可选实例名称 |

`instance_name` 不应成为强制字段；本规范不要求本轮修改现有 schema。

## 9. Display / raw policy

Raw、Photometric Normalization (Ref90)、Manual、Auto 都只是显示方式。

所有 Polygon coordinates、Point coordinates 和 Annotation geometry 始终基于 raw image coordinates：原点为左上角，x 为 column，y 为 row。Magic Wand source pixels 必须来自 raw pixels，而不是 Ref90 或其他增强后的显示图像。

Ref90 不得改变 Ground Truth geometry。Zoom、pan 和显示强度变换不能改变保存的原始图像坐标；科学灰度分析仍使用 raw pixels，不使用显示增强像素。

## 后续模型关系

Spatial segmentation 未来可能学习六类空间对象：`parent_droplet`、`internal_cavity_candidate`、`daughter_droplet`、`flame`、`soot`、`support_structure`，可能使用 YOLO-seg、U-Net 或其他 segmentation model。

Frame-state recognition 是独立问题。未来输入可能包括 image、object masks、parent area、cavity area、daughter count、adjacent frames 和 temporal features；输出为：

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

不要求所有标签由同一个 YOLO 模型完成。本节描述未来关系，不声明已经实现模型推理或状态识别。

## 10. Event timing policy

v1 不要求人工标记 `NUCLEATION_ONSET`、`PUFFING_ONSET`、`MICRO_EXPLOSION_ONSET` 或 `IGNITION_ONSET`。

未来可以根据 Object predictions + Frame-state probabilities + temporal persistence + TIME64 自动推导 event timing；推导方法仍需验证。

正式科学时间必须来自 TIME64，遵守现有 [timing policy](timing_policy.md)。计算时间差时先做原始 TIME64 整数减法，再除以 `2**32`。禁止使用 `frame_index / header_fps` 作为正式 scientific timing。已有 timing mismatch 不能因标注或事件推导而被自动视为已解决。

## 11. v1 Stable ID Registry

以下注册表固定 **6 个 Object IDs、10 个 Frame State IDs、1 个 Quality flag**。Reserved IDs 不计入 v1 标签。

```text
Object IDs:
parent_droplet
internal_cavity_candidate
daughter_droplet
flame
soot
support_structure

Frame State IDs:
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

Quality:
uncertain

Reserved / not used in v1:
ignition
auto_ignition
bursting
```

## 12. Version policy

本文件定义 Droplet Annotation Scheme v1.0。一旦正式 Ground Truth 开始生成，stable ID 的语义不得静默修改。

以下情况必须升级版本，例如 v1.1 或 v2.0：

- 新增标签；
- 删除标签；
- 标签拆分；
- 标签合并；
- 操作性判据发生实质改变。

必要时记录 taxonomy migration，说明旧版本标签与新版本的对应关系及复核需求。显示名称的翻译不改变 stable ID；不得通过改中文名称隐含改变类别语义。

## 13. 最终结构

```text
FRAME
│
├── Object Annotations
│   ├── parent_droplet
│   ├── internal_cavity_candidate
│   ├── daughter_droplet
│   ├── flame
│   ├── soot
│   └── support_structure
│
├── Frame States
│   ├── simple_evaporation
│   ├── nucleation
│   ├── puffing
│   ├── micro_explosion
│   ├── burning
│   ├── boiling
│   ├── sooting
│   ├── secondary_breakup
│   ├── bubble_growth
│   └── oscillation_deformation
│
└── Quality
    ├── uncertain
    └── notes
```

## 14. 核心原则总结

1. Object 回答“图里有什么”。
2. State 回答“这一帧正在发生什么”。
3. Object 与 State 不混合。
4. Frame State 支持多选。
5. Uncertain 是质量标记，不是物理现象。
6. 内部光学结构使用 cavity candidate，不自动断言 bubble。
7. Puffing 与 Micro-explosion 必须区分。
8. Secondary breakup 与父液滴首次破碎必须区分。
9. Stable ID 不随中文 UI 名称变化。
10. 空间标注始终使用 raw image coordinates。
11. Ref90 只用于显示，不改变 Ground Truth。
12. Event onset 暂不人工标记，未来从时序结果 + TIME64 推导。

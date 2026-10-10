<div align="center">
  <img src="src/droplet_vision/ui/assets/icons/planico.png" alt="Droplet Vision" width="200">

# Droplet Vision

**高速液滴影像标注、协同审阅与 AI 辅助定量分析工作站**

面向 Phantom 高速 Cine 数据浏览、可追溯人工标注、离线协作与后续 AI 瞬态液滴定量分析的科研桌面软件。

[English](README.md) | 简体中文

[![项目：科研软件](https://img.shields.io/badge/project-research%20software-3B6FB6)](#项目概览)
[![工作流：人工参与](https://img.shields.io/badge/workflow-human--in--the--loop-2A9D8F)](#核心工作流)
[![数据：Phantom Cine](https://img.shields.io/badge/data-Phantom%20Cine-E9A23B)](docs/cine_viewer.md)
[![界面：PySide6](https://img.shields.io/badge/UI-PySide6-7A6FAC)](pyproject.toml)
<br>
[![Python：已测试 3.12](https://img.shields.io/badge/Python-3.12%20tested-3B6FB6)](#安装说明)
[![平台：Windows](https://img.shields.io/badge/platform-Windows-7B8794)](docs/getting_started.md)
[![许可证：BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-D96C75)](LICENSE)
[![状态：持续开发](https://img.shields.io/badge/status-active%20development-2A9D8F)](#后续计划)

</div>

## 项目概览

高速液滴实验产生的影像通常远超人工逐帧检查、完整标注的能力。
Droplet Vision 将 Phantom `.cine` 只读访问、可追溯人工标注、时序状态判断和离线协作串成一条工作流。

当前工作站提供人工标注与灰度辅助选区。AI 辅助定量分析是后续方向：
**目前不提供训练好的模型、自动物理事件识别或科学测量执行流程**。
模型是未来证据处理与人工复核链路中的一个组件。

## 界面展示

<div align="center">
  <a href="Example/236.png"><img src="Example/236.png" alt="Droplet Vision 标注工作区与关于对话框" width="95%"></a>
</div>

*Cine 元数据、对象标注、帧状态、时间轴导航与离线协作集中于同一工作区。
保留的原始截图展示了早期 Portable Review Mode，现已更名为标注包模式；部分控件已有更新。*

**左栏**查看影像信息、标注体系与当前标注，**中间**查看和编辑图像，
**右栏**完成对象与帧状态操作，**底部**负责导航和检阅速度。中文 / English 可实时切换。

## 功能亮点

| 领域 | 当前源码已实现 |
| --- | --- |
| Cine 浏览 | 按需读取、有限容量 raw 缓存、完整 TIME64、时间诊断、缩放平移与自动适应窗口 |
| 显示 | 原始图像、Cine 内锁定增益的亮度标准化（Ref90）、手动增强、自动对比度与 raw PNG 导出 |
| 对象标注 | 多边形、点、基于原始灰度的魔棒、闭合草稿编辑、空格确认、节点/中点编辑及撤销重做 |
| 标注信息 | 可选实例名、Scheme 驱动的标签与颜色、子液滴编号、多选帧状态、独立“不确定”与备注 |
| 导航与任务 | 可点击的人工标注帧标记、可恢复的 Annotation Queue、可复现锚点/变化峰值采样与独立均匀采样 |
| 标注包 | 允许空标注的 `.dvapkg`、离线编辑、旧 `.dvrpkg` 读取、原子快捷保存与另存副本 |
| 协作审阅 | 不可变历史、返回的 Reviewed 候选、来源记录与 base/local/reviewer 冲突选择 |
| 载滴杆复用 | 全 Cine / 全标注包模板、逐帧稀疏平移与局部几何覆盖 |
| 批量生成 | 递归发现 Cine、镜像目录、每个 Cine 一包、进度/取消与跳过已有包续跑 |

## 快速开始

在 Windows PowerShell 中，准备好 Python 3.12 后运行：

```powershell
git clone https://github.com/xiaorouqiuzi-ai/droplet--vision.git
cd droplet--vision
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[cine,ui]"
python scripts/launch_viewer.py
```

选择 **文件 → 打开 Cine…**，或 **功能 → 打开标注包…**。
打开标注包不需要原始 Cine。[入门指南](docs/getting_started.md)介绍环境配置、首次标注与保存重开。

## 安装说明

当前请使用保留 `configs/` 的**源码检出目录**。
项目元数据声明 Python `>=3.9`；已测试的 Windows 桌面环境使用 **Python 3.12.10**。
元数据最低版本不等于所有可选 UI 依赖均支持或已验证每个 Python 版本。

[pyproject.toml](pyproject.toml) 定义了 `cine`（PIMS 0.7）和 `ui`（PySide6 6.10.2）两个 extras。
基础接口没有强制依赖；当前工作流无需 GPU、Torch、YOLO、OpenCV 或 SciPy。

激活环境后可使用 `launch_viewer.cmd` 启动。
桌面快捷方式与外部 Python 环境的配置见[启动说明](docs/getting_started.md#launch)。
本机解释器路径只应保存在本地设置中，不写入版本化配置。
Windows 安装程序与文件关联仍在后续计划中。

## 核心工作流

```text
A · 本地标注
Cine → 帧浏览 → 对象标注 + 帧状态 → AnnotationDocument

B · 离线协作
Cine 数据集 → 均匀 / 批量抽帧 → .dvapkg → 协作者
           → 标注或审阅 → 返回标注包 → Reviewed 候选

C · 后续分析（规划中）
Ground Truth → 模型训练 → Prediction → 人工复核 → Measurement
```

应用标注体系，选择未锁定的绘制图层与对象，再绘制并闭合草稿。
画布获得焦点时，**空格确认已闭合的多边形或魔棒草稿**，**Esc 取消**。
未闭合草稿按空格不会提交，也不会启动播放；没有草稿时空格仍切换播放/暂停。
文本框保留正常空格输入，Enter 确认仍然可用。

请显式保存 **AnnotationDocument**。ViewerSession 另行保存导航与 UI 状态。
详见[工具与快捷键](docs/annotation_editor.md#keyboard-shortcuts)。

## 标注模型

采用两层标注和独立质量标记：

| 内容 | 回答的问题 |
| --- | --- |
| 对象标注 | “图里有什么、在哪里？”——六个 v1 稳定 ID，几何使用 raw 图像坐标 |
| 帧状态 | “这一帧正在发生什么？”——十个 v1 稳定 ID，支持多标签判断 |
| 判定质量 | `uncertain` 与备注记录证据不足，不作为物理现象类别 |

`internal_cavity_candidate` 描述可见内部结构，不直接断言其为气泡。
动态状态需要结合相邻帧；魔棒与变化峰值采样都不会自动识别物理事件。
[标注内容方案 v1.0](docs/annotation_labeling_scheme_v1.md) 是科学定义的唯一来源，
显示名称的中英文切换不会改变 stable ID。

## 标注包

**`.dvapkg` 是可独立分发的标注任务与协作格式。**
包内包含选取的 raw PNG、TIME64 与时间状态、Annotation Scheme 快照、可选对象/帧状态、
Ref90 来源信息、审阅历史和 SHA-256 校验信息。已有标注数量可以为零，旧 `.dvrpkg` 仍可读取。

协作者只需标注包即可开展标注或审阅，无需接收数 GB 或数 TB 的原始 Cine 数据集。
实际包体积取决于内容，不承诺固定压缩比例。

- **创建：** 功能 → 从 Cine 均匀抽帧创建标注包…。源 Cine 至少有 N 帧时，
  输出恰好 N 个唯一目标帧，包含首尾。32196 帧抽取 50 帧，即 50 个点、49 个间隔。
- **离线操作：** 打开包并标注；数据变化后，底部右侧出现**保存标注包**，
  原子覆盖当前 `.dvapkg`。**保存标注包为…**用于保留版本或返回副本。
- **复用载滴杆：** “应用全包”只影响包内已有的目标/上下文帧；
  “应用全 Cine”属于 Cine 模式。两种作用域均支持逐帧稀疏偏移。
- **返回合并：** 导入后保留 Reviewed 候选、冲突与来源，
  不会静默替换 canonical Ground Truth / 人工真值，也不会自动替换 Cine 模板。

完整操作与候选采用限制见[标注包指南](docs/annotation_package.md)。

## 按文件夹批量创建标注包

**功能 → 按文件夹批量创建标注包…**递归处理 Cine，保留源目录本身名称与子目录层级：

```text
源目录                       输出
A/                           Packages/
├── B/111.cine                └── A/
└── C/222.cine                    ├── B/111.dvapkg
                                 └── C/222.dvapkg
```

默认**每 Cine 20 个目标帧、0 个上下文帧、跳过已有包**。
短 Cine 导出全部可用帧，逐个 Cine 处理；取消保留已完成的包，单个文件失败不阻止其余任务。
源目录严格只读。`_batch_manifest.json` 记录相对路径、数量与结果，
再次执行并跳过已有包即可简单续跑。详见[批量生成说明](docs/annotation_package.md#batch-annotation-package-generation)。

## 数据与科研完整性

- **原始 Cine 只读。** 显示变换不改变科学像素数据。
- **Ref90 不替代原始强度。** Raw 导出与魔棒均使用 raw pixels。
- **几何使用 raw 图像坐标**，不受缩放、平移或显示方式影响。
- **TIME64 是科学时间来源。** 保留 timing status，不用 `frame_index / header_fps`
  替代科学时间，也不因图像可读就忽略未解决的 timing mismatch。
- **检阅速度仅用于 UI 浏览。** 1000 帧/秒表示每现实秒约推进 1000 个源帧，
  允许跳过部分中间图像；它不是实验采集帧率。
- **Ground Truth ≠ Prediction ≠ Measurement。** 模型预测不能覆盖人工真值；
  标注包属于运输/协作层，不是另一套 canonical 数据层。
- 未来训练/评估应按 **Cine / 实验 run** 划分，避免随机拆分相关的抽样帧造成数据泄漏。

详见[数据架构](docs/data_architecture_concept_v1.md)与[预处理政策](docs/image_preprocessing_policy.md)。

## AI 集成状态

当前项目在**架构层面为 AI 集成做好准备**：已有 prediction provider / 图层接口、
不可变派生记录与审阅来源机制。正式模型导入/推理、数据集导出、分割基线、跟踪、
自动测量和时序事件推断均为**未来工作**，不提供训练权重或自动微爆识别。

## 仓库结构

```text
droplet--vision/
├── configs/                 标注体系、采样与显示预设
├── docs/                    使用指南、科学政策与架构
├── Example/236.png          原始工作区截图
├── scripts/                 启动、清点、队列与文档检查工具
├── src/droplet_vision/
│   ├── cine/                只读帧访问与时间信息
│   ├── annotations/         标注文档、Scheme 与辅助标注
│   ├── sampling/            均匀 / 启发式采样与队列
│   ├── review_package/      标注包导出、批量生成与合并
│   └── ui/                  桌面工作站；assets/icons/ 内含 PNG 与 ICO
├── tests/                   合成数据、Qt 与按需启用的真实 Cine 测试
├── launch_viewer.cmd
├── README.md / README.zh-CN.md
└── LICENSE
```

## 文档导航

从[文档索引](docs/README.md)开始。

| 文档 | 用途 |
| --- | --- |
| [Getting Started](docs/getting_started.md) | 安装、启动与首次工作流 |
| [Cine Viewer](docs/cine_viewer.md) | 导航、检阅速度、元数据与显示 |
| [Annotation Editor](docs/annotation_editor.md) | 工具、草稿、快捷键与载滴杆模板 |
| [标注内容方案 v1](docs/annotation_labeling_scheme_v1.md) | 对象、帧状态与质量标记的正式定义 |
| [Annotation Package](docs/annotation_package.md) | 离线任务、批量生成、审阅与冲突 |
| [Frame Sampling & Queue](docs/frame_sampling_queue.md) | 可复现候选选择与任务恢复 |
| [数据架构](docs/data_architecture_concept_v1.md) | Ground Truth / Prediction / Measurement 边界 |
| [预处理政策](docs/image_preprocessing_policy.md) | 原始数据、显示与模型预处理分离 |
| [Photometric Presets](docs/photometric_presets.md) | 冻结的 Ref90 参数与来源 |
| [Annotation Architecture](docs/annotation_architecture.md) | 历史记录、持久化与开发接口约定 |

## 验证

在仓库根目录、已激活的环境中运行：

```powershell
python -m pip check
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -s tests -v
python -m compileall src scripts
python scripts/check_docs_links.py
git diff --check
```

测试覆盖 Cine I/O、raw pixels/时间、标注编辑、帧状态、标注包/合并、采样和 Qt UI。
真实 Cine 集成测试需通过 `DROPLET_VISION_TEST_CINE` 与 `DROPLET_VISION_LAYOUT_TEST_CINE`
按需指定本地样本；跳过的测试不构成真实数据验证证据。
正常启动桌面 UI 前，请移除环境中的 `QT_QPA_PLATFORM` 设置。

## 已知限制

- Cine 验证主要覆盖现有单色 Phantom 样本，其他变体仍需验证。
- TIME64 状态与未解决的时间不一致需要结合实验复核。
- 魔棒和标注包导出目前要求 uint8 灰度图；魔棒拒绝带孔或退化轮廓，尚无 mask 画笔编辑器。
- 标注包只有实际包含的帧，不代表完整 Cine。
- 返回的帧状态与包模板候选会保留，但专用比较/采用 UI 尚未实现。
- 校验和用于检测损坏，不认证审阅者身份；协作是离线流程，不是实时同步。
  运行时配置仍依赖源码检出目录。

## 后续计划

以下为规划方向，不承诺发布日期：

- Windows 可分发程序/安装器与 `.dvapkg` 文件关联。
- 数据集导出与 prediction import/provider 集成。
- 分割基线、测量提取及基于 TIME64 的时序事件逻辑。

## 贡献者

<div align="center">
  <a href="https://github.com/xiaorouqiuzi-ai">
    <img src="https://github.com/xiaorouqiuzi-ai.png?size=120" width="84" alt="xiaorouqiuzi-ai">
    <br>
    <sub><b>@xiaorouqiuzi-ai</b></sub>
  </a>
  <br>
  仓库拥有者（Repository Owner）
  <br><br>
  <a href="https://github.com/BrunelXian">
    <img src="https://github.com/BrunelXian.png?size=120" width="84" alt="BrunelXian">
    <br>
    <sub><b>@BrunelXian</b></sub>
  </a>
  <br>
  合作者（Collaborator）
</div>

桌面 UI 名称为 **Droplet Annotation Workstation**，属于 Droplet Vision 项目。
[GitHub 仓库](https://github.com/xiaorouqiuzi-ai/droplet--vision)。

## 许可证

Droplet Vision 源代码使用 [BSD-3-Clause](LICENSE) 许可证。
第三方库与未来模型运行时仍适用各自许可证。
分发打包后的二进制程序时，应检查随附依赖的许可证；本项目不会将其重新授权为 BSD。

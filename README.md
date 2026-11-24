# Park Behavior Mapping

把**手绘的公园人群行为注记图**变成结构化数据与出版级图表。

> **方法与出处**
> 本项目的标注方法——`人数-性别-活动` 三编码体系、以"两个交点之间为一段路"划分路段、按段汇总人数与停留特征——由 **Hon Sytsi** 提出，用于**风景园林**专业的建成环境行为观察（使用后评价 / post-occupancy evaluation）。
> 本仓库是该方法的数字化实现：标注在浏览器里完成，统计与出图自动生成。
> 若在论文或设计研究中使用该方法，请引用 Hon Sytsi 的原始工作（见 [CITATION.cff](CITATION.cff)）。

> 扫描一张手绘平面图 → 在网页里圈注记、画路段 → 半自动读出 `人数-性别-活动` 编码 → 按路段汇总 → 输出统计图与 CSV。

这是风景园林专业的现场调研工具：一张平面图、一支笔记录一天的人流，回来却要花几天转录成表格。这个仓库把那几天压缩到一两个小时——**方法不变，只是把誊抄和汇总交给机器**。

![workflow](docs/workflow.svg)

## 它解决什么

现场注记通常长这样：一张手绘平面图，路口写着 `10-2-6`，含义是「10 人、女性为主、手机」。

问题是：

- **它不可计算**。想统计"哪段路停留最久"，只能靠眼睛数。
- **OCR 读不出来**。字高约 12×20 px，被箭头和引线压着。实测：TrOCR 把 `2-3-1` 读成 `girls . I`，EasyOCR 切成 `4 | 4 | 72 | 3`，PP-OCRv4 把 `2-1-5` 读成 `J-2J`。
- **框和路段对不上**。一个注记框切成了两半，两个注记并成了一个框。

这个工具的三条对策：**给框加旋转矩形约束**、**用白名单约束 CTC 解码**、**用人工确认兜底**。

## 组成

| 部分 | 作用 |
|---|---|
| `python/build_tool.py` | 把扫描图打包成**单文件网页**（图片 base64 内嵌，离线可用） |
| 标注网页 | 画路段（沿笔迹自动寻路）、拉框、自动吸附、读数、导出 JSON |
| `python/ocr_read.py` | PP-OCRv4 + **白名单约束解码**，对每个框给出建议值 |
| `python/render_figure.py` | 生成线稿版统计图 + 分段 CSV |
| `skill/SKILL.md` | Agent Skill：把整套流程（含踩坑清单）交给 AI 执行 |

## 快速开始

```bash
pip install -r python/requirements.txt
# OCR 引擎单独装，避免污染主环境
pip install --target ./ocr rapidocr-onnxruntime

# 0) 没有素材？先合成一张演示图
python demo/make_demo.py

# 1) 生成标注网页
python python/build_tool.py --images demo/park1.jpg --labels 演示公园 --out demo/tool.html

# 2) 浏览器打开 demo/tool.html，画完导出 标注结果.json

# 3) 读数字（给出建议值）
PBM_OCR_PATH=./ocr python python/ocr_read.py --export 标注结果.json --images i1=demo/park1.jpg

# 4) 出图
python python/render_figure.py --export 标注结果.json --key i1 \
  --image demo/park1.jpg --out 图1.png --csv 统计.csv
```

## 编码约定

注记 `人数-性别-活动`：

| 位 | 取值 | 含义 |
|---|---|---|
| 人数 | 1–2 位 | 该注记代表的人数 |
| 性别 | 1 / 2 / 3 | 男 / 女 / 男女均衡 |
| 活动 | 1–13 | 步行 跑步 骑行 坐憩 社交 亲子 锻炼 遛狗 野餐 手机 拍照 文化 其他 |

停留等级不单独标注，由活动推导：`1–3 → 路过`、`8/11 → 短暂停留`、`4–7/9/10/12/13 → 持续活动`。

**路段** = 两个交点之间的一段路，一段可挂多个注记。

## 为什么需要人工确认

约束解码把识别率从不可用提到约 45%。剩下的靠人，但人只需要**确认**而不是**输入**。

这是有意为之的取舍：这类手写体在任何现成模型上都读不到 90%，与其给出 55 个错误值让人逐个改，不如给出 45 个对的 + 一堆空白。

## 目录

```
python/     三个命令行工具（打包 / 识别 / 出图）
skill/      Agent Skill（交给 AI 执行）
demo/       合成演示数据（无需真实素材即可试跑）
docs/       流程图与工作流详解
```

## 引用

```bibtex
@software{park_behavior_mapping,
  title  = {Park Behavior Mapping: 手绘行为注记图的分段统计工具},
  author = {Sytsi, Hon and Cat0ntheRoof},
  year   = {2026},
  note   = {标注方法由 Hon Sytsi 提出；本仓库为其数字化实现},
  url    = {https://github.com/Cat0ntheRoof/park-behavior-mapping}
}
```

## 关于数据

本仓库**不包含任何真实调研数据**：`demo/park1.jpg` 与 `demo/truth.json` 由 `demo/make_demo.py` 程序合成，仅用于跑通流程。
实际使用的扫描图与标注结果请自行保管，不要提交到公开仓库。

## 许可

代码 MIT。**标注方法的知识产权归 Hon Sytsi**，本仓库仅提供实现；方法本身的使用请遵循其原始发表的要求。

OCR 使用 [RapidOCR](https://github.com/RapidAI/RapidOCR) 打包的 PP-OCRv4 ONNX 模型（Apache-2.0）。

# 工作流详解

## 0. 准备

```bash
pip install -r python/requirements.txt
pip install --target ./ocr rapidocr-onnxruntime     # OCR 引擎单独装
export PBM_OCR_PATH=./ocr                            # Windows: set PBM_OCR_PATH=.\ocr
```

标注网页本身**不需要 Python**：`build_tool.py` 产出的 HTML 是自包含的，发给同事也能用。

## 1. 打包标注网页

```bash
python python/build_tool.py \
  --images scan/park1.jpg scan/park2.jpg \
  --labels 园A 园B \
  --out 工作台/tool.html
```

可选参数：

| 参数 | 作用 |
|---|---|
| `--keys` | 内部标识（默认 i1、i2…），导出 JSON 用它当 key |
| `--boxes` | 预置框 JSON，省去手拉 |
| `--ink` | 预先生成的掩膜 PNG，用于"沿笔迹吸附" |

打开 HTML 后所有操作都在浏览器里，数据存在 localStorage，刷新不丢。

## 2. 标注

### 2.1 画路段

按 `S` → 点起点 → 点终点。中间会自动沿手绘笔迹寻路（A\*，墨迹代价 1、空白 16），拐弯会跟着走。

- 拐得太偏？关掉工具栏的"沿路吸附"退回直线；
- 两条路挨得太近导致串线？把起止点挪开一点重画；
- 画长了可以"合并"或删掉重画。

### 2.2 画框 / 检测

- `N` 拖一个矩形，再拖顶部圆点旋转；
- `D` 框选一片区域跑本地检测（笔画聚类），整图检测在工具栏；
- 检测结果是绿色候选框，可删可改。

### 2.3 挂路段

三种方式：

1. 点路段 → 点框 → 「挂到选中路段」（推荐，带 manual 标记，不会被自动吸附覆盖）；
2. 选中框 → 下拉选路段；
3. 拖动框，松开时自动吸到最近路段（140px 内）。

### 2.4 读数

按 `R` 进读数模式：画面放大对准当前框，底部三个输入框（人数 / 性别 / 活动）。

- 填完人数按 `空格` 跳下一项；性别填 1/2/3 自动跳到活动；
- 活动填满或停 1.4 秒自动提交并跳下一个；
- `←` `→` 前后翻，`Esc` 退出。

校验收紧：性别只允许 1/2/3，越界会红框报"性别码非法"，不保存。

### 2.5 导出

「导出 JSON」→ 得到 `{i1: {boxes, segs, deleted}, i2: …}`。

## 3. 机器初读

```bash
python python/ocr_read.py \
  --export 标注结果.json \
  --images i1=scan/park1.jpg i2=scan/park2.jpg \
  --out work/
```

产出 `work/suggestions.json`（key → {box_id: 编码}）和 `suggestions.csv`。

回到网页点「导入建议值」，读数卡片会显示"模型建议 …[采用]"，点一下即可填入。

## 4. 出图

```bash
python python/render_figure.py \
  --export 标注结果.json --key i1 \
  --image scan/park1.jpg \
  --out 图1.png --csv 统计.csv \
  --title "图 1  XX 公园" --subtitle "（……）"
```

生成的图包含：线稿底图（手写已擦除）、绿色路段带、每段 `人数-性别-停留` 标注、右侧统计表。

## 常见问题

**识别率低（约 45%）**
正常。数字只有十几个像素高，还被箭头压着。提高扫描分辨率（300dpi 以上）能明显改善；再不行就手工敲，读数模式一个框 3–5 秒。

**角度导致全读错**
框的角度必须是 `[-90°, 90°)`。导出里是 `[0,180)`，`>90°` 的框要先减 180 再旋转裁剪，否则文字上下颠倒。工具里已处理，自己写脚本要注意。

**路段统计人数对不上**
检查：① 是否有框没挂路段（图上显示红框）；② 编码是否合法；③ 男女均衡三列相加是否等于总数。

**中文乱码**
绘图用了 `msyhbd.ttc` / `msyh.ttc`（Windows 自带）。macOS 换成 `PingFang.ttc`，Linux 换 `NotoSansCJK`，改 `render_figure.py` 顶部的 `F_B` / `F_R`。

# 矢量输出（SVG / 转曲 PDF）

本仓库在原始 Silicon Canvas 上增加了一个**矢量后端**：同一套布局、避障布线和字号测量结果直接输出 SVG，不再只产出给图片生成模型用的 `guide.png`。适用于论文、技术文档和任何需要可编辑矢量图的场合。

改动原则是最小侵入：绘图调用不变，只替换接收绘图调用的后端（`src/silicon_canvas/svg_backend.py`）。

## 命令行

```bash
# 例：按论文单栏宽度生成 SVG（85 mm，正文 6 pt）
python -m silicon_canvas.svg_backend examples/soc.json out/figure.svg --width-mm 85 --body-pt 6

# 或指定完整 settings
python - <<'PY'
import json
from silicon_canvas import engine, svg_backend
payload = json.load(open("examples/gpu.json"))
result = engine.compile_manual({**payload, "settings": {"scene": "auto", "target_width_mm": 85, "body_pt": 8}})
figure = next(f for f in result["figures"] if f["id"] == result["selected_figure_id"])
open("out/figure.svg", "wb").write(svg_backend.render(result, figure))
PY
```

## 文档宽度与字号

`target_width_mm` 与 `body_pt` 覆盖场景默认值（架构图默认 160 mm / 9 pt），只作用于主图：

- SVG 根元素写成 `width="85mm"`，`viewBox` 保持像素坐标，因此 1 个 viewBox 单位仍是确定的物理尺寸。
- 排版预检使用同一物理宽度重新测量；**内容放不下时不会硬塞**——编译会退回 `text-only`，`svg_backend.render` 返回 `None`，需要减少模块或加宽画幅。
- 场景最小值（concept 240 mm、flow 200 mm）在显式指定宽度时不再生效。

## 导出转曲 PDF

与论文插图目录使用的三步流程相同，文字转路径、图形保持矢量：

```bash
./scripts/export_svg_pdf.sh out/figure.svg out/pdf_outlined/figure.pdf
```

脚本等价于：

```bash
rsvg-convert -f pdf -o input.pdf figure.svg
pdftocairo -svg input.pdf outlined.svg
rsvg-convert --dpi-x 72 --dpi-y 72 -f pdf -o figure.pdf outlined.svg
```

校验：`pdfinfo` 的页面宽度应等于 `target_width_mm`（85 mm = 240.945 pt），`pdffonts` 不应列出字体。脚本会自动打印页面尺寸并在仍有字体时告警。

## MCP 中的位置

- `silicon_compile` 的返回新增 `vector_figure`：`{uri, path, role: "final_vector", note}`。
- 编译产物目录同时写入 `<figure_id>.figure.svg`，资源地址 `silicon://artifacts/<id>/figures/<figure_id>/figure.svg`。
- 导出 ZIP 内含 `figures/<figure_id>/figure.svg`。
- 有矢量图时 `next_step` 会明确说明**不再需要图片生成模型**。

## 适用范围

| 视图 | 矢量输出 |
| --- | --- |
| 系统架构、所有权图（`publication`） | 支持，几何与 `guide.png` 完全一致 |
| 数据流、实现细节（`structure_scene`） | 支持 |
| 状态机、时序（`behavior_guide`） | 支持 |
| 算法算子依赖图（`algorithm_flow_plan`） | **不支持**：该视图只有文字计划，没有测量几何，返回 `None` |
| 商业产品渲染（`product_render`） | 仍是 prompt 驱动；材质、光照、透视不属于矢量表达 |

## 已知边界

- 路线标签放不下时会被记为 `deferred_labels` 而不是硬塞；矢量模式下这些文字不会出现在图中，需在图注补全。
- SVG 只引用 `font-family`，换行宽度是按 Noto Sans CJK 实测的；导出转曲前必须保证该字体可用（仓库内已附带），否则换行位置会变。
- 文字在 SVG 中是可编辑的 `<text>`，转曲只发生在导出的 PDF 上。

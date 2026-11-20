# SCA 2.2.7 实测笔记

> 本文件是后面所有任务写 SCA 代码的依据。每一节的代码都在 `scripts/probe_sca.py`、`scripts/probe_sca_cheatsheet.py` 里实际跑通过，
> 完整输出存在 `docs/sca-probe-output.txt`（Windows 11、Python 3.13.7、simplecadapi 2.2.7、2026-11-09）。
> 笔记里没有的写法，先写探测代码跑通，再补进这里，然后才能用。

## 0. 总览：后面任务要用的取法（速查）

| 要什么 | 怎么取 |
|---|---|
| 运行 notebook | `from simplecadapi.runtime import run_notebook`；`run = run_notebook(path, cache=False, timeout=60)` |
| 产品实体 | `run.product.body`（`Solid`）；`run.definition` 用来导出 |
| 参数值 | `float(run.values["w"])`（参数是 `Var`，`float()` 可用；个数参数是普通整数） |
| 包围盒、体积、有效性、个数 | `brep.inspect_shape_rbrepinspection(body.wrapped)`，见第 4、7 节 |
| 选面选边 | `ql.faces()` / `ql.edges()` + `.where(...)` + `.resolve(body)`（返回 Python 列表），见第 5 节 |
| 点在不在材料里、最小距离 | OCP 的 `BRepClass3d_SolidClassifier`、`BRepExtrema_DistShapeShape`，见第 14 节 |
| 截图 | `scad.render_screenshot_rpath(body, str(png), view="iso")` |
| 导出 STEP | `cap = scad.capture(run.definition, pkg_path)`，再 `exporter.export_product_package_to_step(cap.package, step_path)` |
| 出错的特征 | 在 traceback 里找 `__marimo__cell_` 帧，用 `linecache` 读 cell 源码里的特征注释，见第 9 节 |
| API 文档 | 包内 `skill/resources/docs/skill/references/docs/api/<函数名>.md`，见第 10 节 |
| `sca` 命令 | `Path(sys.executable).parent / "sca.exe"`（`shutil.which("sca")` 找不到），见第 11 节 |

## 1. 安装情况

- Python 3.13.7，`python -m venv .venv` 后 `.venv\Scripts\python -m pip install -e ".[dev]"` 一次成功，**`verify` 附加包能装**（带来 `cadquery-ocp-novtk`、`cadquery-ocp-proxy`，`from OCP.Bnd import Bnd_Box` 可用）。所以依赖保持 `simplecadapi[editor,verify]==2.2.7`，不需要改。
- 装到的主要版本：simplecadapi 2.2.7、marimo 0.25.2、openai 3.46.0、PyYAML 6.0.3、pytest 9.2.0、numpy 2.5.4。
- `simplecadapi.__version__` 不存在，取版本用 `importlib.metadata.version("simplecadapi")`。
- 安装时 setuptools 会提示“工作目录里有和包同名的文件夹”，是可编辑安装的常规提示，不影响。
- **SCA 会在当前目录下写 `.simplecad/diagnostics/*.png`（报错时的诊断图）**。所以子进程的工作目录必须是临时目录；探测脚本也先 `chdir` 到临时目录。项目 `.gitignore` 里已加 `.simplecad/`。

## 2. 中文路径

实测（脚本第 13 项，目录 `...\Temp\cad-probe-xxx\中文目录`）：

| 操作 | 结果 |
|---|---|
| `render_screenshot_rpath` 把 PNG 写进中文目录 | 成功（`view="iso"`、`(30, 45)`、`"auto"` 都行） |
| `scad.capture(...)` 写 `.scadpkg` + `export_product_package_to_step` 写 STEP 进中文目录 | 成功，STEP 19630 字节 |
| `run_notebook` 运行**放在中文目录里**、文件名是英文的 notebook | 成功 |
| `run_notebook` 运行**文件名是中文**的 notebook | **失败**：`ArtifactValidationError: path_invalid at /source_file/display_path: artifact paths must be ASCII` |

结论：
- notebook 文件名一律用英文（`model.py`），目录是中文没问题。
- 计划里的做法（在英文临时目录里运行，产物复制回会话目录）本来就稳妥，保持不变。
- `sca` 命令在中文目录下（Task 11 补测，目录 `...\会话测试\`，里面有 `model.py` 和 `versions\v1\model.py`）：`sca ls .` 把两个 notebook 都列出来（`error: null`）；`sca run model.py` 正常运行并返回 `definition_kind: single_solid`；`sca edit --no-browser --port 8765 <中文目录>` 能启动，访问 `http://127.0.0.1:8765/` 返回 200（页面标题 `SimpleCAD Studio`）。所以 `/view` 可以直接对会话目录用 `sca edit`，不需要改成英文路径。（没有用浏览器逐个点开 notebook 验证编辑器里的运行效果，留给 Task 13 联调时人工看一眼。）

## 3. 参数与单位

notebook 骨架（`with app.setup` 里导入，所有 cell 都能直接用 `scad`、`ql`、`math`）：

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["simplecadapi"]
#
# [tool.simplecadapi]
# id = "model"
# ///
import marimo

app = marimo.App()

with app.setup:
    import simplecadapi as scad
    from simplecadapi import ql
    import math


@app.cell
def _():
    # ---- params ----
    a = scad.var("a", 30, unit="deg")
    h = scad.var("h", 36, unit="mm")
    n = 6
    r = scad.var("r", 5, unit="mm")
    t = scad.var("t", 8, unit="mm")
    w = scad.var("w", 60, unit="mm")
    return a, h, n, r, t, w


@app.cell
def _(h, t, w):
    # ---- feature: plate (build) ----
    plate = scad.make_box_rsolid(width=w, height=h, depth=t, bottom_face_center=(0, 0, 0))
    return (plate,)


@app.cell
def _(plate, r, t):
    # ---- feature: hole (subtract) ----
    _tool = scad.make_cylinder_rsolid(radius=r, height=t + 2, bottom_face_center=(0, 0, -1))
    hole = scad.cut_rsolid(plate, _tool)
    return (hole,)


@app.cell
def _(hole):
    model = scad.Part(part_id="model", body=hole)
    return (model,)
```

实测结果：
- 运行 `run_notebook(path, cache=False)` 成功，`run.product` 是 `Part`，`run.cells` 5 个都是 `ran`。一次简单运行约 0.1~1 秒。
- 产品是“变量的 id 等于 notebook id（`model`）的那个 `Part`”，变量名也叫 `model`。
- `scad.var("w", 60, unit="mm")` 得到 `Var`；`float(run.values["w"])` → `60.0`；角度 `scad.var("a", 30, unit="deg")` → `float(a)` = `30.0`。
- **角度单位写 `"deg"`**（正确写法）；长度写 `"mm"`；`"degree"`、`"degrees"`、`"°"` 也被接受，但统一用 `"deg"`。`"rad"` 会被换算成度（1 rad → 57.29…）。
- 个数这类无量纲参数写成**普通整数**（如 `n = 6`），不用 `scad.var`。`range(n)`、`count=n` 都能直接用。
- **Var 参与运算能直接传进函数**，都实测通过，不需要包 `float()`：
  - `height=t + 2`、`radius=hole_d / 2`、`bottom_face_center=(base_w / 2, base_d / 2, 0)`；
  - `make_polyline_rwire(points=[(0, 0, 0), (base_d, 0, 0), (0, 0, rib_h)])`，点里直接放 Var；
  - `math.tan(math.radians(tilt_deg))`（`tilt_deg` 是 Var）；
  - `rotate_shape(shape=..., angle=tilt_deg, ...)`；
  - `ql.prop("geom.center.z", ">=", base_t - 0.1)`（值里放 Var 表达式也行）。
  - 要注意的只有：`bool(Var)` / `if R:` 报错，要写成比较 `if R > 0:`。
- 参数 cell 里的变量名和特征变量名不能重名（marimo 规定一个名字只能有一个定义的 cell），Task 3 要拦。
- 临时变量用 `_` 开头（如 `_tool`），属于本 cell，别的 cell 读不到。

## 4. 包围盒、体积

SDK 的 `Solid` 上没有 bbox 方法（`bounding_box`、`get_bounding_box`、`bbox` 都不存在）。用检视函数，一次拿到包围盒、体积、有效性和个数：

```python
from simplecadapi.inspect import brep

body = run.product.body
i = brep.inspect_shape_rbrepinspection(body.wrapped)
i.bounding_box   # [xmin, ymin, zmin, xmax, ymax, zmax]，实测 [-30.0, -18.0, 0.0, 30.0, 18.0, 8.0]，是紧的
i.volume         # 16651.68…，和 60*36*8 - pi*25*8 = 16651.68 一致
body.get_volume()  # 同样可用，结果一样
```

- 另一种：OCP 的 `Bnd_Box` + `BRepBndLib.Add_s(body.wrapped, bb)`，`bb.Get()` 得到 `(xmin, ymin, zmin, xmax, ymax, zmax)`，但每边会多出 1e-7 的缝隙（实测 `(-30.0000001, -18.0000001, -1e-07, 30.0000001, ...)`）。**统一用检视函数**，不用 OCP 的包围盒。
- 某个方向的尺寸 = `bounding_box[axis+3] - bounding_box[axis]`。

## 5. 面和边的属性

```python
from simplecadapi import ql

body = run.product.body
cyl = ql.faces().where(ql.prop("geom.type", "==", "CYLINDER")).resolve(body)   # Python 列表
f = cyl[0]
f.get_center()      # Vec3，.x .y .z，.to_tuple() -> (1.7e-15, -2.1e-16, 4.0)
f.get_area()        # 251.3274，和 2*pi*5*8 一致
f.get_normal_at()   # 默认取面中间，Vec3；平面的是朝材料外的法向
e = ql.edges().resolve(body)[0]
e.get_length(); e.get_center()
```

实测：
- 长方体减一个通孔：`ql.faces().resolve(body)` 7 个面，`ql.edges().resolve(body)` 15 条边（13 条 `LINE`、2 条 `CIRCLE`）。
- 顶面：`ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99))` → 1 个，`center.z = 8`，`get_normal_at() = (0, 0, 1)`；底面用 `geom.normal.z <= -0.99` → 1 个，`center.z = 0`，法向 `(0, 0, -1)`。**平面法向都是朝材料外**。
- **圆柱面也有 `geom.normal.*`**：`geom.normal.z >= -1e9` 命中 7 个面（含圆柱面）。所以按法向选面时**必须同时限定 `geom.type == "PLANE"`**。
- 可用的属性：面 `geom.type`（`PLANE`、`CYLINDER`）、`geom.center.x/y/z`、`geom.normal.x/y/z`、`geom.area`；边 `geom.type`（`LINE`、`CIRCLE`）、`geom.center.*`、`geom.length`。
- **没有 `geom.radius`、`geom.diameter`、`geom.axis.*`**：查询不报错，只是一个也选不到（命中 0 个）。要按孔径选圆柱面，就用面积：侧面积 = π × 直径 × 高度；或者用圆边的长度（`2πr`）。
- 圆边长度：`[31.4159, 31.4159]`（= 2π×5）。
- `get_center()` 的坐标会有 1e-15 的浮点噪声，选坐标用范围，不用等号。
- `exactly(n)` 不满足时抛 `SimpleCADError`，见第 13 节。

## 6. 有效性、实体个数

`brep.inspect_shape_rbrepinspection(body.wrapped)` 的字段（`BRepInspection`）：

| 字段 | 实测值（带孔板） | 用途 |
|---|---|---|
| `valid` | `True` | 实体有效检查 |
| `counts["solid"]` | `1` | 实体个数（只有一个实体检查） |
| `counts["unique_faces"]` / `counts["unique_edges"]` | `7` / `15` | 面数、边数 |
| `volume` | `16651.68` | 体积 |
| `surface_area` | `5950.25` | 表面积 |
| `bounding_box` | 6 个数 | 包围盒 |
| `surface_type_counts` | `{'Plane': 6, 'Cylinder': 1}` | 面类型统计 |
| `edge_type_counts` | `{'Line': 13, 'Circle': 2}` | 边类型统计 |

补充：把板整个切成两块的 `cut_rsolid` 会直接抛 `SimpleCADError: Failed to compute the boolean cut.`，所以 notebook 里产品基本总是一个实体；`single_solid` 检查仍然按 `counts["solid"]` 做。

## 7. 截图

```python
png = scad.render_screenshot_rpath(body, str(out_dir / "view.png"), view="iso")
```

- 返回值是 PNG 路径字符串。`view="iso"` 实测成功（85 KB）；`view=(30, 45)`（仰角、方位角）和 `view="auto"`（四视图拼图）也成功。
- 交付截图用 `view="iso"` 单视图；`"auto"` 是四视图，可作备选。
- 中文目录也能写（见第 2 节）。
- 渲染在独立的子进程里完成，不会拖垮调用方。

## 8. STEP 导出

```python
from simplecadapi import exporter

cap = scad.capture(run.definition, pkg_path)          # 注意是 run.definition，不是 run.product
exporter.export_product_package_to_step(cap.package, step_path)
```

- `scad.capture(run.product, ...)` 会报 `TypeError: result must be a PartDefinition, ...`，必须传 `run.definition`。
- `export_product_package_to_step(cap.package, step)` 和 `export_product_package_to_step(pkg_path, step)`（直接传 `.scadpkg` 路径）都成功，STEP 19630 字节，返回 `ProductSTEPExportReport`（有 `output_path`、`schema`、`occurrence_count` 等字段）。
- 英文目录和中文目录都成功。

## 9. 报错定位（哪个特征出错）

`run_notebook` 把 cell 里的异常**原样抛出**（`ZeroDivisionError`、`NameError`、`SimpleCADError` 等）。traceback 里：

```text
帧: runner.py ... script_runner.py:266 run
帧: __marimo__cell_11edcfd8-vblA_.py 行号=2 函数=<module>      <- 用户 cell 里的那一帧
```

- 帧文件不是 notebook 本身，是 marimo 编译 cell 时生成的临时文件 `__marimo__cell_<哈希>.py`，**行号是 cell 内部的行号**（第 1 行是 `# ---- feature: boom (subtract) ----`），不能和 notebook 文件的行号对照，所以不能用 `cell_lines` 反查。
- 可用的方法：遍历 `traceback.extract_tb(e.__traceback__)`，取最后一个文件名含 `__marimo__cell_` 的帧，用 `linecache.getlines(filename)` 读 cell 源码，正则匹配第一行里的特征注释：

```python
import linecache, re, traceback

def slug_of_failed_cell(exc):
    slug = None
    for f in traceback.extract_tb(exc.__traceback__):
        if "__marimo__cell_" in f.filename:
            src = "".join(linecache.getlines(f.filename)[:3])
            m = re.search(r"# ---- feature: ([a-z][a-z0-9-]*) \(", src)
            slug = m.group(1) if m else None      # 参数 cell、产品 cell 里出错时是 None
    return slug
```

实测：故意在 `boom` 特征里写 `1 / 0`，得到 `slug='boom'`。
- 参数 cell 和最后的产品 cell 没有特征注释，出错时得到 `None`（对应 build 返回里 `feature: null`）。
- 超时：`run_notebook(..., timeout=3)` 对死循环在 3.02 秒后抛 `TimeoutError: the notebook did not finish in 3s ...`；但仍然要在父进程里设子进程超时作为兜底。

## 10. API 文档位置

```text
<site-packages>/simplecadapi/skill/resources/docs/skill/references/docs/api/<函数名>.md    358 个
.../references/docs/core/   .../references/docs/stdlib/   .../references/docs/guides/
.../references/ql-playbook.md      选面选边的实战写法（含 QL 属性表）
```

- 取路径：`Path(simplecadapi.__file__).parent / "skill" / "resources" / "docs" / "skill" / "references" / "docs" / "api"`。
- 每个函数一个文件，如 `make_box_rsolid.md`；内容有 `API Definition`（函数签名）、`Description`、`Parameters`。`api_help` 工具直接读这些文件。
- 文件名就是函数名；QL 里的函数也有：`prop.md`、`and_.md`。

## 11. sca 命令

- `shutil.which("sca")` 返回 `None`（虚拟环境的 `Scripts` 目录没在 PATH 上）。
- 要用与 python 同目录的：`Path(sys.executable).parent / "sca.exe"`，实测存在：`.venv\Scripts\sca.exe`。
- `sca edit [--host HOST] [--port PORT] [--no-browser] [workspace]`：打开代码优先编辑器，`workspace` 是放 notebook 的目录或单个 notebook；默认会自动打开浏览器，`--no-browser` 只启动服务。会话目录里的 `model.py` 和各版本的 `versions\vN\model.py` 都会被当作 notebook 列出来（见第 2 节的实测）。
- 其他子命令：`run`、`ls`、`params`、`export`、`snapshot`、`cell` 等。

## 12. 速查表条目实测（第 14 项）

下面每条都在 notebook 里以 `Var` 参数跑通，括号里是用包围盒验证的结果。参数名：`base_w=60, base_d=40, base_t=8, hole_d=10, tilt_deg=65 (deg), n_holes=6, rib_h=30, rib_t=5, pcd=40, flange_od=100, bore_d=30, boss_d=55, flange_t=10, total_h=30`。

**函数签名（来自包内文档）**
```text
make_box_rsolid(width, height, depth, bottom_face_center=(0, 0, 0), *, ...tags)
make_cylinder_rsolid(radius, height, bottom_face_center=(0, 0, 0), axis=(0, 0, 1), *, ...tags)
make_rectangle_rface(width, height, center=(0, 0, 0), normal=(0, 0, 1), *, ...)
make_circle_rface(center, radius, normal=(0, 0, 1), *, ...)
make_polyline_rwire(points, closed=False)
make_face_from_wire_rface(wire, normal=(0, 0, 1), *, ...)
extrude_rsolid(profile, direction, distance, *, ...)
revolve_rsolid(profile, axis=(0, 0, 1), angle=360, origin=(0, 0, 0), *, ...)
union_rsolid(*solids, clean=True, glue=False, tol=None, tracking_policy='full')
cut_rsolid(*solids, skip_non_intersecting=True, tracking_policy='full')     # 第一个是被减的，其余是工具体
intersect_rsolid(*solids)
translate_shape(shape, vector)
rotate_shape(shape, angle, axis=(0, 0, 1), origin=(0, 0, 0))                # angle 单位是度
radial_pattern_rsolidlist(shape, center, axis, count, total_rotation_angle)
linear_pattern_rsolidlist(shape, direction, count, spacing)
fillet_rsolid(solid, edges, radius, *, ...)
chamfer_rsolid(solid, edges, distance, *, angle=None, reference_direction=None, ...)
```

### 12.1 基本体
```python
base = scad.make_box_rsolid(width=base_w, height=base_d, depth=base_t, bottom_face_center=(0, 0, 0))
```
- `width` 沿 x，`height` 沿 y，`depth` 沿 z。`bottom_face_center` 是**底面中心**（不是角点）：x、y 方向居中，从该点向 +z 长高。
- 结果包围盒 `[-30, -20, 0, 30, 20, 8]`。要角点在原点：`bottom_face_center=(base_w / 2, base_d / 2, 0)` → `[0, 0, 0, 60, 40, 8]`。
```python
post = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t, bottom_face_center=(0, 0, 0))
```
- 圆柱默认沿 +z，`bottom_face_center` 是底面圆心 → `[-5, -5, 0, 5, 5, 8]`。横放：`axis=(1, 0, 0)`，`bottom_face_center=(0, 0, 5)`，`height=20` → `[0, -5, 0, 20, 5, 10]`（沿 +x 伸出 20）。

### 12.2 草图轮廓与拉伸
```python
_profile = scad.make_rectangle_rface(width=base_w, height=base_d, center=(0, 0, 0), normal=(0, 0, 1))
plate = scad.extrude_rsolid(profile=_profile, direction=(0, 0, 1), distance=base_t)   # [-30,-20,0, 30,20,8]
```
```python
_profile = scad.make_circle_rface(center=(0, 0, 0), radius=hole_d / 2, normal=(0, 0, 1))
disc = scad.extrude_rsolid(profile=_profile, direction=(0, 0, 1), distance=base_t)    # [-5,-5,0, 5,5,8]
```
- 矩形的 `width` 沿 x、`height` 沿 y，`center` 是矩形中心。拉伸沿 `direction` 方向走 `distance`。

### 12.3 多边形截面拉伸（XZ 平面）
```python
_wire = scad.make_polyline_rwire(points=[(0, 0, 0), (base_d, 0, 0), (0, 0, rib_h)], closed=True)
_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0))
rib = scad.extrude_rsolid(profile=_profile, direction=(0, 1, 0), distance=rib_t)
```
- 结果包围盒 `[0, 0, 0, 40, 5, 30]`：截面在 XZ 平面（y=0），沿 +y 拉伸厚度 `rib_t`。
- **法向要和点的顺序一致，否则会在 stderr 打印 `Warning: the normal of the created face is opposite to the expected direction`**（结果仍然正确）。规则：点在 XZ 平面里按“x 向右、z 向上”看是**逆时针**时，用 `normal=(0, -1, 0)`；顺时针用 `(0, 1, 0)`。
- 用角度算顶点，直接写 `_rise = base_d * math.tan(math.radians(tilt_deg))`，`tilt_deg` 是 Var 也可以：65° 时 `_rise` = 85.78，包围盒 z 到 85.780277。

### 12.4 旋转体（法兰盘）
```python
_pts = [(bore_d / 2, 0, 0), (flange_od / 2, 0, 0), (flange_od / 2, 0, flange_t),
        (boss_d / 2, 0, flange_t), (boss_d / 2, 0, total_h), (bore_d / 2, 0, total_h)]
_wire = scad.make_polyline_rwire(points=_pts, closed=True)
_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0))
body = scad.revolve_rsolid(profile=_profile, axis=(0, 0, 1), angle=360, origin=(0, 0, 0))
```
- 截面画在 XZ 平面（x 是半径，z 是高度），绕 z 轴转一圈。包围盒 `[-50, -50, 0, 50, 50, 30]`，面型 3 个平面 + 3 个圆柱面（中心孔、凸台外圆、底盘外圆）。

### 12.5 布尔运算
```python
joined = scad.union_rsolid(base, post)                       # [-30,-20,0, 30,20,28]
holes  = scad.cut_rsolid(base, _h1, _h2)                     # 一次减两个工具体，圆柱面 2 个
cap    = scad.intersect_rsolid(base, _box)                   # [-10,-20,0, 10,20,8]
```
- `cut_rsolid(被减体, 工具1, 工具2, ...)`：一次可以减多个，也可以传工具体列表（嵌套序列会被展开）。
- **工具体完全没碰到主体时，默认参数下不报错，悄悄跳过**（结果和原来一样，体积不变）。想让它报错就加 `skip_non_intersecting=False`。
- 相切的两个工具体（如间距正好等于直径的相邻圆柱）会让 `cut_rsolid` 报 `Failed to compute the boolean cut`，工具体之间要留缝或干脆重叠。
- **`skip_non_intersecting=False` 在所有减孔写法里都能用**（Task 10 补测）：两个工具体 `cut_rsolid(base, _h1, _h2, skip_non_intersecting=False)` → 2 个圆柱面；圆周阵列列表 → 6 个；线性阵列列表 → 3 个；循环生成的 Python 列表 → 6 个。工具体确实穿过主体时结果和不加参数完全一样（体积 17943.36 / 15872.31 / 17315.04 / 16787.26），只是工具体没碰到时会报错而不是悄悄跳过。所以速查表里减孔一律带这个参数。

### 12.6 移动与旋转
```python
moved  = scad.translate_shape(shape=base, vector=(10, 0, 5))                                   # [-20,-20,5, 40,20,13]
turned = scad.rotate_shape(shape=base, angle=90, axis=(0, 0, 1), origin=(0, 0, 0))              # [-20,-30,0, 20,30,8]
```
- `angle` 单位是度，绕 `axis` 通过 `origin` 的轴旋转，右手定则（绕 z 转 90° 后 60×40 变成 40×60）。`angle=tilt_deg`（Var）也行。

### 12.7 阵列
```python
_hole = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t + 2, bottom_face_center=(pcd / 2, 0, -1))
_holes = scad.radial_pattern_rsolidlist(shape=_hole, center=(0, 0, 0), axis=(0, 0, 1), count=n_holes, total_rotation_angle=360)
bolt_holes = scad.cut_rsolid(base, _holes)
```
- 圆周阵列：`count` 是**总个数（含原件）**，`n_holes=6` 切出 6 个圆柱面；`total_rotation_angle=360` 时均布。
```python
_holes = scad.linear_pattern_rsolidlist(shape=_hole, direction=(1, 0, 0), count=3, spacing=15)
```
- 线性阵列：`_hole` 在 x=-15 时，3 个孔中心 x = -15、0、15，`count` 含原件，`spacing` 是相邻间距。
- 也可以用循环生成工具体后一次相减（`n_holes` 是整数参数，`range(n_holes)` 可用）：
```python
_tools = [scad.make_cylinder_rsolid(radius=hole_d / 2.5, height=base_t + 2, bottom_face_center=(-25 + i * 10, 0, -1))
          for i in range(n_holes)]
row_holes = scad.cut_rsolid(base, _tools)       # 6 个圆柱面
```

### 12.8 圆角与倒角
```python
_edges = ql.edges().where(ql.and_(
    ql.prop("geom.type", "==", "LINE"),
    ql.prop("geom.center.z", ">=", base_t - 0.1),
    ql.prop("geom.center.z", "<=", base_t + 0.1))).exactly(4)
rounded = scad.fillet_rsolid(solid=base, edges=_edges, radius=2)       # 体积 19031.39，新增 4 个圆柱面
chamfered = scad.chamfer_rsolid(solid=base, edges=_edges, distance=1)  # 体积 19101.33，面型全是平面（10 个）
```
- `edges` 可以直接传带 `.exactly(n)` 的选择器，也可以先 `.resolve(base)` 成列表再传，结果一样。
- 圆角生成的是圆柱面，所以倒圆角之后，按 `geom.type == "CYLINDER"` 选孔会多选到圆角面；要加上位置或面积条件（见 `ql-playbook.md`）。
- 竖直棱：`LINE` 且 `center.z` 在 `depth/2` 附近，4 条。

### 12.9 选面选边（QL）
```python
ql.faces().resolve(body)                  # 全部面，Python 列表（长方体 6 个）
ql.edges().resolve(body)                  # 全部边（长方体 12 条）
top = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99)))
top.resolve(body)                         # 1 个
top.exactly(1).resolve(body)              # 个数不对时抛 SimpleCADError
ql.faces().where(ql.prop("geom.type", "==", "PLANE")).order_by(ql.value("geom.area"), desc=True).take(1).resolve(body)  # 面积最大的平面
ql.faces().where(ql.or_(ql.prop("geom.normal.z", ">=", 0.99), ql.prop("geom.normal.z", "<=", -0.99))).resolve(body)     # 顶或底，2 个
ql.faces().where(ql.not_(ql.prop("geom.normal.z", ">=", 0.99))).resolve(body)                                            # 非顶面，5 个
```
- `ql.prop(路径, 比较符, 值)`：比较符 `== != >= <= > <`；`geom.type` 的值是大写字面量。
- 选坐标用范围，不要用 `==`。例：侧面 `ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.center.x", ">=", 29.9), ql.prop("geom.center.x", "<=", 30.1))).exactly(1).resolve(base)`（60×40×8 的板，选中 1 个，Task 10 补测）。

## 13. 常见报错原文（第 15 项）

异常类型 `simplecadapi.errors.SimpleCADError` 的信息是分段的多行文本：`Operation` / `Signature` / `Documentation` / `What happened` / `Measurements` / `Evidence`（含诊断图的临时路径）/ `Possible causes` / `How to fix` / `Technical details` / `Inventory`。给模型的翻译只保留 `What happened`、`Measurements` 和 `How to fix` 的前几行，去掉 `Evidence` 里的路径。

1. **选中 0 条边**（`.exactly(4)` 但没选到）
   ```text
   SimpleCADError: Operation: ql.edge.resolve
   What happened: QL selector expected exactly 4 edge(s), got 0
   Measurements: matched_count: 0 / candidate_count: 12 / expected_count: 4
   How to fix: No entity satisfies the full predicate; the near-miss inventory above lists what actually exists — align predicate values with those measured geometries.
   Inventory: E1 [near_miss] line, length 8 mm ...
   ```
   改法：看 Inventory 里实际有什么，把坐标范围、类型条件改对；不要降低 n 来凑数。
2. **圆角半径过大**
   ```text
   SimpleCADError: Operation: fillet_rsolid
   What happened: radius 50 mm meets or exceeds the 8 mm of face room between the failing edge and the opposite boundary of an adjacent face
   Measurements: radius: 50 mm / available_face_room: 8 mm / edge_start: (-30, 20, 8) mm / edge_end: (-30, -20, 8) mm
   How to fix: Reduce the radius to below 8 mm (e.g. 7.6) and retry. ...
   Technical details: ValueError: Fillet failed: OCC build did not complete
   ```
   改法：半径小于信息里给的余量，或换一组边。
3. **布尔运算的工具体没碰到主体**
   - `cut_rsolid(base, _tool)`（默认）：**不报错**，结果和原来一样（体积 19200 不变）。
   - `cut_rsolid(base, _tool, skip_non_intersecting=False)`：
     ```text
     SimpleCADError: Operation: cut_rsolid
     What happened: separated solids: operand 1 and operand 2 never touch; nearest detected gap is 668.8 mm (tolerance 0)
     Measurements: min_gap: 668.8 mm / closest_point_a: (30, 20, 0) mm / closest_point_b: (497.9, 497.9, 0) mm / closure_vector_a_to_b: (467.9, 477.9, 0) mm
     ```
   - `union_rsolid(base, _tool)`（两个不相连）：`What happened: separated solids: operand 1 and operand 2 never touch; nearest detected gap is 668.8 mm (tolerance 1e-05)`。
   改法：检查工具体的位置（信息里的 closure_vector 给出该移动多少），需要报错时给 `cut_rsolid` 加 `skip_non_intersecting=False`。
4. **参数名写错**：特征代码里用了没有的名字 `base_wd`
   ```text
   builtins.NameError: name 'base_wd' is not defined
   ```
   改法：对照需求单的参数名。（Task 3 的输入推断只认“参数名 ∪ 前面特征的变量名”，写错的名字不会成为 cell 输入，运行时才暴露为 `NameError`。）
5. **关键字参数名写错**（补充）
   ```text
   builtins.TypeError: make_box_rsolid(): incompatible function arguments. The following argument types are supported:
       1. (width: float | Expr, height: float | Expr, depth: float | Expr, bottom_face_center: ... = (0, 0, 0), *, tag_prefix: ...) -> Solid
   Invoked with: kwargs: w=Var(...), height=Var(...), ...
   ```
   改法：对照签名，`w=` 应为 `width=`。
6. **函数名写错**（补充）：`builtins.AttributeError: module 'simplecadapi' has no attribute 'make_box'`。改法：用 `api_help` 查真实函数名，函数名带 `_rsolid` 之类的后缀。
7. **一刀把实体切成两块**（补充）：`SimpleCADError: ... What happened: Failed to compute the boolean cut.`。

## 14. 附：Task 5 用到的测量写法

```python
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT

# 点在不在材料里
c = BRepClass3d_SolidClassifier(body.wrapped, gp_Pnt(x, y, z), 1e-6)
c.State()        # TopAbs_IN / TopAbs_OUT / TopAbs_ON
# 两个面（或边）的最小距离
d = BRepExtrema_DistShapeShape(face_a.wrapped, face_b.wrapped)
d.Perform(); d.IsDone(); d.Value()
# 两个平面的法向夹角
n1, n2 = fa.get_normal_at(), fb.get_normal_at()
angle = math.degrees(math.acos(max(-1, min(1, n1.x*n2.x + n1.y*n2.y + n1.z*n2.z))))
```

实测（带孔板，孔在中心）：
- `(0,0,4)`（孔里）→ `OUT`；`(20,0,4)`（板内）→ `IN`；`(100,0,4)` → `OUT`；`(30,0,4)`（侧面上）→ `ON`。**点分类的 `ON` 要当作“在材料上”还是“不在”由检查器决定**：`point_inside` 取 `IN` 或 `ON`，`point_outside` 取 `OUT`。
- 孔的圆柱面到 +x 侧面（x=30）的最小距离 = `25.000000`。
- 顶面与 +x 侧面的法向夹角 = `90.0000°`。
- `face.wrapped`、`edge.wrapped` 是 OCP 的 `TopoDS_*`，可以直接给上面两个类用。

## 15. 检查写法实测（1.1 版 Task 8）

速查表"检查写法"一节的 9 条写法，每条都在 `tests/test_check_recipes.py` 里用真实 SCA 跑过：参数正确时检查全部通过；"做错了的模型"（notebook 里参数值不变，只在特征代码里把这个参数换成 `(参数 * 1.2)` 或 `(参数 * 0.8)`，孔数换成 `+ 1`、`- 1`）都有检查不通过，而且模型本身能建出来（`error` 为空）。检查 JSON 与速查表里"例："逐项相等（`tests/test_prompts.py::test_check_recipe_examples_match_tests`）。

| 参数种类 | 小模型 | 检查类型 | 正确时实测 | 偏大 / 偏小时 |
|---|---|---|---|---|
| 总体尺寸 | 60×40×5 的板 | `bbox` | 60.0 | 72.0 / 48.0，都不通过 |
| 板厚 | 同上 | `distance`（顶面到底面） | 5.0 | 6.0 / 4.0，都不通过 |
| 孔径 | 板上 1 个直径 8 的通孔 | `count`（CYLINDER 面，面积在 π·d·t 的 ±5% 内） | 1 | 0 / 0 |
| 孔数 | 100×100×5 的板上圆周阵列 6 个直径 6 的孔 | `count`（同上，expected 写孔数参数） | 6 | 7 / 5 |
| 孔位 | 80×40×5 的板，孔心 x=25，直径 6 | `point_outside`（孔心）+ `point_inside`（孔边外 0.5 mm） | 两条都过 | 偏大两条都不过；偏小只有孔心那条不过（孔边那条仍过） |
| 槽或缺口宽度 | 60×40×5 的板，边上开宽 10、深 15 的缺口 | `point_outside`（墙内 0.5 mm）+ `point_inside`（墙外 0.5 mm） | 两条都过 | 偏大只有墙外那条不过；偏小只有墙内那条不过 |
| 圆角半径 | 60×40×10 的块，一条竖直棱圆角 r=4 | `count`（CYLINDER 面，面积在 π/2·r·L 的 ±5% 内） | 1 | 0 / 0 |
| 倒角尺寸 | 同上，倒角 c=3 | `count`（PLANE 面，法向 x、y 分量在 0.6~0.8，面积在 √2·c·L 的 ±5% 内） | 1 | 0 / 0 |
| 两面夹角 | 底长 60、宽 30、倾角 30° 的楔形块 | `angle`（斜面与底面法向夹角，期望 `180 - slope_deg`） | 150.0° | 144.0° / 156.0°，都不通过 |

注意：
- 用面积间接测孔径、圆角、倒角时，偏 20% 面积会偏 20%（圆角、倒角、孔径的面积都和该尺寸成正比），所以 ±5% 的窗口能抓住 20% 的偏差，但抓不住 5% 以内的小偏差。
- 孔位、槽宽用的是"点在不在材料里"，窗口是 ±0.5 mm：孔位偏差超过 0.5 mm 左右（孔心点落进材料）、槽宽偏差超过 1 mm 左右会被抓到，更小的偏差抓不到。孔位的两条检查互补，偏小时只有第一条（孔心）能抓住。
- 点检查的 `point` 里可以放参数表达式（字符串），也可以夹数字。
- 这 9 条都做到了"偏 20% 就不通过"，没有需要降级成"只能粗略检查"的条目，所以没有为此新增偏离记录。

## 16. STL 导出（网页前端 Task 1）

探测脚本 `scripts/probe_stl.py`（一块 60×40×8 带 φ10 通孔的板）：

```python
cap = scad.capture(run.definition, pkg_path)                       # 同导出 STEP
report = exporter.export_product_package_to_stl(cap.package, "model.stl")   # 也可以直接传 .scadpkg 路径
```

- 签名：`export_product_package_to_stl(data, output_path, *, linear_deflection=0.1, angular_deflection_degrees=20.0, relative=False) -> ProductSTLExportReport`。
- 返回 `ProductSTLExportReport`：`output_path`、`root_definition_id`、`solid_count`、`definition_count`、`vertex_count`、`triangle_count`、`linear_deflection`、`angular_deflection_degrees`、`relative`、`tessellation_backend`（`opencascade-brep-tessellation`）。实测板：160 个三角形、8084 字节。
- 输出是**二进制 STL**：80 字节头（以 `Simpl` 开头，不是 `solid`，所以 three.js 的 `STLLoader` 会当二进制读）+ 4 字节三角形个数 + 每个三角形 50 字节；文件大小 = 84 + 50 × 三角形数。
- 精度：`linear_deflection` 是最大弦高偏差（毫米）。0.5 → 112 个三角形（5684 字节）；0.1（默认）→ 160（8084）；0.02、角度 10° → 304（15284）。默认值对网页预览足够，不调。`relative=True` 在这块板上和默认结果一样。
- 坐标就是模型自己的坐标，单位毫米，z 朝上、底面在 z=0：这块板的顶点范围 x ±30、y ±20、z 0~8。
- 写进中文目录成功。
- 第一个版本（STEP）已经在同一个 `capture` 的包上导出，所以网页版的交付在子进程里只多一步 STL 导出，不用再 `capture` 一次。

## 17. probe 单元与占位产品

探测脚本 `scripts/probe_v2.py`（第二版计划 1 Task 1，2026-11-10），输出在 `docs/sca-probe-output.txt` 末尾。

probe 单元的形状（程序写，放在最后一个特征之后、产品单元之前）：

```python
@app.cell
def _(base, n, phone_w):
    # ---- probe ----
    import contextlib as _ctx
    import io as _io
    def _probe(model):
        print('phone_w =', float(phone_w))
        print('n =', n)
    _buf = _io.StringIO()
    try:
        with _ctx.redirect_stdout(_buf):
            _probe(base)
    finally:
        with open("probe_out.txt", "w", encoding="utf-8") as _f:
            _f.write(_buf.getvalue())
    return ()
```

实测：
- `run_notebook` 正常运行，5 个 cell 都是 `ran`；`probe_out.txt` 写在**当前工作目录**（沙盒里就是临时目录），内容是 `'phone_w = 78.0\nmodel type Solid\nn = 3\n'`。参数（`Var` 和整数）、特征变量都能读到；`model` 就是传进去的实体（`Solid`）。`return ()` 的 cell 没问题。
- probe 里抛异常时（先 `print('到这里')` 再用未定义的名字）：`run_notebook` 原样抛出 `NameError`；`finally` 照样写出文件，内容是 `'到这里\n'`。
- 出错帧：traceback 里有两个文件名含 `__marimo__cell_` 的帧（cell 本身，函数 `<module>`；`_probe` 里面，函数名被改写成 `_cell_<哈希>-vblA_probe`），用 `linecache.getlines(帧文件)[:3]` 读到的源码第一行都是 `# ---- probe ----`。所以判断办法和特征一样：取最后一个 `__marimo__cell_` 帧，源码前几行里有 `# ---- probe ----` 就把出错位置标成 `probe`。`_probe` 里的行号是 cell 内部行号（probe 代码的第 1 行是 cell 的第 5 行）。
- **笔记第 4 节的 `brep.inspect_shape_rbrepinspection` 在 notebook 里不能用**：`RuntimeError: simplecadapi.inspect.brep tools cannot run inside an active GraphSession`（官方文档 `geometric-validation.md` 也写了检视函数只能在 GraphSession 之外用）。probe 里量尺寸要用这几种在 notebook 里能用的写法：
  - 体积：`model.get_volume()` → `24960.0`；
  - 包围盒：全部顶点的坐标取最大最小，`_pts = [v.get_center() for v in ql.vertices().resolve(model)]`，再分别取 `p.x`、`p.y`、`p.z` 的范围 → `78.0 40.0 8.0`。只有平面围成的零件这样量是准的；有圆柱面、圆角时，顶点范围可能比真实包围盒小（圆柱面中间鼓出去的部分没有顶点）。
  - 面数、边数：`len(ql.faces().resolve(model))` → 6，`len(ql.edges().resolve(model))` → 12。
  - probe 代码要过 `check_code`，所以不能写 `getattr`、`import`。

没有特征时的占位（实验 2）：在 probe 单元前面加一个程序写的单元 `placeholder_body = scad.make_box_rsolid(width=1, height=1, depth=1, bottom_face_center=(0, 0, 0))`，probe 单元里写 `_probe(None)`，产品单元用 `placeholder_body`。实测能运行，`probe_out.txt` 是 `'True\n78.0\n'`（`model is None`、参数可读），产品包围盒 `[-0.5, -0.5, 0, 0.5, 0.5, 1]`。

**一次运行取各阶段末尾的实体（实验 3，只记结论，这一版不用）：** `run.values` 里有**全部** cell 定义的名字：`['base', 'hole', 'math', 'model', 'n', 'phone_w', 'ql', 'scad']`。`run.values['base']` 是 `Solid`，在 notebook 外用检视函数量得包围盒 `[-39, -20, 0, 39, 20, 8]`、体积 24960；`run.values['hole']` 体积 24331.68。所以一次运行就能拿到每个特征（也就是每个阶段最后一个特征）的实体，以后可以把"每个阶段各跑一次截断的 notebook"优化成一次运行。

## 18. 草图轮廓

最短可行写法（L 形，画在 XZ 平面，顶点里直接用 `Var` 表达式）：

```python
_s = scad.make_sketch_rsketch("l_profile", plane="XZ")
_pts = [(-l / 2, 0), (l / 2, 0), (l / 2, t), (-l / 2 + 20, t), (-l / 2 + 20, h), (-l / 2, h)]
for _i, (_u, _v) in enumerate(_pts):
    _s = scad.add_point_rsketch(_s, f"p{_i}", _u, _v)
for _i in range(6):
    _s = scad.add_line_rsketch(_s, f"e{_i}", f"p{_i}", f"p{(_i + 1) % 6}")
_face = scad.make_face_from_sketch_rface(_s)
_solid = scad.extrude_rsolid(profile=_face, direction=(0, 1, 0), distance=w)
lsk = scad.translate_shape(shape=_solid, vector=(0, -w / 2, 0))
```

实测：l=120、t=8、h=60、w=30 → 包围盒 `[-60, -15, 0, 60, 15, 60]`，体积 60000（= 120×8×30 + 20×52×30），8 个平面，有效。
- 签名：`make_sketch_rsketch(name=None, *, plane='XY')`，`plane` 只能是 `'XY'`、`'XZ'`、`'YZ'`（写 `'ZX'` 报 `Sketch plane must be 'XY', 'XZ', 'YZ', or a plane mapping`）。`add_point_rsketch(sketch, point_id, x, y)`；`add_line_rsketch(sketch, entity_id, start, end)` 的 `start`、`end` **必须是点的名字（或 SketchRef）**，直接传坐标元组报 `TypeError: incompatible function arguments`。每个 `add_*` 都返回新的草图，要重新赋值。
- 平面映射：`XZ` 平面上局部坐标 (u, v) → (x, z)，面的法向是 (0, −1, 0)；`XY` → (x, y)，法向 (0, 0, 1)；`YZ` → (y, z)，法向 (1, 0, 0)。
- 拉伸方向：XZ 平面的面沿 (0, 1, 0) 拉伸 30 → y 从 0 到 30；要在 y 方向以 0 为中心，再 `translate_shape` 平移 −w/2。**沿面内方向拉伸不会报错**：沿 (0, 0, 1) 拉伸得到体积 0、`valid=True` 的"实体"，所以拉伸后一定要用体积或包围盒检查。
- 求解状态：`scad.inspect_sketch_rsketchresult(_s)` 返回 `SketchSolveResult`：`status='underconstrained'`、`dof=12`、`residual_norm=0.0`。没加任何约束时也能照样转成面（`make_face_from_sketch_rface` 默认 `require_fully_constrained=False`），顶点就在给定坐标上。卡尺里尺寸都由参数直接给出，不需要加约束。
- 圆弧：`scad.add_arc_rsketch(sketch, entity_id, start, end, center)`（三个都是点的名字），从 `start` 按正方向（逆时针）扫到 `end`。实测：(−20,−10)→(20,−10) 直线 + 圆心 (20,0) 从 (20,−10) 到 (20,10) 的半圆 + 两段直线，拉伸 5 → 包围盒 `[-20, -10, 0, 30, 10, 5]`、体积 4785.3982，和手算 (40×20 + π×100/2)×5 一致。

## 19. 抽壳

```python
_box = scad.make_box_rsolid(width=l, height=w, depth=h, bottom_face_center=(0, 0, 0))
_top = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99)))
tray = scad.shell_rsolid(solid=_box, faces_to_remove=_top, thickness=wall)
```

实测：80×50×30、去掉顶面、壁厚 2 → 外形不变 `[-40, -25, 0, 40, 25, 30]`，体积 22112（= 80×50×30 − 76×46×28），11 个平面。
- 签名 `shell_rsolid(solid, faces_to_remove, thickness)`；`faces_to_remove` 传选择器或 `.resolve()` 出来的列表都行。**壁厚向里长**（外形尺寸不变）。`thickness` 必须是正数，写负数报 `Failed to apply the shell operation`。
- "外形减内腔"的写法 `cut_rsolid(_box, 小一圈的盒子（底面在 z=wall）, skip_non_intersecting=False)` 得到完全相同的结果（体积 22112）。两种都可控：要底厚和侧壁厚不同时，只能用"减内腔"；壁厚一样时用 `shell_rsolid` 更短。
- 先圆角再抽壳：四条竖棱 R6 圆角后再抽壳，成功，体积 21569.49，多出 8 个圆柱面（外圆角 4 个、内壁跟着变成的圆角 4 个）。所以外竖边的圆角放在抽壳**前面**，内壁会自动带上圆角。

沉头孔（实验 8）：一次减两个同轴圆柱，通孔 φ5 贯穿、沉头 φ10 从顶面往下 3（工具体多伸出 1 mm）：

```python
_hole = scad.make_cylinder_rsolid(radius=2.5, height=t + 2, bottom_face_center=(0, 0, -1))
_cb = scad.make_cylinder_rsolid(radius=5, height=3 + 1, bottom_face_center=(0, 0, t - 3))
plate = scad.cut_rsolid(_plate, _hole, _cb, skip_non_intersecting=False)
```

80×50×8 的板 → 结果是一个有效实体，体积 31666.2058（= 32000 − π×2.5²×5 − π×5²×3，一致），2 个圆柱面。

## 20. 扫掠

```python
_c = math.cos(math.radians(45))
_e1 = scad.make_segment_redge(start=(0, 0, 0), end=(0, 0, h))
_e2 = scad.make_three_point_arc_redge(start=(0, 0, h), middle=(10 - 10 * _c, 0, h + 10 * _c), end=(10, 0, h + 10))
_e3 = scad.make_segment_redge(start=(10, 0, h + 10), end=(10 + l, 0, h + 10))
_path = scad.make_wire_from_edges_rwire(edges=[_e1, _e2, _e3])
_profile = scad.make_circle_rface(center=(0, 0, 0), radius=r, normal=(0, 0, 1))
pipe = scad.sweep_rsolid(profile=_profile, path=_path)
```

实测：r=4、h=30、l=40（圆弧半径 10，圆心 (10, 0, 30)）→ 包围盒 `[-4, -4, 0, 50, 4, 44]`，体积 4308.1521，和 π×4²×(30 + 40 + 10×π/2) 完全一致；面型 2 个圆柱面 + 1 个圆环面 + 2 个平面。
- 截面放在路径起点、法向沿路径起始方向。`is_frenet=True` 结果一样。
- 路径各段首尾要相接；边用 `make_segment_redge`、`make_three_point_arc_redge`（起点、中间一点、终点），再用 `make_wire_from_edges_rwire(edges=[...])` 连成线。
- 折线路径（`make_polyline_rwire` 的直角拐弯，不带圆弧）也能扫，但拐角处是尖角拼接（体积 1507.96，出现一个 `SurfaceOfExtrusion` 面），拉手这类要圆滑过渡的用圆弧段。

## 21. 标准件：齿轮与齿条

齿轮在 `scad.std.gear` 里（不在 `api/` 文档目录，文档在 `references/docs/stdlib/make_spur_gear_rsolid.md`；`api_help` 查不到）：

```python
gear = scad.std.gear.make_spur_gear_rsolid(n_teeth=z, module=m, gear_height=gw)
```

- 签名 `make_spur_gear_rsolid(n_teeth, module, pressure_angle=20.0, gear_height=6.0, *, addendum_factor=1.0, clearance_factor=0.25, backlash=0.0)`。`n_teeth` 是整数（参数单位写 `1`），`gear_height` 可以是 `Var`。
- 模数 2、齿数 30、齿宽 12：**轴线是 z 轴**，z 从 0 到 12；包围盒 `[-32, -31.893, 0, 32, 31.893, 12]`，即 x 方向 64.0、y 方向 63.79。**齿顶圆直径实测 64**（= 模数×(齿数+2)），和验收里按 64 算一致，不用改数字。x 方向是 64 是因为 +x 方向正对一个齿的中心：点 (31.9, 0, 6) 在材料里、(32.1, 0, 6) 在材料外；y 方向两侧不是齿尖，所以略小于 64。体积 33435.25，182 个面。
- 能直接和圆柱 `union_rsolid`（轮毂 φ24 高 20）、能直接 `cut_rsolid` 轴孔（φ10）：结果有效，包围盒 z 到 20，体积 35483.57。单个齿轮约 1.5 秒。

齿条：

```python
rack = scad.std.gear.make_spur_rack_rsolid(module=2, n_teeth=10, rack_height=10)
```

- 签名 `make_spur_rack_rsolid(module, n_teeth=10, pressure_angle=20.0, rack_height=6.0)`。齿形在 XY 平面里，沿 z 拉伸 `rack_height`；x 方向长 n_teeth×π×module（62.83），y 方向只有齿高（−2.5 到 2.0，即齿根 1.25m、齿顶 1m），**没有齿条的背板**。
- **踩到的坑：SCA 2.2.7 生成的齿条 `valid=False`**（`BRepCheck_Analyzer` 也判定无效），三组参数（m2 z10、m1 z5、m2.5 z12 h8）都一样。减孔（`cut_rsolid`）能算出来，但结果仍然无效；和一个方块 `union_rsolid`（默认和 `glue=True` 都试了）在 60 秒内不返回。所以齿条**不能**用来做必须通过"实体有效"检查的零件。要做齿条时得另想办法（比如用第 18 节的草图画齿形再拉伸），这个写法还没有实测，用之前要先探测。

内齿圈（第二版计划 1 Task 14 补测，偏离 D13）：

```python
ring = scad.std.gear.make_spur_ring_gear_rsolid(n_teeth=teeth_n, module=gear_m, gear_height=ring_h, rim_thickness=2.5 * gear_m)
```

- 签名 `make_spur_ring_gear_rsolid(n_teeth, module, pressure_angle=20.0, gear_height=6.0, rim_thickness=3.0, backlash=0.0, *, addendum_factor=1.0, clearance_factor=0.25)`。模数 2、齿数 40、齿宽 8、轮缘厚 5：**实体有效**（`valid=True`、1 个实体），约 1.7 秒；轴线是 z 轴，z 从 0 到 8；包围盒 x、y 都是 ±47.5。
- 尺寸：齿顶（齿尖朝里）半径 = 模数 ×（齿数 − 2）/ 2 = 38；齿根半径 = 模数 ×（齿数 + 2.5）/ 2 = 42.5；外圈半径 = 齿根半径 + 轮缘厚 = 47.5。
- 齿的位置：**+x 方向正对一个齿**：(38.2, 0, 4)、(40, 0, 4) 在材料里，(37.5, 0, 4) 在材料外；转半个齿距（4.5°）的方向是齿槽：半径 38.2~42 都在材料外，42.8 才进入轮缘。
- 面：81 个圆柱面（40 个齿顶面、40 个齿根面、1 个外圆柱面 2πrh = 2387.6）、80 个 SurfaceOfExtrusion（齿廓）、2 个平面。
- 能直接和一个套在外圈上的圆环（外径 120、内径 86，内孔边落在轮缘里）`union_rsolid`，结果有效，0.4 秒；再用圆周阵列减 6 个 φ6 孔，有效。

## 22. 多视角渲染

`render_screenshot_rpath(body, path, view=...)` 的 `view` 用 `(仰角, 方位角)`，实测用一块 +x、+y 角上带立柱的不对称零件认方向：

| 视图 | `view` | 画面 |
|---|---|---|
| 正视（从 −y 看） | `(0, -90)`，等同于预设 `"front"` | x 向右、z 向上 |
| 俯视（从 +z 看） | `(90, 0)`，等同于预设 `"top"` | x 向右、y 向上 |
| 右视（从 +x 看） | `(0, 0)`，等同于预设 `"right"` | y 向右、z 向上 |
| 等轴测 | `"iso"` | — |

- 每张都正常写出 PNG（500×400 时约 11 KB，iso 约 20 KB）。预设名和对应的角度元组得到的图一样（左下角标注不同："front" 与 "view"）。
- 渲染在独立子进程里完成，不会拖垮调用方。

## 23. 零件 notebook 的组装

探测脚本 `scripts/probe_assembly.py`（3.0 计划 2 Task 1，2026-11-20），输出在 `docs/sca-probe-output.txt` 末尾。

- 零件 notebook 文件头的 `id` 和产品变量都用零件编号（`id = "body"`，`body = scad.Part(part_id="body", body=...)`）。装配 notebook（文件头 `id = "product"`）里：
  ```python
  body = scad.use("body.py", h=h, w=w)      # 相对装配 notebook 所在目录
  _a = scad.make_assembly_rassembly("product")
  _a = scad.add_component_rassembly(_a, body, "body", scad.make_placement_rplacement((0, 0, 0)))
  product = _a
  ```
  运行成功（2.2 秒），`run.product` 是 `Assembly`，`run.definition` 是 `AssemblyDefinition`，`run.product.components` 的 `component_id` 是 `['body', 'lid']`。
- **覆盖值要把参数 cell 里的变量一起传**：只传 `h` 不传 `w` 报 `ValueError: body.py: the cell defining h also defines w; override them together, or define them in cells of their own`。所以装配 notebook 把零件参数 cell 里的全部参数都传过去。
- 编号写死成 `model`、但产品变量是 `body` 时报 `ProductNotFoundError: body.py: no top-level Part or Assembly has the notebook id 'model'; Parts and Assemblies found: body (id 'body')`。`scad.use("body.py", id="body", ...)` 可以改编号（能运行），但我们直接在文件头写零件编号，不用这个参数。

## 24. 摆放与重叠体积

- 4×4 矩阵（3×3 旋转 + 平移）放实体，两种写法和手算的包围盒都一致（绕 (1,1,0) 转 90° 再平移 (100,0,50) → `[92.5, -10.3284, 39.3934, 110.3284, 7.5, 60.6066]`）：
  - SCA：`rotate_shape(shape, angle, axis, origin=(0,0,0))` 再 `translate_shape(shape, vector)`，要从矩阵算轴角，转 180° 时轴要另算；
  - **OCP（沙盒里用这个）**：`gp_Trsf().SetValues(r00, r01, r02, tx, r10, ..., r22, tz)` + `BRepBuilderAPI_Transform(solid.wrapped, trsf, True).Shape()`，转 180° 也对。注意得到的是 OCP 形状：**SCA 的 `Solid` 不能从 OCP 形状构造**（`TypeError: No constructor defined!`），所以摆好的零件只用 OCP 和检视函数量（检视函数可以直接传 OCP 形状）。
- 重叠体积：
  - `scad.intersect_rsolid(a, b)` **不重叠、贴面时都抛 `SimpleCADError`**（"What happened" 为空），没法和真正的出错区分，而且齿轮啮合时一次要 7 秒多。**不用它。**
  - **用 OCP**：`BRepAlgoAPI_Common(a, b)`、`.Build()`，再 `BRepGProp.VolumeProperties_s(op.Shape(), props)`、`props.Mass()`。不重叠 0、贴面 0、重叠 1 毫米 400（20×20×1）、轴在孔里（单边间隙 0.2 或零间隙）都是 0；方块几毫秒，齿轮 0.5～1 秒。`op.IsDone()` 判断有没有算成。
  - 先比包围盒：OCP `Bnd_Box` + `BRepBndLib.Add_s` + `IsOut` 约 1 毫秒一对，不相交就跳过。
- 齿轮（模数 2，20 齿和 40 齿，中心距 60）：大齿轮转半个齿距（4.5°）让齿槽对着小齿轮的齿 → 重叠 0；齿顶对齿顶 → 196.73；小齿轮转 9°、大齿轮反向转 4.5°（一起转半齿）→ 0；转 4°/2° → 0。标准齿轮正确啮合时重叠就是 0。

## 25. 装配、材料与导出

- 材料：`scad.make_material_rmaterial("abs", name="ABS", color=(0.227, 0.247, 0.278))`。**颜色是 0～1 的三个浮点数**，写 `"#3A3F47"` 或 0～255 的整数都报 `Failed to create the material definition`。程序把 `#RRGGBB` 换成三个浮点数（保留三位小数）再写进 notebook。
- 在 notebook 里赋材料要用 `make_part_rpart`：
  ```python
  body = scad.assign_material_rpart(scad.make_part_rpart("body", base), scad.make_material_rmaterial("abs", name="ABS", color=(0.227, 0.247, 0.278)))
  ```
  写成 `assign_material_rpart(scad.Part(...), ...)` 报 `ValueError: unrecorded Part cannot be used in active graph 'body'; build it inside this GraphSession`。运行后 `run.product` 是 `Part`，`.body` 是 `Solid`，`.material` 就是这个材料。
- 零件和产品的 STEP 里都带颜色（文件里有 `COLOUR_RGB`）。
- `scad.capture` 只收 `PartDefinition`、`AssemblyDefinition`、`PartBuildResult`、`AssemblyBuildResult`；在 notebook 外面手搭的 `Assembly` 不能直接 capture。所以**整个产品的 STEP 由运行装配 notebook 得到**：`cap = scad.capture(run.definition, pkg)`，再 `export_product_package_to_step(cap.package, step)`（2 个 occurrence，35 KB）；`export_product_package_to_stl` 也能导出整个产品（2 个实体）。
- 摆放：`scad.make_placement_rplacement(origin, x_axis=..., y_axis=...)` 就是矩阵的三列：零件自己的 x、y 轴在装好后朝哪里、原点在哪里（z 轴 = x × y）。实测盖子 `x_axis=(1,0,0)`、`y_axis=(0,0,1)`、原点 (0,0,12) 后，产品 STL 的 z 范围到 32（= 12 + 20），和手算一致。

## 26. 约束驱动与闭环

- 转动约束能驱动：两个零件各加一个面连接点（`add_connector_rpart(part, make_face_connector_rconnector("top", face))`，被动零件的底面连接点 `flip=True`），`ground_component_rassembly(asm, "base")`，`add_revolute_constraint_rassembly(asm, "hinge", make_connector_ref_rconnectorref("base", "top"), make_connector_ref_rconnectorref("arm", "bottom"), drive_angle_degrees=30)`，`solve_assembly_constraints_rassembly(asm)`。解出来 `arm` 的 `placement` 是绕底座顶面中心、沿顶面法向转 30°/60°/90°（x 轴 (0.866, 0.5, 0)、(0.5, 0.866, 0)、(0, 1, 0)），和手算一致（误差 1e-15），每次不到 1 毫秒。
- 滑动约束 `add_prismatic_constraint_rassembly(..., drive_distance=...)` 签名相同，这次没有单独实测。
- **闭环（曲柄滑块）没有测**：用户要求省时间，本计划也不做闭环。结论：不支持（本计划只做树形装配）。
- 多零件验收（`benchmarks/assembly_accept.py`）用的就是上面的转动约束驱动；滑动关节在验收里独立写平移。

## 27. 连接点取几何

孔（φ6，轴线沿 z，中心 x=5）的块，用 OCP 的适配器读真实几何：

```python
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
s = BRepAdaptor_Surface(face.wrapped); ax = s.Cylinder().Axis()     # 圆柱面
ax.Location(), ax.Direction(), s.Cylinder().Radius()                 # (5, 0, -1)、(0, 0, 1)、3.0
c = BRepAdaptor_Curve(edge.wrapped).Circle(); c.Axis().Location(), c.Axis().Direction(), c.Radius()   # 圆形的边
```

- 圆柱面：`get_center()` 是 (5, 0, 5)（面中间），轴线上的点是 (5, 0, −1)（圆柱的起点）。**连接点的原点取 `get_center()` 投影到轴线上的点**（这里是 (5, 0, 5)），方向取轴线方向。轴线方向的正负由 SCA 定（这里是 +z），所以模型要用 `flip` 定朝向。
- 平面：原点 `get_center()`，方向 `get_normal_at()`（朝材料外）。注意 `get_center()` 是面的形心，带孔的面形心会偏（顶面形心 x = −0.12）。
- 圆形的边：原点是圆心 `Circle().Axis().Location()`（(5, 0, 10)），方向是 `Axis().Direction()`（(0, 0, 1)）。
- 判断类型：面用 `BRepAdaptor_Surface(f.wrapped).GetType()`（`GeomAbs_Plane`、`GeomAbs_Cylinder`），边用 `BRepAdaptor_Curve(e.wrapped).GetType()`（`GeomAbs_Circle`）。SCA 的面对象没有 `get_type()`。

## 三个常量（3.0 计划 2 Task 1 定下）

- `CONTACT_TOL_MM3 = 0.5`：实测"接触"（轴在孔里、齿轮正确啮合、贴面）的重叠体积都是 0；按规则 2 × 0 向上取到 0.5 的整数倍是 0，那样接触配对就和普通配对一样了，所以取最小的正值 0.5。
- 默认取样数 24：齿轮一次重叠约 0.5～1 秒，一个齿轮关节 24 个位置约 20 秒（方块之类不到 1 秒）。
- 闭环：没有测，本计划不做（见第 26 节）。

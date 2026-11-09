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
- 没验证过 `sca edit` 在中文目录下的表现，留到 Task 11（`/view`）时测，测完补进本节。

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
- `sca edit [--host HOST] [--port PORT] [--no-browser] [workspace]`：打开代码优先编辑器，`workspace` 是放 notebook 的目录或单个 notebook。
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

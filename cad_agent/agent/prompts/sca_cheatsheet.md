# SCA 常用写法速查（simplecadapi 2.2.7 实测）

下面每条写法都在 SCA 2.2.7 里实际跑通过。参数名（如 base_w）都是需求单里的参数，可以直接参与运算，不用写成数字。调用函数一律用关键字参数。

## 基本体
- `make_box_rsolid(width=, height=, depth=, bottom_face_center=)`：长方体。width 沿 x 轴，height 沿 y 轴，depth 沿 z 轴；bottom_face_center 是**底面的中心点**（不是角点）：长方体在 x、y 方向以它为中心，从它所在的高度向 +z 长出 depth。
  例：`_b = scad.make_box_rsolid(width=base_w, height=base_d, depth=base_t, bottom_face_center=(0, 0, 0))`
  想让角点落在原点，就把底面中心放到 (宽/2, 深/2, 0)：
  例：`_b = scad.make_box_rsolid(width=base_w, height=base_d, depth=base_t, bottom_face_center=(base_w / 2, base_d / 2, 0))`
- `make_cylinder_rsolid(radius=, height=, bottom_face_center=, axis=(0, 0, 1))`：圆柱。radius 是半径（不是直径）；height 是沿 axis 方向的长度；bottom_face_center 是起始那个圆面的圆心；axis 默认 +z（竖直），写 (1, 0, 0) 就沿 +x 横放。
  例：`_post = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t, bottom_face_center=(0, 0, 0))`
  例：`_pin = scad.make_cylinder_rsolid(radius=hole_d / 2, height=20, bottom_face_center=(0, 0, 5), axis=(1, 0, 0))`

## 草图轮廓与拉伸
- `make_rectangle_rface(width=, height=, center=, normal=(0, 0, 1))`：矩形面。width 沿 x，height 沿 y，center 是矩形中心。再用 `extrude_rsolid(profile=, direction=, distance=)` 沿 direction 拉伸 distance 的长度；沿 +z 拉伸就写 direction=(0, 0, 1)。
  例：`_profile = scad.make_rectangle_rface(width=base_w, height=base_d, center=(0, 0, 0), normal=(0, 0, 1)); plate = scad.extrude_rsolid(profile=_profile, direction=(0, 0, 1), distance=base_t)`
- `make_circle_rface(center=, radius=, normal=(0, 0, 1))`：圆形面，center 是圆心，radius 是半径。拉伸方法同上。
  例：`_profile = scad.make_circle_rface(center=(0, 0, 0), radius=hole_d / 2, normal=(0, 0, 1)); disc = scad.extrude_rsolid(profile=_profile, direction=(0, 0, 1), distance=base_t)`

## 多边形截面拉伸
- `make_polyline_rwire(points=, closed=True)` → `make_face_from_wire_rface(wire=, normal=)` → `extrude_rsolid(profile=, direction=, distance=)`：用一串三维点围成截面，在指定平面上拉伸。截面画在 XZ 平面时，点写成 (x, 0, z)，沿 +y 拉伸 distance，得到的实体 y 从 0 到 distance；要让厚度居中，再用 translate_shape 平移 (0, -厚度/2, 0)。
  **normal 要和点的顺序一致**：点在 XZ 平面里按“x 向右、z 向上”看是逆时针时写 `normal=(0, -1, 0)`，顺时针写 `(0, 1, 0)`；写反了结果还是对的，但会打印“normal of the created face is opposite”告警。
  例：`_wire = scad.make_polyline_rwire(points=[(0, 0, 0), (base_d, 0, 0), (0, 0, rib_h)], closed=True); _profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0)); rib = scad.extrude_rsolid(profile=_profile, direction=(0, 1, 0), distance=rib_t)`
  用角度算顶点时，数学函数可以直接用（参数是角度，要先 `math.radians`）：
  例：`_rise = base_d * math.tan(math.radians(tilt_deg)); _wire = scad.make_polyline_rwire(points=[(0, 0, 0), (base_d, 0, 0), (base_d, 0, _rise)], closed=True)`

## 旋转体
- `revolve_rsolid(profile=, axis=(0, 0, 1), angle=360, origin=(0, 0, 0))`：把截面绕 axis 转 angle 度。截面画在 XZ 平面：x 是到轴线的距离（半径），z 是高度，各点围成封闭多边形，再绕 z 轴转一圈。法兰盘就这样做：带中心孔的截面转出来，孔和凸台一次成形。
  例：`_pts = [(bore_d / 2, 0, 0), (flange_od / 2, 0, 0), (flange_od / 2, 0, flange_t), (boss_d / 2, 0, flange_t), (boss_d / 2, 0, total_h), (bore_d / 2, 0, total_h)]; _wire = scad.make_polyline_rwire(points=_pts, closed=True); _profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0)); flange = scad.revolve_rsolid(profile=_profile, axis=(0, 0, 1), angle=360, origin=(0, 0, 0))`

## 布尔运算
- `union_rsolid(a, b)`：合并。两个实体必须相接或重叠，完全分开会报错。
  例：`joined = scad.union_rsolid(base, post)`
- `cut_rsolid(被减体, 工具1, 工具2, ...)`：第一个是被减的，后面的都是工具体，一次可以减多个，也可以传一个工具体列表。**工具体完全没碰到被减体时，默认悄悄跳过、不报错**，所以减孔、开槽时加 `skip_non_intersecting=False`，位置错了才会报错。相切的工具体（比如间距刚好等于直径的两个孔）会让布尔运算失败，要留出缝隙或让它们重叠。
  例：`holes = scad.cut_rsolid(base, _h1, _h2, skip_non_intersecting=False)`
- `intersect_rsolid(a, b)`：取交集，只留两个实体重叠的部分。
  例：`cap = scad.intersect_rsolid(base, _box)`

## 移动与旋转
- `translate_shape(shape=, vector=)`：把实体平移 vector=(dx, dy, dz)。
  例：`moved = scad.translate_shape(shape=base, vector=(10, 0, 5))`
- `rotate_shape(shape=, angle=, axis=, origin=)`：绕过 origin、方向为 axis 的轴旋转 angle **度**（右手定则）。绕 z 轴转 90 度，60×40 的板会变成 40×60。
  例：`turned = scad.rotate_shape(shape=base, angle=90, axis=(0, 0, 1), origin=(0, 0, 0))`

## 阵列
- `radial_pattern_rsolidlist(shape=, center=, axis=, count=, total_rotation_angle=)`：圆周阵列，得到实体列表。count 是**总个数（包含原件）**，total_rotation_angle=360 时均布。先在分布圆上放好第一个工具体，阵列后一次 cut_rsolid 减掉。
  例：`_hole = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t + 2, bottom_face_center=(pcd / 2, 0, -1)); _holes = scad.radial_pattern_rsolidlist(shape=_hole, center=(0, 0, 0), axis=(0, 0, 1), count=n_holes, total_rotation_angle=360); bolt_holes = scad.cut_rsolid(base, _holes, skip_non_intersecting=False)`
- `linear_pattern_rsolidlist(shape=, direction=, count=, spacing=)`：线性阵列，count 含原件，spacing 是相邻两个的间距。
  例：`_holes = scad.linear_pattern_rsolidlist(shape=_hole, direction=(1, 0, 0), count=3, spacing=15); row_holes = scad.cut_rsolid(base, _holes, skip_non_intersecting=False)`
- 间距不规则或要按参数算位置时，用循环生成工具体后一次相减（个数参数可以直接放进 `range()`）：
  例：`_tools = [scad.make_cylinder_rsolid(radius=hole_d / 2.5, height=base_t + 2, bottom_face_center=(-25 + i * 10, 0, -1)) for i in range(n_holes)]; row_holes = scad.cut_rsolid(base, _tools, skip_non_intersecting=False)`

## 圆角与倒角
- `fillet_rsolid(solid=, edges=, radius=)`：圆角，radius 要小于相邻面的宽度。edges 用 QL 选出来，**一定带 `.exactly(n)`**，选不到或个数不对会立刻报错，而不是悄悄少倒几条边。
  例：`_edges = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.z", ">=", base_t - 0.1), ql.prop("geom.center.z", "<=", base_t + 0.1))).exactly(4); rounded = scad.fillet_rsolid(solid=base, edges=_edges, radius=2)`
- `chamfer_rsolid(solid=, edges=, distance=)`：倒角，两边各切 distance。选边方法同上。
  例：`_edges = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.z", ">=", base_t - 0.1), ql.prop("geom.center.z", "<=", base_t + 0.1))).exactly(4); chamfered = scad.chamfer_rsolid(solid=base, edges=_edges, distance=1)`
- 圆角生成的是圆柱面，倒圆角之后再按 `CYLINDER` 选孔会多选到圆角面；孔的圆柱面要再加位置或面积条件。

## 选面选边（QL）
- `ql.faces()`、`ql.edges()`：从全部面 / 全部边开始选；`.resolve(solid)` 得到 Python 列表（面有 get_center()、get_area()，边有 get_center()、get_length()）。
  例：`_all_faces = ql.faces().resolve(base)`
- `.where(条件)`：筛选。条件用 `ql.prop(属性, 比较符, 值)` 写；多个条件用 `ql.and_(...)` 合并（并且），`ql.or_(...)`（或者），`ql.not_(...)`（非）。属性有 geom.type（PLANE、CYLINDER；边是 LINE、CIRCLE）、geom.center.x / y / z、geom.normal.x / y / z（只有平面有意义）、geom.area（面）、geom.length（边）。**没有 geom.radius**，要按孔径选圆柱面就用面积（侧面积 = π × 直径 × 高度）。
  例：`_top = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99)))`
- 按坐标选时用范围，不要用等号（坐标有浮点误差）；按法向选面时一定要同时限定 `geom.type == "PLANE"`，因为圆柱面也有法向。
  例：`_side = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.center.x", ">=", 29.9), ql.prop("geom.center.x", "<=", 30.1)))`
- `.exactly(n)`：要求恰好选中 n 个，不是 n 个就报错；给圆角、倒角选边时必用。
  例：`_top_face = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99))).exactly(1)`

## 常见报错与改法
- 选中 0 条边（或个数不对）：`QL selector expected exactly 4 edge(s), got 0`，下面会列出 near_miss（实际有的边）。→ 对照列出的类型、长度，把坐标范围和类型条件改对；不要为了不报错而改小 n。
- 圆角半径过大：`radius 50 mm meets or exceeds the 8 mm of face room ...`。→ 半径改到信息里给的余量以下（比如余量 8 就用 7 以内），或换一组边。
- 布尔运算的工具体没碰到主体：加了 `skip_non_intersecting=False` 时报 `operand 1 and operand 2 never touch; nearest detected gap is ... mm`，信息里的 closure_vector 就是该移动的方向和距离；没加这个参数时不报错，但孔根本没切出来，会被孔相关的检查抓到。→ 检查工具体的位置和高度，让它穿过主体。
- 参数名写错：`NameError: name 'base_wd' is not defined`。→ 对照需求单里的参数名（小写加下划线），以及前面特征的变量名（slug 里的短横线换成下划线）。
- 关键字参数名写错：`TypeError: make_box_rsolid(): incompatible function arguments`，后面会列出正确的参数签名。→ 照签名改（例如 `w=` 要写成 `width=`）。
- 函数名写错：`AttributeError: module 'simplecadapi' has no attribute 'make_box'`。→ 用 api_help 查真实的函数名，SCA 的函数名常带 `_rsolid`、`_rface`、`_rwire` 之类的后缀。

## 检查写法
- **总体尺寸**：用 bbox 测整体在某个方向上的长度，axis 写 x、y 或 z。
  例：`{"id": "size-x", "type": "bbox", "axis": "x", "expected": "plate_w"}`
- **板厚**：用 distance 测顶面（PLANE，法向朝上）到底面（PLANE，法向朝下）的最短距离。不要按 z 坐标去选面，板放在别处也能用。
  例：`{"id": "thickness", "type": "distance", "a": {"kind": "faces", "where": [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]]}, "b": {"kind": "faces", "where": [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]}, "expected": "plate_t"}`
- **孔径**：圆柱面没有半径属性，所以用面积间接测：通孔的侧面积 = π × 孔径 × 板厚。用 count 数出 CYLINDER 面里面积在这个值 ±5% 内的，应当恰好 1 个；孔径偏 20%，面积就超出 ±5%，检查不通过。
  例：`{"id": "hole-dia", "type": "count", "kind": "faces", "expected": 1, "where": [["geom.type", "==", "CYLINDER"], ["geom.area", ">=", "pi * hole_d * plate_t * 0.95"], ["geom.area", "<=", "pi * hole_d * plate_t * 1.05"]]}`
- **孔数**：选择条件同孔径（CYLINDER 面，面积在单个孔的 ±5% 内；圆角的圆柱面面积不一样，一般不会混进来），expected 直接写孔数参数。
  例：`{"id": "hole-count", "type": "count", "kind": "faces", "expected": "hole_n", "where": [["geom.type", "==", "CYLINDER"], ["geom.area", ">=", "pi * hole_d * plate_t * 0.95"], ["geom.area", "<=", "pi * hole_d * plate_t * 1.05"]]}`
- **孔位**：用两个点：孔心处 point_outside（应当没有材料），孔边外 0.5 mm 处 point_inside（应当有材料）。点的坐标可以写参数表达式，z 取板厚的一半。
  例：`{"id": "hole-center-empty", "type": "point_outside", "point": ["hole_x", 0, "plate_t / 2"]}`
  例：`{"id": "hole-edge-solid", "type": "point_inside", "point": ["hole_x + hole_d / 2 + 0.5", 0, "plate_t / 2"]}`
- **槽或缺口宽度**：同样用两个点：缺口一侧的墙内 0.5 mm 处 point_outside，墙外 0.5 mm 处 point_inside。缺口左右对称时测一侧就够；点的另一个坐标要落在缺口的长度范围内。宽度差 1 mm 左右就会被抓到。
  例：`{"id": "slot-empty", "type": "point_outside", "point": ["slot_w / 2 - 0.5", 12, "plate_t / 2"]}`
  例：`{"id": "slot-wall", "type": "point_inside", "point": ["slot_w / 2 + 0.5", 12, "plate_t / 2"]}`
- **圆角半径**：圆角面是 CYLINDER，直棱上 90° 圆角的侧面积 = π ÷ 2 × 半径 × 棱长。用 count 数出面积在这个值 ±5% 内的 CYLINDER 面，应当恰好 1 个。
  例：`{"id": "fillet-r", "type": "count", "kind": "faces", "expected": 1, "where": [["geom.type", "==", "CYLINDER"], ["geom.area", ">=", "pi / 2 * fillet_r * plate_h * 0.95"], ["geom.area", "<=", "pi / 2 * fillet_r * plate_h * 1.05"]]}`
- **倒角尺寸**：倒角面是 PLANE，法向和相邻两面都成 45°（例子里法向 x、y 分量在 0.6 到 0.8 之间，因为 cos45° ≈ 0.707），面积 = √2 × 倒角距离 × 棱长。例子是 +x +y 角上竖直棱的倒角，换位置时改法向条件。
  例：`{"id": "chamfer-c", "type": "count", "kind": "faces", "expected": 1, "where": [["geom.type", "==", "PLANE"], ["geom.normal.x", ">=", 0.6], ["geom.normal.x", "<=", 0.8], ["geom.normal.y", ">=", 0.6], ["geom.normal.y", "<=", 0.8], ["geom.area", ">=", "sqrt(2) * chamfer_c * plate_h * 0.95"], ["geom.area", "<=", "sqrt(2) * chamfer_c * plate_h * 1.05"]]}`
- **两面夹角**：angle 测的是两个平面法向（朝材料外）的夹角，不是两面之间的开口角。例子里斜面（法向朝上偏 +x）和底面（法向朝下）的夹角 = 180° − 斜面倾角；用法向分量的范围把两个面分开。
  例：`{"id": "slope-angle", "type": "angle", "expected": "180 - slope_deg", "a": [["geom.type", "==", "PLANE"], ["geom.normal.x", ">=", 0.1], ["geom.normal.z", ">=", 0.1]], "b": [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]}`

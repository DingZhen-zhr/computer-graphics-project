# SCA 写法补充

下面每条写法都在 SCA 2.2.7 里实际跑通过。参数名（如 base_l）都是需求单里的参数。

## 草图约束与轮廓
- `make_sketch_rsketch(名字, plane=)` → `add_point_rsketch(草图, 点名, u, v)` → `add_line_rsketch(草图, 线名, 起点名, 终点名)`：用草图画任意直线轮廓。plane 只能是 "XY"、"XZ"、"YZ"；XZ 平面上 (u, v) 就是 (x, z)，XY 平面上是 (x, y)。线的两端要写**点的名字**，不能直接写坐标。每次 add 都返回新的草图，要重新赋值给 _s。坐标里可以直接用参数，不用加约束。
  例：`_s = scad.make_sketch_rsketch("profile", plane="XZ"); _pts = [(-base_l / 2, 0), (base_l / 2, 0), (base_l / 2, base_t), (-base_l / 2 + arm_w, base_t), (-base_l / 2 + arm_w, arm_h), (-base_l / 2, arm_h)]`
  例：`for _i, (_u, _v) in enumerate(_pts): _s = scad.add_point_rsketch(_s, f"p{_i}", _u, _v)`
  例：`for _i in range(len(_pts)): _s = scad.add_line_rsketch(_s, f"e{_i}", f"p{_i}", f"p{(_i + 1) % len(_pts)}")`
- `make_face_from_sketch_rface(草图)` 把封闭的轮廓变成面，再用 `extrude_rsolid` 拉伸。XZ 平面的面沿 (0, 1, 0) 拉伸，得到的实体 y 从 0 到 distance，要居中再平移 (0, -distance/2, 0)。**拉伸方向不能在草图平面里**：那样不报错，但得到体积为 0 的实体。
  例：`_face = scad.make_face_from_sketch_rface(_s); _solid = scad.extrude_rsolid(profile=_face, direction=(0, 1, 0), distance=part_w); body = scad.translate_shape(shape=_solid, vector=(0, -part_w / 2, 0))`
- `add_arc_rsketch(草图, 弧名, 起点名, 终点名, 圆心名)`：圆弧，从起点**逆时针**转到终点，三个点都要先用 add_point_rsketch 加好。轮廓里直线和圆弧首尾相接即可。
  例：`_s = scad.add_point_rsketch(_s, "c0", cam_l / 2, 0); _s = scad.add_arc_rsketch(_s, "a0", "p1", "p2", "c0")`

## 抽壳
- `shell_rsolid(solid=, faces_to_remove=, thickness=)`：把实体挖空成薄壁，去掉 faces_to_remove 选中的面（敞口）。**壁厚向里长**，外形尺寸不变；thickness 必须是正数。
  例：`_top = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99))); tray = scad.shell_rsolid(solid=_box, faces_to_remove=_top, thickness=wall)`
- 底厚和侧壁厚不一样时，不用抽壳，用"外形减内腔"：内腔比外形每边小一个壁厚，底面放在 z = 底厚，高度到顶面以上。结果和抽壳一样可控。
  例：`_cavity = scad.make_box_rsolid(width=box_l - 2 * wall, height=box_w - 2 * wall, depth=box_h, bottom_face_center=(0, 0, floor_t)); tray = scad.cut_rsolid(_box, _cavity, skip_non_intersecting=False)`
- 外竖边要圆角时，先圆角、再抽壳：内壁会自动带上对应的圆角。
  例：`_vert = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.z", ">=", box_h / 2 - 0.1), ql.prop("geom.center.z", "<=", box_h / 2 + 0.1))); _round = scad.fillet_rsolid(solid=_box, edges=_vert, radius=corner_r)`

## 扫掠
- `make_segment_redge(start=, end=)`、`make_three_point_arc_redge(start=, middle=, end=)` 画路径的每一段（首尾要相接），再用 `make_wire_from_edges_rwire(edges=[...])` 连成一条路径。圆弧用起点、弧上中间一点、终点三个点确定。
  例：`_c = math.cos(math.radians(45)); _e1 = scad.make_segment_redge(start=(0, 0, 0), end=(0, 0, leg_h)); _e2 = scad.make_three_point_arc_redge(start=(0, 0, leg_h), middle=(bend_r - bend_r * _c, 0, leg_h + bend_r * _c), end=(bend_r, 0, leg_h + bend_r))`
  例：`_e3 = scad.make_segment_redge(start=(bend_r, 0, leg_h + bend_r), end=(bend_r + grip_l, 0, leg_h + bend_r)); _path = scad.make_wire_from_edges_rwire(edges=[_e1, _e2, _e3])`
- `sweep_rsolid(profile=, path=)`：截面沿路径扫出实体。截面放在路径**起点**，法向沿路径起始的方向。拐角要圆滑就在路径里放圆弧段；直接用折线拐弯会得到尖角拼接。
  例：`_profile = scad.make_circle_rface(center=(0, 0, 0), radius=rod_d / 2, normal=(0, 0, 1)); handle = scad.sweep_rsolid(profile=_profile, path=_path)`

## 标准件：齿轮与齿条
- `scad.std.gear.make_spur_gear_rsolid(n_teeth=, module=, gear_height=)`：直齿圆柱齿轮，注意前面是 `scad.std.gear.`。轴线是 z 轴，一个端面在 z=0，向 +z 长 gear_height；齿顶圆直径 = module × (n_teeth + 2)，+x 方向正对一个齿。n_teeth 是整数参数（单位 1）。
  例：`_gear = scad.std.gear.make_spur_gear_rsolid(n_teeth=teeth_n, module=gear_m, gear_height=face_w)`
- 齿轮可以直接和圆柱合并（轮毂），也可以直接减孔（轴孔、减重孔）。
  例：`_hub = scad.make_cylinder_rsolid(radius=hub_d / 2, height=face_w + hub_h, bottom_face_center=(0, 0, 0)); gear = scad.union_rsolid(_gear, _hub)`
- 齿条函数 `scad.std.gear.make_spur_rack_rsolid` 在 SCA 2.2.7 里做出来的实体是**无效的**（"实体有效"这条必做检查过不了，和别的实体合并还会卡住），不要用它。

## 分阶段时的写法
- 每个阶段的最后一个特征，变量就是到这个阶段为止的整个零件；下一个阶段从它接着做。
- 先做好一个孔（或一个筋、一个齿），build 通过后，再用阵列做出其余的。
- 圆角和倒角单独放在最后一个阶段；选边之前先用 probe 打印选中了几条边、各在哪里。
- probe 里量尺寸：体积用 `model.get_volume()`；包围盒用全部顶点坐标的范围（只有平面围成的零件才准）；面数、边数用 `len(ql.faces().resolve(model))`。`brep.inspect_shape_rbrepinspection` 这类检视函数在 probe 里不能用。
  例：`_pts = [v.get_center() for v in ql.vertices().resolve(model)]; _xs = [p.x for p in _pts]; print("体积", round(model.get_volume(), 3), "x 向尺寸", round(max(_xs) - min(_xs), 3))`

## 装配的写法
- 连接点挂在零件上真实存在的一个面或一条边上。两个面贴在一起：两边各选那个平面（朝外的法向），配合写 align 为 opposite；要留缝就写 gap。
  例：{"part": "handle", "connectors": [{"name": "base", "kind": "faces", "where": [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]}]}
- 铰链（转动）：两边各选铰链孔或轴的圆柱面（得到轴线），配合写 align 为 same，关节写 revolute，range 是能转的角度；正负方向不对时把一边的连接点 flip。
  例：{"ground": "body", "mates": [{"id": "lid_hinge", "fixed": "body.hinge_axis", "moving": "lid.hinge_axis", "align": "same"}], "joints": [{"id": "lid_open", "mate": "lid_hinge", "type": "revolute", "range": [0, "lid_max"], "label": "盖子翻开"}]}
- 抽屉（滑动）：抽屉前面板的背面贴在柜子正面（两边各选那个平面，align 为 opposite），关节写 prismatic，direction 是装好时拉出的方向，range 是能拉出的距离。
  例：{"ground": "cabinet", "mates": [{"id": "drawer_in", "fixed": "cabinet.front", "moving": "drawer.panel_back", "align": "opposite"}], "joints": [{"id": "drawer_pull", "mate": "drawer_in", "type": "prismatic", "range": [0, "pull_max"], "direction": [0, -1, 0], "label": "拉出抽屉"}]}
- 齿轮联动：两个齿轮各自绕轴转（两个 revolute 关节），连接点选轴根部的圆形边和齿轮轴孔底部的圆形边，gap 是齿轮下表面离底板的高度；大齿轮转半个齿（angle 写 180 / 齿数）才能和小齿轮的齿对上。couplings 里写 ratio = 被带动的转角 / 带动的转角，外啮合是负数（齿数比取反）。
  例：{"ground": "plate", "mates": [{"id": "pinion_on", "fixed": "plate.shaft_a", "moving": "pinion.bore", "align": "same", "gap": "lift"}, {"id": "gear_on", "fixed": "plate.shaft_b", "moving": "gear.bore", "align": "same", "gap": "lift", "angle": "180 / gear_z"}], "joints": [{"id": "pinion_turn", "mate": "pinion_on", "type": "revolute", "range": [0, 360], "label": "小齿轮转动"}, {"id": "gear_turn", "mate": "gear_on", "type": "revolute", "range": [-360, 360], "label": "大齿轮转动"}], "couplings": [{"driver": "pinion_turn", "driven": "gear_turn", "ratio": "-pinion_z / gear_z", "kind": "gear"}]}

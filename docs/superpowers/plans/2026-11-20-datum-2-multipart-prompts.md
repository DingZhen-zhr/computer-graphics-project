# 3.0 · 计划 2（多零件内核）· 原文照抄内容

本文件中用 ```text、```json 框起来的内容，执行者必须**逐字复制**到对应文件或代码里，不改写、不润色。`<尖括号>` 是运行时填入的内容。这里没有写到的原文，仍以第二版计划 1 的提示词文档 `2026-11-10-caliper-1-kernel-prompts.md` 为准。

---

## 1. 系统提示词的新增两段

写入 `cad_agent/agent/prompts/system_multipart.md`（Task 11），在分阶段流程的系统提示词里接在 `system_v2.md` 后面、`references_index.md` 前面。

```text
## 多个零件的产品
用户要的东西由两个或更多零件组成时（比如盒子和盖子、柜子和抽屉、一对齿轮），按下面做。只有一个零件时，忽略这一节。

1. 澄清时，在需求单里多写三样：
   - parts：每个零件一项，写编号（小写英文，如 body、lid）、名字、材料，以及这个零件由哪些部分组成。
   - 参数：几个零件共用的尺寸（比如盒子的长宽高）不写 part；只属于某一个零件的尺寸，part 写那个零件的编号。
   - motions：每个会动的地方一句话，写清哪个零件、绕哪里转或沿哪个方向滑、动多少，比如"盖子绕后边的铰链向上翻开，0 到 110 度"。不会动就传空数组。
   - relations 里写清每两个相接的零件怎么连：哪里贴在一起、哪根轴穿过哪个孔、留多大的间隙。
2. 用户确认后，一个零件一个零件地做。程序会告诉你现在做哪个零件；对这个零件照常 set_plan、set_checks、upsert_feature、build。每个零件都在它自己的坐标里建模：底面贴 z=0，大致以原点为中心，不用管它装好后在哪里。
3. 一个零件做完（它的全部步骤和最后检查都通过），程序会把它收起来，换到下一个零件。
4. 全部零件做完后，装配：
   a. set_connectors：在每个零件上声明连接点。连接点必须选中零件上真实存在的一个面或一条边（写法和检查的 where 一样）：选圆柱面就得到它的轴线，选平面就得到它的位置和朝外的方向。
   b. set_assembly：写 mates（两个连接点怎么对上）、joints（哪个配合会动、动多少）、couplings（齿轮、皮带这类联动）、ground（固定不动的那个零件）。
   c. set_assembly_checks：写装配和运动的检查。程序会自动加上：每个连接点都选中了真实几何、任意两个零件装好后不穿模、每个会动的地方从头到尾都不碰撞。
   d. build_assembly。
5. 装配没通过时，读返回结果：哪两个零件在哪个位置碰到了、碰到多少，连接点选中了什么。是零件尺寸的问题，就用 select_part 回到那个零件改，改完 build，再 build_assembly；是连接点或配合写错了，就改 set_connectors 或 set_assembly。动起来刚离开装好的位置就碰到，多半是方向反了，先把关节的范围或连接点的方向反过来试，不要先改零件。

## 零件要做得好看、好用
- 倒角、圆角、沉孔这类修饰，用户没提就不加。觉得加了更好看、更好用时，在澄清的提问里问一句（比如"外露的边要不要倒 R2 的圆角？"），用户同意了才写进需求单和计划，放在这个零件的最后一步。不要改用户给的尺寸。
- 壁厚尽量统一；受力的地方加筋或加厚；两个零件之间留合理的间隙（滑动的地方单边 0.5 到 1 毫米，转动的轴和孔单边 0.2 到 0.5 毫米）；会动的零件要给它留出动的空间。
- 每个零件都要写材料。没有特别要求时，外壳用 ABS 塑料，受力的金属件用铝或不锈钢，手接触的地方可以用橡胶。
- 用户没给比例时，参考常见的同类产品定建议值，不要做成一个方块了事。
```

---

## 2. 材料表

写入 `cad_agent/product/materials.py`（Task 3）的 `MATERIALS`：键、中文名、默认颜色、界面渲染用的质感。顺序照抄。

```json
[
  {"key": "abs", "name": "ABS 塑料", "color": "#3A3F47", "finish": "matte"},
  {"key": "aluminum", "name": "铝", "color": "#C9CDD3", "finish": "metal"},
  {"key": "anodized", "name": "阳极氧化铝", "color": "#4767E8", "finish": "metal"},
  {"key": "steel", "name": "不锈钢", "color": "#B8BDC4", "finish": "polished"},
  {"key": "brass", "name": "黄铜", "color": "#C9A24A", "finish": "polished"},
  {"key": "rubber", "name": "橡胶", "color": "#1E1F22", "finish": "matte"},
  {"key": "wood", "name": "木头", "color": "#B98A5A", "finish": "matte"}
]
```

---

## 3. 工具说明

由 `scripts/gen_staged_specs.py` 一起生成进 `cad_agent/staged/specs.py`（Task 9）。第二版的 12 个工具里，**update_brief 换成本节的版本**，其余 11 个不变；在末尾追加本节的 5 个新工具，顺序：select_part、set_connectors、set_assembly、set_assembly_checks、build_assembly。

### update_brief（替换第二版的同名工具）

```json
{
  "name": "update_brief",
  "description": "修改需求单。只传要改的部分：set_params 里的同名参数会被覆盖；features、relations、parts、motions、open_questions 只要传了就整体替换。返回改动列表，以及现在能不能建模。要提问时，在同一次回复里先调用本工具，再调用 ask_user。需求单完整、没有待问问题、位置关系写全时，程序会自动请用户确认。交付后只改已有参数的数值时，程序会自动从头重新验证并交付。产品由多个零件组成时，parts 写每个零件，motions 写每个会动的地方。",
  "parameters": {
    "type": "object",
    "properties": {
      "part": {
        "type": "object",
        "properties": {
          "name": {"type": "string", "description": "零件或产品的名称"},
          "purpose": {"type": "string", "description": "用途，一句话"}
        }
      },
      "set_params": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string", "description": "小写英文加下划线，如 phone_w"},
            "value": {"type": "number"},
            "unit": {"type": "string", "enum": ["mm", "deg", "1"]},
            "source": {"type": "string", "enum": ["user", "suggested"], "description": "user：用户给出或明确同意；suggested：你自己定的"},
            "note": {"type": "string", "description": "这个参数的含义；suggested 时写上理由"},
            "part": {"type": "string", "description": "可选：只属于某一个零件时，写零件编号；几个零件共用就不写"}
          },
          "required": ["name", "value", "unit", "source", "note"]
        }
      },
      "remove_params": {"type": "array", "items": {"type": "string"}},
      "features": {"type": "array", "items": {"type": "string"}, "description": "只有一个零件时：零件由哪些部分组成，每项一个部件的名字和大致位置"},
      "relations": {"type": "array", "items": {"type": "string"}, "description": "各部分或各零件怎么相接，每项一句话，要原样写出两边的名字"},
      "parts": {
        "type": "array",
        "description": "产品由多个零件组成时才写：每个零件一项",
        "items": {
          "type": "object",
          "properties": {
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$", "description": "零件编号，小写英文，如 lid"},
            "name": {"type": "string", "description": "零件名字，如 盖子"},
            "material": {"type": "string", "enum": ["abs", "aluminum", "anodized", "steel", "brass", "rubber", "wood"]},
            "color": {"type": "string", "description": "可选：颜色，如 #4767E8；不写就用材料的默认颜色"},
            "features": {"type": "array", "items": {"type": "string"}, "description": "这个零件由哪些部分组成"}
          },
          "required": ["id", "name", "material", "features"]
        }
      },
      "motions": {"type": "array", "items": {"type": "string"}, "description": "每个会动的地方一句话：哪个零件、绕哪里转或沿哪个方向滑、动多少；不会动就传空数组"},
      "open_questions": {"type": "array", "items": {"type": "string"}, "description": "还需要问用户的问题；没有就传空数组"}
    }
  }
}
```

### select_part

```json
{
  "name": "select_part",
  "description": "切换到某个零件，之后的 set_plan、set_checks、upsert_feature、remove_feature、build、probe 都作用于这个零件。一般不用调用：程序会自动带你做下一个零件。装配时发现某个零件要改，用它回到那个零件。",
  "parameters": {
    "type": "object",
    "properties": {"part": {"type": "string", "description": "零件编号"}},
    "required": ["part"]
  }
}
```

### set_connectors

```json
{
  "name": "set_connectors",
  "description": "整体替换某个零件的连接点。每个连接点必须选中这个零件上恰好一个真实的面或边：选圆柱面（geom.type == CYLINDER）得到它的轴线，原点在圆柱面中心；选平面（geom.type == PLANE）得到它的中心和朝外的法向；选圆形的边（geom.type == CIRCLE）得到圆心和圆所在平面的法向。可以用 offset 沿连接点自己的方向再移动一段（表达式可以用参数名）；flip 为 true 时方向反过来。",
  "parameters": {
    "type": "object",
    "properties": {
      "part": {"type": "string", "description": "零件编号"},
      "connectors": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$", "description": "连接点名字，如 hinge_axis"},
            "kind": {"type": "string", "enum": ["faces", "edges"]},
            "where": {"type": "array", "items": {"type": "array"}, "description": "选择条件，写法同 set_checks"},
            "offset": {"type": ["number", "string"], "description": "可选：沿连接点方向移动多少，默认 0"},
            "flip": {"type": "boolean", "description": "可选：方向反过来"}
          },
          "required": ["name", "kind", "where"]
        }
      }
    },
    "required": ["part", "connectors"]
  }
}
```

### set_assembly

```json
{
  "name": "set_assembly",
  "description": "整体替换装配关系。ground 是固定不动的零件。mates 的每一项把两个连接点对上：align 为 same 时两个方向相同，opposite 时相反（两个面贴在一起用 opposite）；gap 是沿方向留的距离；angle 是绕方向转多少度。连接点写成 零件编号.连接点名字。每个零件除 ground 外都要被某一个配合连到已经装好的零件上，配合之间不能连成一圈。joints 声明某个配合会动：revolute 绕配合的方向转，prismatic 沿 direction 滑；range 是可以动的范围；label 是给用户看的名字，如 盖子翻开。couplings 让一个关节带动另一个：ratio 是被带动的关节动多少 / 带动的关节动多少（齿轮外啮合是负数）。",
  "parameters": {
    "type": "object",
    "properties": {
      "ground": {"type": "string", "description": "固定不动的零件编号"},
      "mates": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
            "fixed": {"type": "string", "description": "已经装好的那一边的连接点，如 body.hinge_axis"},
            "moving": {"type": "string", "description": "被装上去的那一边的连接点，如 lid.hinge_axis"},
            "align": {"type": "string", "enum": ["same", "opposite"]},
            "gap": {"type": ["number", "string"], "description": "可选，默认 0"},
            "angle": {"type": ["number", "string"], "description": "可选，默认 0，单位度"}
          },
          "required": ["id", "fixed", "moving", "align"]
        }
      },
      "joints": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
            "mate": {"type": "string", "description": "在哪个配合上动"},
            "type": {"type": "string", "enum": ["revolute", "prismatic"]},
            "range": {"type": "array", "items": {"type": ["number", "string"]}, "minItems": 2, "maxItems": 2},
            "direction": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "description": "prismatic 才要：装好时在世界坐标里滑动的方向"},
            "label": {"type": "string", "description": "给用户看的名字"}
          },
          "required": ["id", "mate", "type", "range", "label"]
        }
      },
      "couplings": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "driver": {"type": "string", "description": "带动的关节"},
            "driven": {"type": "string", "description": "被带动的关节"},
            "ratio": {"type": ["number", "string"]},
            "kind": {"type": "string", "enum": ["gear", "belt"]}
          },
          "required": ["driver", "driven", "ratio", "kind"]
        }
      }
    },
    "required": ["ground", "mates"]
  }
}
```

### set_assembly_checks

```json
{
  "name": "set_assembly_checks",
  "description": "整体替换装配和运动的检查（零件自己的检查仍然用 set_checks）。程序会自动加上：每个连接点都选中了真实几何、任意两个零件装好后不穿模、每个会动的地方从头到尾都不碰撞，不用你写。\ninterference：零件 a 和 b 装好后重叠的体积不超过 tol（默认 0.01 立方毫米）。\nclearance：a 和 b 之间最短距离，op 默认 >=，要写 expected。\ncoaxial：a、b 各写 {\"part\": 零件编号, \"kind\": ..., \"where\": [...]}，各选中一个圆柱面，量两条轴线之间的距离和夹角；expected 是距离，默认 0，tol 默认 0.05。\nflush：a、b 各选中一个平面，量两个平面的距离和夹角，expected 是距离。\nmotion_clear：关节 joint 从头到尾，零件 a 和 b 在每个取样位置都不穿模；不写 a、b 就是所有零件两两之间。\nreach：关节 joint 能动到 value，中间不出错。\nratio：关节 driven 动的量 / 关节 driver 动的量，等于 expected。\n装好后的坐标是 ground 零件的坐标。",
  "parameters": {
    "type": "object",
    "properties": {
      "checks": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": {"type": "string"},
            "type": {"type": "string", "enum": ["interference", "clearance", "coaxial", "flush", "motion_clear", "reach", "ratio"]},
            "a": {}, "b": {},
            "joint": {"type": "string"}, "driver": {"type": "string"}, "driven": {"type": "string"},
            "value": {"type": ["number", "string"]},
            "expected": {"type": ["number", "string"]},
            "op": {"type": "string", "enum": ["==", ">=", "<="]},
            "tol": {"type": "number"}
          },
          "required": ["id", "type"]
        }
      }
    },
    "required": ["checks"]
  }
}
```

### build_assembly

```json
{
  "name": "build_assembly",
  "description": "按当前的零件、连接点、装配关系和检查，把产品装起来并检查；有会动的地方时，每个关节从头到尾取若干位置，每个位置都检查碰撞。全部零件都做完才能调用。全过之后程序会做最后检查（把每个尺寸改一改，确认检查真的管得住它），通过就自动交付。返回：连接点各选中了什么；没通过的检查；碰撞发生在哪个关节的哪个位置、哪两个零件、重叠多少；下一步该做什么。",
  "parameters": {"type": "object", "properties": {}}
}
```

---

## 4. 程序生成的消息

### 4.1 换到下一个零件

一个零件做完时，本轮里这个零件的来往换成一条 user 消息（Task 10）：

```text
【零件已做完（程序生成）】<编号> <名字>
步骤：<每一步的标题，用顿号连接>
检查：<n> 项，全部通过。外形：<sx> × <sy> × <sz>
```

后面还有零件时，再空一行加：

```text
现在做零件 <编号> <名字>。先用 set_plan 把它拆成几步。
```

全部零件都做完时，改成：

```text
全部零件都做完了。现在装配：先用 set_connectors 给每个零件声明连接点，再 set_assembly、set_assembly_checks，最后 build_assembly。
```

### 4.2 关卡报错

都以 `{"error": "<原文>"}` 返回，不计失败次数。

还有零件没做完时调用 build_assembly：

```text
还有零件没做完：<编号，用顿号连接>。全部零件做完才能装配。
```

连接点没有选中恰好一个几何：

```text
零件 <编号> 的连接点 <名字> 选中了 <n> 个几何，要恰好 1 个。改一下 where 的条件。
```

连接点选中的几何类型不对：

```text
零件 <编号> 的连接点 <名字> 选中的是 <类型>，只能是圆柱面、平面或圆形的边。
```

配合连成了一圈或者有零件没连上：

```text
装配关系有问题：<具体原因>。除了 ground，每个零件都要被恰好一个配合连到已经装好的零件上，不能连成一圈。
```

### 4.3 build_assembly 的 hint

按下表从上到下取第一条符合的：

| 情况 | hint |
|---|---|
| 运行出错 | 旧流程"出错位置不在某个特征里"的原文 |
| 有连接点没选中真实几何 | 见下面 A |
| 装好后有零件穿模 | 见下面 B |
| 运动中碰撞 | 见下面 C |
| 有别的检查没通过 | 旧流程"有没通过的检查"的原文 |
| 最后检查：有尺寸没被管住 | 第二版提示词文档 7.2 的 text 块 B |
| 全部通过 | 旧流程"全部通过"的原文 |

A：

```text
有连接点没有挂在真实的几何上。看 connectors 里每个连接点选中了什么，改 set_connectors 的 where。
```

B：

```text
装好后零件 <a> 和 <b> 重叠了 <v> 立方毫米。看是哪边的尺寸或位置不对：尺寸不对就用 select_part 回去改那个零件；位置不对就改 set_connectors 或 set_assembly。
```

C：

```text
<关节名字> 动到 <value><单位> 时，零件 <a> 和 <b> 碰到了，重叠 <v> 立方毫米。给它们留出动的空间：加大间隙、缩短会碰到的部分，或者改动的范围（改范围要先问用户）。
```

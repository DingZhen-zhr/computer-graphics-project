"""分阶段流程的工具说明（OpenAI function 格式）。

由 scripts/gen_staged_specs.py 生成，不要手改。内容逐字取自第二版提示词文档第 6 节和 1.1 版提示词文档第 4 节；
update_brief 和末尾 5 个取自 3.0 计划 2 提示词文档第 3 节；set_checks 按第 6 节写的拼法算出。tests/test_staged_tools.py 会逐项比对。
"""

from __future__ import annotations

import json

_RAW: list[str] = [
    r'''{
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
}''',
    r'''{
  "name": "ask_user",
  "description": "向用户提问，然后结束本轮，等用户回答。用在关键尺寸缺失或需求矛盾时。一次把问题问全，最多 5 个。",
  "parameters": {
    "type": "object",
    "properties": {
      "questions": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5, "description": "每个问题一句话，说明为什么要问；有建议值时附上"}
    },
    "required": ["questions"]
  }
}''',
    r'''{
  "name": "request_confirmation",
  "description": "把当前需求单展示给用户，请用户确认，然后结束本轮。一般不用调用：需求单完整、没有待问问题时，程序会自动请用户确认。用户确认之后才能建模。",
  "parameters": {"type": "object", "properties": {}}
}''',
    r'''{
  "name": "set_plan",
  "description": "提交或修改分阶段计划。用户确认需求单之后、写任何特征之前必须先调用。每次传全部阶段，按先后顺序；程序按顺序给它们编号 s1、s2……。已经通过的阶段必须原样保留在前面，不能改；没通过的阶段可以改、可以删、可以在末尾追加。只说每个阶段做什么、做完后零件上多了什么，不写代码。",
  "parameters": {
    "type": "object",
    "properties": {
      "stages": {
        "type": "array",
        "minItems": 1,
        "maxItems": 12,
        "items": {
          "type": "object",
          "properties": {
            "title": {"type": "string", "description": "这个阶段做什么，几个字，如：底板和安装孔"},
            "done_when": {"type": "string", "description": "做完后零件上多了什么，一句话，能量出来，如：有一块长 base_l 宽 base_w 的底板，四角各有一个通孔"}
          },
          "required": ["title", "done_when"]
        }
      }
    },
    "required": ["stages"]
  }
}''',
    r'''{
  "name": "upsert_feature",
  "description": "新增一个特征，或替换同名特征（替换时位置和所属阶段不变）。新增的特征属于当前阶段，默认放在这个阶段的最后，传 before 可以插到同一阶段的某个特征前面。当前阶段还没有检查时不能新增特征，要先 set_checks。替换已通过阶段里的特征时，那个阶段和它后面的阶段都会变回未通过。code 只写这个特征的建模代码：最后把结果赋给与 slug 同名的变量（短横线换成下划线）；临时变量以下划线开头；不要 import，scad、ql、math 可以直接用；直接使用需求单里的参数名。可以在同一次回复里连续调用多次，最后再调用 build。",
  "parameters": {
    "type": "object",
    "properties": {
      "slug": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$", "description": "特征名，小写英文和短横线，如 bolt-holes"},
      "role": {"type": "string", "enum": ["build", "add", "subtract", "intersect", "modify", "pattern"]},
      "code": {"type": "string", "description": "这个特征的 Python 代码"},
      "before": {"type": "string", "description": "可选：插到同一阶段里这个 slug 的特征前面"}
    },
    "required": ["slug", "role", "code"]
  }
}''',
    r'''{
  "name": "remove_feature",
  "description": "删除一个特征。后面的特征如果用到了它的变量，build 时会报错，需要一起修改。",
  "parameters": {
    "type": "object",
    "properties": {"slug": {"type": "string"}},
    "required": ["slug"]
  }
}''',
    r'''{
  "name": "set_checks",
  "description": "整体替换某一个阶段的检查项：stage 写阶段编号（如 s2），checks 写这个阶段的全部检查。先写检查，再写这个阶段的特征。每条检查可以带 holds：from_here（默认）表示从这个阶段起一直成立，后面每个阶段和终检都会重新测；here_only 表示只在这个阶段结束时成立。改动已通过阶段的检查时，那个阶段和它后面的阶段都会变回未通过。程序会自动加上 3 条必做检查，不用你写。每个用户参数至少要被一条 from_here 的检查用到；不知道怎么检查时，照速查表“检查写法”一节写。\n表达式里可以用：参数名、数字、+ - * / **、括号、sin cos tan asin acos atan radians degrees sqrt abs min max、pi。\nwhere 是条件列表，每条写成 [属性, 比较符, 值]，条件之间是“并且”。属性有：geom.type（值写 PLANE、CYLINDER 等大写字样）、geom.center.x / y / z、geom.normal.x / y / z（只有平面有）、geom.area（面）、geom.length（边）。比较符有：== != >= <= > <。\n各类型的写法：\nbbox：整体在 axis（x、y、z）方向的尺寸；要写 axis、expected，tol 可选（默认 0.1）。\ncount：满足 where 的面（kind=faces）或边（kind=edges）有几个；要写 kind、where、expected，op 可选（== >= <=，默认 ==）。\nangle：a、b 各是一组 where，各取选中面里面积最大的平面，测两者法向的夹角（0 到 180 度）；要写 a、b、expected，tol 可选（默认 0.5）。\npoint_inside / point_outside：点 point=[x, y, z] 在材料里 / 不在材料里；只写 point。\ndistance：a、b 各是 {\"kind\": ..., \"where\": [...]}，测两组几何之间的最短距离；要写 a、b、expected，op 可选（默认 ==），tol 可选。\nvolume：整体体积；要写 expected，rel_tol 可选（默认 0.01，即 1%）。",
  "parameters": {
    "type": "object",
    "properties": {
      "stage": {
        "type": "string",
        "description": "阶段编号，如 s1"
      },
      "checks": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": {
              "type": "string",
              "description": "检查名，小写英文，如 tilt-angle"
            },
            "type": {
              "type": "string",
              "enum": [
                "bbox",
                "count",
                "angle",
                "point_inside",
                "point_outside",
                "distance",
                "volume"
              ]
            },
            "axis": {
              "type": "string",
              "enum": [
                "x",
                "y",
                "z"
              ]
            },
            "kind": {
              "type": "string",
              "enum": [
                "faces",
                "edges"
              ]
            },
            "where": {
              "type": "array",
              "items": {
                "type": "array"
              }
            },
            "a": {},
            "b": {},
            "point": {
              "type": "array",
              "items": {
                "type": [
                  "number",
                  "string"
                ]
              },
              "minItems": 3,
              "maxItems": 3
            },
            "expected": {
              "type": [
                "number",
                "string"
              ]
            },
            "op": {
              "type": "string",
              "enum": [
                "==",
                ">=",
                "<="
              ]
            },
            "tol": {
              "type": "number"
            },
            "rel_tol": {
              "type": "number"
            },
            "holds": {
              "type": "string",
              "enum": [
                "from_here",
                "here_only"
              ]
            }
          },
          "required": [
            "id",
            "type"
          ]
        }
      }
    },
    "required": [
      "stage",
      "checks"
    ]
  }
}''',
    r'''{
  "name": "build",
  "description": "从当前阶段开始验证：把到这个阶段为止的特征拼成模型，运行并检查。通过就进入下一个阶段；下一个阶段已经写好特征和检查时，程序接着往后验证。最后一个阶段通过后，程序自动做终检（每个用户参数都有检查、把每个用户参数改掉 20% 后至少有一条检查不通过），终检通过就自动交付。写完检查和特征后，在同一次回复里最后调用它；同一次回复里前面的调用出错时，它不会运行，也不算失败。返回内容：是否可以交付；现在停在哪个阶段、这次新通过了哪些阶段；出错时是哪个特征、什么错误；没通过的检查和详情；终检的结果；下一步该做什么。",
  "parameters": {"type": "object", "properties": {}}
}''',
    r'''{
  "name": "inspect",
  "description": "查当前模型里满足条件的面或边（最多返回 30 个），每个给出类型、中心、面积或长度、法向（只有平面有）；同时给出整体包围盒、体积、面数、边数。用来排查没通过的检查，或弄清几何实际在哪里。",
  "parameters": {
    "type": "object",
    "properties": {
      "kind": {"type": "string", "enum": ["faces", "edges"]},
      "where": {"type": "array", "items": {"type": "array"}, "description": "条件列表，写法同 set_checks；不写就是全部"}
    },
    "required": ["kind"]
  }
}''',
    r'''{
  "name": "api_help",
  "description": "查 SCA 某个函数的用法：函数定义、参数、说明。name 写函数名，如 make_box_rsolid。名字不对时会返回几个相近的名字。",
  "parameters": {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"]
  }
}''',
    r'''{
  "name": "probe",
  "description": "试一小段代码，看它打印的结果，不会改动模型。用来确认某个函数怎么用、某个操作能不能做、某个条件选中了哪些面和边。代码里可以用需求单里的参数名、前面所有特征的变量名，以及 model（到当前阶段为止的整个零件；还没有任何特征时是 None）。用 print 输出你想看的东西，最多返回 2000 个字符；不要打印整个实体，只打印数量、尺寸、坐标这类小的事实。不要 import。每个阶段最多用 10 次，不算失败次数。",
  "parameters": {
    "type": "object",
    "properties": {
      "code": {"type": "string", "description": "要试的 Python 代码"}
    },
    "required": ["code"]
  }
}''',
    r'''{
  "name": "read_reference",
  "description": "读一篇 SCA 官方的建模文档（英文）。name 只能取系统提示词“文档目录”里列出的名字。不传 section 时，返回这篇文档的各节标题和开头一段；传 section（节标题的原文）时，返回那一节的全文。",
  "parameters": {
    "type": "object",
    "properties": {
      "name": {"type": "string"},
      "section": {"type": "string", "description": "可选：节标题的原文，如 Boolean discipline"}
    },
    "required": ["name"]
  }
}''',
    r'''{
  "name": "select_part",
  "description": "切换到某个零件，之后的 set_plan、set_checks、upsert_feature、remove_feature、build、probe 都作用于这个零件。一般不用调用：程序会自动带你做下一个零件。装配时发现某个零件要改，用它回到那个零件。",
  "parameters": {
    "type": "object",
    "properties": {"part": {"type": "string", "description": "零件编号"}},
    "required": ["part"]
  }
}''',
    r'''{
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
}''',
    r'''{
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
}''',
    r'''{
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
}''',
    r'''{
  "name": "build_assembly",
  "description": "按当前的零件、连接点、装配关系和检查，把产品装起来并检查；有会动的地方时，每个关节从头到尾取若干位置，每个位置都检查碰撞。全部零件都做完才能调用。全过之后程序会做最后检查（把每个尺寸改一改，确认检查真的管得住它），通过就自动交付。返回：连接点各选中了什么；没通过的检查；碰撞发生在哪个关节的哪个位置、哪两个零件、重叠多少；下一步该做什么。",
  "parameters": {"type": "object", "properties": {}}
}''',
]

TOOL_SPECS_V2: list[dict] = [{"type": "function", "function": json.loads(raw)} for raw in _RAW]
TOOL_NAMES_V2: list[str] = [spec["function"]["name"] for spec in TOOL_SPECS_V2]
# 需求单不能建模时只给这几个
PRE_CONFIRM_TOOLS_V2: list[str] = ["update_brief", "ask_user", "request_confirmation", "api_help", "read_reference"]

"""分阶段流程的工具说明（OpenAI function 格式）。

由 scripts/gen_staged_specs.py 生成，不要手改。内容逐字取自第二版提示词文档第 6 节和 1.1 版提示词文档第 4 节；
set_checks 按第 6 节写的拼法算出。tests/test_staged_tools.py 会逐项比对。
"""

from __future__ import annotations

import json

_RAW: list[str] = [
    r'''{
  "name": "update_brief",
  "description": "修改需求单。只传要改的部分：set_params 里的同名参数会被覆盖；features、relations 和 open_questions 只要传了就整体替换。返回改动列表，以及现在能不能建模。要提问时，在同一次回复里先调用本工具，再调用 ask_user。需求单完整、没有待问问题、位置关系写全时，程序会自动请用户确认。交付后只改已有参数的数值时，程序会自动从第一个阶段起重新验证并交付。",
  "parameters": {
    "type": "object",
    "properties": {
      "part": {
        "type": "object",
        "properties": {
          "name": {"type": "string", "description": "零件名称"},
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
            "note": {"type": "string", "description": "这个参数的含义；suggested 时写上理由"}
          },
          "required": ["name", "value", "unit", "source", "note"]
        }
      },
      "remove_params": {"type": "array", "items": {"type": "string"}},
      "features": {"type": "array", "items": {"type": "string"}, "description": "零件由哪些部分组成，每项是一个部件的名字和大致位置，如：底部托唇"},
      "relations": {"type": "array", "items": {"type": "string"}, "description": "各部分怎么相接，每项一句话，要原样写出两个部分的名字，如：立板的下端和底板的一端重叠，外侧面和底板的端面平齐"},
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
]

TOOL_SPECS_V2: list[dict] = [{"type": "function", "function": json.loads(raw)} for raw in _RAW]
TOOL_NAMES_V2: list[str] = [spec["function"]["name"] for spec in TOOL_SPECS_V2]
# 需求单不能建模时只给这几个
PRE_CONFIRM_TOOLS_V2: list[str] = ["update_brief", "ask_user", "request_confirmation", "api_help", "read_reference"]

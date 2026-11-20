"""评测任务的分组（从 run.py 拆出来；run.py 照样能导入这些名字）。"""

from __future__ import annotations

ALL_TASKS = ["phone_stand", "flange", "l_bracket"]
HOLDOUT_TASKS: list[str] = ["enclosure", "stepped_shaft"]  # 留出任务：只用来测，不许为它们调提示词
MEDIUM_TASKS = ["bearing_block", "battery_box", "spur_gear"]   # 第二版：中等
HARD_TASKS = ["heatsink", "tee_fitting", "bracket_arm"]        # 第二版：困难
MULTI_TASKS = ["toolbox", "drawer_cabinet", "gear_pair"]         # 3.0：多零件、会动
TASK_SETS: dict[str, list[str]] = {
    "dev": ALL_TASKS, "holdout": HOLDOUT_TASKS, "all": ALL_TASKS + HOLDOUT_TASKS,
    "medium": MEDIUM_TASKS, "hard": HARD_TASKS, "v2": ALL_TASKS + HOLDOUT_TASKS + MEDIUM_TASKS + HARD_TASKS,
    "multi": MULTI_TASKS, "v3": ALL_TASKS + HOLDOUT_TASKS + MEDIUM_TASKS + HARD_TASKS + MULTI_TASKS,
}
# 3.0 计划 4：开发 10 个、留出 4 个（留出任务的对话记录不读，不许为它们调提示词）
V3_DEV = ["phone_stand", "flange", "l_bracket", "enclosure", "bearing_block", "spur_gear", "heatsink", "tee_fitting", "toolbox", "drawer_cabinet"]
V3_HOLDOUT = ["stepped_shaft", "battery_box", "bracket_arm", "gear_pair"]
TASK_SETS.update({"v3dev": V3_DEV, "v3holdout": V3_HOLDOUT, "v3all": V3_DEV + V3_HOLDOUT})

"""第二版的六个中等和困难评测任务：任务集合、能读入、验收数字和计划一致（第二版计划 1 Task 13）。"""

import pytest

from benchmarks.run import ALL_TASKS, HARD_TASKS, HOLDOUT_TASKS, MEDIUM_TASKS, TASK_SETS, load_task

NEW = ["bearing_block", "battery_box", "spur_gear", "heatsink", "tee_fitting", "bracket_arm"]


def by_id(task: dict, stage: str) -> dict:
    return {c["id"]: c for c in task["acceptance"][stage]}


def points(task: dict, stage: str, kind: str) -> list:
    return [c["point"] for c in task["acceptance"][stage] if c["type"] == f"point_{kind}"]


def ids(task: dict, stage: str, prefix: str) -> list[str]:
    return [c["id"] for c in task["acceptance"][stage] if c["id"].startswith(prefix)]


def sizes(task: dict, stage: str) -> list:
    s = by_id(task, stage)
    return [(s[k]["expected"], s[k]["tol"], s[k]["axis"]) for k in ("size-x", "size-y", "size-z")]


def test_new_task_sets():
    assert MEDIUM_TASKS == ["bearing_block", "battery_box", "spur_gear"]
    assert HARD_TASKS == ["heatsink", "tee_fitting", "bracket_arm"]
    assert TASK_SETS["medium"] == MEDIUM_TASKS and TASK_SETS["hard"] == HARD_TASKS
    assert TASK_SETS["v2"] == ALL_TASKS + HOLDOUT_TASKS + NEW
    assert TASK_SETS["dev"] == ["phone_stand", "flange", "l_bracket"]
    assert TASK_SETS["holdout"] == ["enclosure", "stepped_shaft"]
    assert TASK_SETS["all"] == ["phone_stand", "flange", "l_bracket", "enclosure", "stepped_shaft"]


@pytest.mark.parametrize("name", NEW)
def test_new_tasks_load(name):
    task = load_task(name)
    assert task["id"] == name and task["max_user_turns"] == 14 and len(task["modifications"]) == 1
    assert list(task["acceptance"]) == ["after_initial", "after_mod_1"]
    for stage in task["acceptance"]:
        assert ids(task, stage, "in-") == [f"in-{i}" for i in range(1, len(ids(task, stage, "in-")) + 1)]
        assert ids(task, stage, "out-") == [f"out-{i}" for i in range(1, len(ids(task, stage, "out-")) + 1)]


def test_bearing_block_acceptance_numbers():
    t = load_task("bearing_block")
    assert t["initial"] == "做一个轴承座" and t["modifications"] == ["轴孔直径改成 30 mm"]
    for stage in ("after_initial", "after_mod_1"):
        assert sizes(t, stage) == [(100, 0.5, "x"), (40, 0.5, "y"), (65, 0.5, "z")]
    assert points(t, "after_initial", "inside") == [[0, 0, 5], [45, 0, 5], [10, 0, 60], [20, 0, 20], [48, 18, 5], [13.5, 0, 40]]
    assert points(t, "after_initial", "outside") == [[0, 0, 40], [38, 0, 5], [0, 0, 60], [40, 0, 30], [49.5, 19.5, 5]]
    assert points(t, "after_mod_1", "inside") == [[0, 0, 5], [45, 0, 5], [10, 0, 60], [20, 0, 20], [48, 18, 5], [16.5, 0, 40]]
    assert points(t, "after_mod_1", "outside") == [[0, 0, 40], [38, 0, 5], [0, 0, 60], [40, 0, 30], [49.5, 19.5, 5], [13.5, 0, 40]]


def test_battery_box_acceptance_numbers():
    t = load_task("battery_box")
    assert t["initial"] == "做一个装两节电池的小盒子" and t["modifications"] == ["安装柱的高度改成 15 mm，孔深不变"]
    for stage in ("after_initial", "after_mod_1"):
        assert sizes(t, stage) == [(90, 0.5, "x"), (60, 0.5, "y"), (25, 0.5, "z")]
    assert points(t, "after_initial", "inside") == [[0, 0, 1], [44, 0, 10], [0, 10, 12], [39, 24, 10], [41.5, 24, 20], [-44, 0, 20]]
    assert points(t, "after_initial", "outside") == [[20, 0, 12], [44, 0, 20], [39, 24, 18], [-20, 0, 12]]
    assert points(t, "after_mod_1", "inside") == [[0, 0, 1], [44, 0, 10], [0, 10, 12], [39, 24, 5], [41.5, 24, 15], [-44, 0, 20]]
    assert points(t, "after_mod_1", "outside") == [[20, 0, 12], [44, 0, 20], [39, 24, 10], [41.5, 24, 20], [-20, 0, 12]]


def test_spur_gear_acceptance_numbers():
    t = load_task("spur_gear")
    assert t["initial"] == "做一个直齿轮" and t["modifications"] == ["减重孔改成 4 个"]
    for stage in ("after_initial", "after_mod_1"):
        assert sizes(t, stage) == [(64, 1.0, "x"), (64, 1.0, "y"), (20, 0.5, "z")]
    assert points(t, "after_initial", "inside") == [[8, 0, 6], [10, 0, 16], [26, 0, 6], [0, 7.5, 6], [17.32, 10, 6], [0, 20, 6]]
    assert points(t, "after_initial", "outside") == [[0, 0, 10], [20, 0, 6], [0, 5.8, 10], [15, 0, 16], [10, 17.32, 6]]
    assert points(t, "after_mod_1", "inside") == [[8, 0, 6], [10, 0, 16], [26, 0, 6], [0, 7.5, 6], [10, 17.32, 6], [17.32, 10, 6]]
    assert points(t, "after_mod_1", "outside") == [[0, 0, 10], [20, 0, 6], [0, 5.8, 10], [15, 0, 16], [0, 20, 6]]


def test_heatsink_acceptance_numbers():
    t = load_task("heatsink")
    assert t["initial"] == "做一个铝散热器" and t["modifications"] == ["鳍片改成 11 片，最外面两片的位置不变"]
    for stage, n in (("after_initial", 13), ("after_mod_1", 15)):
        assert sizes(t, stage) == [(80, 0.5, "x"), (60, 0.5, "y"), (30, 0.5, "z")]
        fin = by_id(t, stage)["fin-tops"]
        assert fin["type"] == "count" and fin["kind"] == "faces" and fin["expected"] == n
        assert fin["where"] == [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99], ["geom.center.z", ">=", 29.9]]
    assert points(t, "after_initial", "inside") == [[0, 0, 3], [0, 0, 20], [9, 0, 20], [20, 26, 20], [38.5, 28.5, 3], [36, 0, 20]]
    assert points(t, "after_initial", "outside") == [[4.5, 0, 20], [0, 25, 20], [20, 26, 26], [34, 26, 3], [39.5, 29.5, 3], [38.5, 0, 20]]
    assert points(t, "after_mod_1", "inside") == [[0, 0, 3], [0, 0, 20], [7.2, 0, 20], [20, 26, 20], [38.5, 28.5, 3], [36, 0, 20]]
    assert points(t, "after_mod_1", "outside") == [[4.5, 0, 20], [0, 25, 20], [20, 26, 26], [34, 26, 3], [39.5, 29.5, 3], [9, 0, 20]]


def test_tee_fitting_acceptance_numbers():
    t = load_task("tee_fitting")
    assert t["initial"] == "做一个带法兰的三通管接头" and t["modifications"] == ["支管的内径改成 24 mm"]
    for stage in ("after_initial", "after_mod_1"):
        assert sizes(t, stage) == [(120, 0.5, "x"), (70, 0.5, "y"), (85, 0.5, "z")]
    assert points(t, "after_initial", "inside") == [[0, 17.5, 35], [12.5, 0, 60], [58, 30, 35], [20, 0, 81], [-58, -30, 35], [11, 0, 60]]
    assert points(t, "after_initial", "outside") == [[0, 0, 35], [0, 0, 60], [58, 19.8, 54.8], [15.56, 15.56, 81], [30, 0, 60], [0, 0, 52]]
    assert points(t, "after_mod_1", "inside") == [[0, 17.5, 35], [13.5, 0, 60], [58, 30, 35], [20, 0, 81], [-58, -30, 35]]
    assert points(t, "after_mod_1", "outside") == [[0, 0, 35], [0, 0, 60], [58, 19.8, 54.8], [15.56, 15.56, 81], [30, 0, 60], [0, 0, 52],
                                                   [11, 0, 60]]


def test_bracket_arm_acceptance_numbers():
    t = load_task("bracket_arm")
    assert t["initial"] == "做一个 L 形的支架臂" and t["modifications"] == ["立臂总高改成 70 mm，耳孔离顶端的距离不变"]
    assert sizes(t, "after_initial") == [(120, 0.5, "x"), (30, 0.5, "y"), (60, 0.5, "z")]
    assert sizes(t, "after_mod_1") == [(120, 0.5, "x"), (30, 0.5, "y"), (70, 0.5, "z")]
    assert points(t, "after_initial", "inside") == [[50, 10, 4], [48, 4, 3], [15, 10, 4], [-50, 0, 20], [-50, 0, 55], [-35, 0, 12],
                                                    [58.5, 0, 6.5], [-50, 10, 45]]
    assert points(t, "after_initial", "outside") == [[48, 0, 4], [48, 4, 7], [15, 0, 4], [-50, 0, 45], [-35, 5, 12], [-20, 0, 30],
                                                     [59.5, 0, 7.5], [-25, 9, 4]]
    assert points(t, "after_mod_1", "inside") == [[50, 10, 4], [48, 4, 3], [15, 10, 4], [-50, 0, 20], [-50, 0, 45], [-50, 0, 65],
                                                  [-35, 0, 12], [58.5, 0, 6.5]]
    assert points(t, "after_mod_1", "outside") == [[48, 0, 4], [48, 4, 7], [15, 0, 4], [-50, 0, 55], [-35, 5, 12], [-20, 0, 30],
                                                   [59.5, 0, 7.5], [-25, 9, 4]]

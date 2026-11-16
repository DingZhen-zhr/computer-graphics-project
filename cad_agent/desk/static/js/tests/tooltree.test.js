// tooltree.js：把一轮的工具树变成要显示的行（第二版计划 3 Task 9）。
import test from "node:test";
import assert from "node:assert/strict";
import { treeLines } from "../tooltree.js";

const tool = (label, state, summary = "") => ({ name: "x", label, state, summary });

test("test_last_tool_uses_corner_mark", () => {
  const work = { stages: [{ id: "s1", title: "底板", passed: false, tools: [tool("写检查", "ok"), tool("写特征 base", "ok"), tool("运行并检查", "ok")] }], loose: [] };
  const lines = treeLines(work);
  assert.deepEqual(lines.map((l) => l.mark), ["S1", "├", "├", "└"]);
  assert.deepEqual(lines.map((l) => l.depth), [0, 1, 1, 1]);
  assert.equal(lines[0].text, "底板");
  assert.equal(lines[2].text, "写特征 base");
});

test("test_passed_stage_collapses_to_one_line", () => {
  const work = { stages: [{ id: "s1", title: "底板", passed: true, checks: 5, tools: [tool("写检查", "ok"), tool("运行并检查", "ok")] },
    { id: "s2", title: "立板", passed: false, tools: [tool("写检查", "running")] }], loose: [] };
  const lines = treeLines(work);
  assert.deepEqual(lines.map((l) => l.mark), ["S1", "S2", "└"]);
  assert.equal(lines[0].text, "底板 ✓ 检查 5 条");
  assert.equal(lines[0].state, "ok");
  assert.equal(lines[0].collapsed, true);
  assert.equal(lines[0].stage, "s1");
  const open = treeLines(work, new Set(["s1"]));
  assert.deepEqual(open.map((l) => l.mark), ["S1", "├", "└", "S2", "└"]);
  assert.equal(open[0].collapsed, false);
});

test("test_running_tool_state", () => {
  const work = { stages: [{ id: "s2", title: "立板", passed: false, tools: [tool("写检查", "ok"), tool("运行并检查", "running")] }], loose: [] };
  const lines = treeLines(work);
  assert.equal(lines[2].state, "running");
  assert.equal(lines[0].state, "running");   // 阶段里有工具在跑，阶段这一行也算在跑
  assert.equal(lines[1].state, "ok");
});

test("test_loose_tools_have_no_stage_row", () => {
  const work = { stages: [], loose: [tool("更新需求单", "ok", "加了 2 个参数"), tool("制定计划", "ok")] };
  const lines = treeLines(work);
  assert.equal(lines.length, 2);
  assert.ok(lines.every((l) => l.depth === 0 && !l.stage && !/^S\d/.test(l.mark)));
  assert.equal(lines[0].detail, "加了 2 个参数");
});

test("test_failed_tool_is_bad", () => {
  const work = { stages: [{ id: "s1", title: "底板", passed: false, tools: [{ name: "build", label: "运行并检查", ok: false, summary: "检查没通过：base-w" }] }], loose: [] };
  const lines = treeLines(work);
  assert.equal(lines[1].state, "bad");
  assert.equal(lines[1].detail, "检查没通过：base-w");
  assert.equal(lines[0].state, "bad");
});

test("test_loose_before_stages_order", () => {
  const work = { stages: [{ id: "s1", title: "底板", passed: false, tools: [tool("写检查", "ok")] }], loose: [tool("制定计划", "ok")] };
  assert.deepEqual(treeLines(work).map((l) => l.text), ["制定计划", "底板", "写检查"]);
});

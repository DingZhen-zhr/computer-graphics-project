// store.js 的规则（第二版计划 3 Task 8）。运行：node --test cad_agent/desk/static/js/tests/
import test from "node:test";
import assert from "node:assert/strict";
import { applyEvent, emptyState } from "../store.js";

const plan2 = { stages: [{ id: "s1", title: "底板", done_when: "有底板", passed: false }, { id: "s2", title: "立板", done_when: "有立板", passed: false }], current: "s1" };

function fullState(extra = {}) {
  return { ...emptyState(), session: { id: "a", title: "支架", demo: false }, phase: "modeling", last_seq: 10,
    transcript: [{ role: "user", text: "你好" }, { role: "assistant", kind: "reply", text: "在" }], ...extra };
}

function run(state, events) {
  return events.reduce((s, e) => applyEvent(s, e), state);
}

const live = (s) => s.transcript[s.transcript.length - 1];

test("test_state_event_replaces_everything", () => {
  let s = run(emptyState(), [{ seq: 1, type: "turn_start", text: "旧的" }, { seq: 2, type: "delta", text: "半句" }]);
  s = applyEvent(s, { seq: 11, type: "state", state: fullState() });
  assert.equal(s.transcript.length, 2);
  assert.equal(s.transcript[1].text, "在");
  assert.equal(s.busy, false);
  assert.equal(s.last_seq, 11);
  assert.equal(s.needResync, false);
  assert.ok(!s.transcript.some((t) => t.role === "live"));
  // 之后再来一条旧事件（seq 不比状态新）：不重复
  assert.equal(applyEvent(s, { seq: 9, type: "turn_start", text: "旧的" }), s);
});

test("test_state_while_busy_keeps_streaming_text", () => {
  const st = fullState({ busy: true, last_seq: 20, transcript: [{ role: "user", text: "开始" },
    { role: "work", stages: [{ id: "s1", title: "底板", passed: false, tools: [{ name: "set_checks", label: "写检查", ok: true, summary: "完成" }] }], loose: [] }],
    pending: { streaming: "我先写", running: { id: "t3", name: "build", label: "运行并检查" } }, plan: plan2 });
  let s = applyEvent(emptyState(), { seq: 21, type: "state", state: st });
  assert.equal(live(s).role, "live");
  assert.equal(live(s).streaming, "我先写");
  assert.equal(s.transcript.length, 2);   // work 项并进了进行中的那一项
  assert.equal(live(s).work.stages[0].tools.length, 2);
  assert.equal(live(s).work.stages[0].tools[1].state, "running");
  s = applyEvent(s, { seq: 22, type: "delta", text: "检查" });
  assert.equal(live(s).streaming, "我先写检查");
});

test("test_turn_start_adds_user_and_pending", () => {
  const s = applyEvent(fullState(), { seq: 11, type: "turn_start", text: "做个盒子" });
  assert.deepEqual(s.transcript.slice(-2).map((t) => t.role), ["user", "live"]);
  assert.equal(s.transcript[2].text, "做个盒子");
  assert.equal(s.busy, true);
  assert.equal(live(s).streaming, "");
});

test("test_delta_appends_and_reset_clears", () => {
  let s = run(fullState(), [{ seq: 11, type: "turn_start", text: "x" }, { seq: 12, type: "delta", text: "说到" }, { seq: 13, type: "delta", text: "一半" }]);
  assert.equal(live(s).streaming, "说到一半");
  s = applyEvent(s, { seq: 14, type: "delta_reset" });
  assert.equal(live(s).streaming, "");
  s = applyEvent(s, { seq: 15, type: "delta", text: "重说" });
  assert.equal(live(s).streaming, "重说");
});

test("test_assistant_replaces_streaming", () => {
  const s = run(fullState(), [{ seq: 11, type: "turn_start", text: "x" }, { seq: 12, type: "delta", text: "半" },
    { seq: 13, type: "assistant", content: "完整的一句" }]);
  assert.equal(live(s).streaming, "");
  assert.deepEqual(live(s).replies, ["完整的一句"]);
});

test("test_tools_grouped_by_current_stage", () => {
  let s = run(fullState({ plan: plan2 }), [{ seq: 11, type: "turn_start", text: "x" },
    { seq: 12, type: "tool_start", id: "t1", name: "set_checks", label: "写检查" },
    { seq: 13, type: "tool_end", id: "t1", name: "set_checks", ok: true, summary: "记下 2 条检查" }]);
  const st = live(s).work.stages;
  assert.equal(st.length, 1);
  assert.equal(st[0].id, "s1");
  assert.equal(st[0].title, "底板");
  assert.deepEqual(st[0].tools[0], { id: "t1", name: "set_checks", label: "写检查", state: "ok", ok: true, summary: "记下 2 条检查" });
  s = run(s, [{ seq: 14, type: "plan", stages: plan2.stages, current: "s2" }, { seq: 15, type: "tool_start", id: "t2", name: "upsert_feature", label: "写特征 wall" }]);
  assert.deepEqual(live(s).work.stages.map((x) => x.id), ["s1", "s2"]);
  assert.equal(live(s).work.stages[1].tools[0].state, "running");
});

test("test_tools_before_plan_are_loose", () => {
  const s = run(fullState({ plan: null }), [{ seq: 11, type: "turn_start", text: "x" },
    { seq: 12, type: "tool_start", id: "t1", name: "set_plan", label: "制定计划" },
    { seq: 13, type: "tool_end", id: "t1", name: "set_plan", ok: false, summary: "出错：…" }]);
  assert.deepEqual(live(s).work.stages, []);
  assert.equal(live(s).work.loose[0].state, "bad");
});

test("test_stage_event_marks_passed", () => {
  const s = run(fullState({ plan: plan2 }), [{ seq: 11, type: "turn_start", text: "x" },
    { seq: 12, type: "tool_start", id: "t1", name: "build", label: "运行并检查" },
    { seq: 13, type: "stage", id: "s1", title: "底板", checks: 5, size: [1, 2, 3], volume: 6 }]);
  assert.equal(live(s).work.stages[0].passed, true);
  assert.equal(s.plan.stages[0].passed, true);
  assert.equal(plan2.stages[0].passed, false);   // 不改原来的对象
});

test("test_error_event_adds_message", () => {
  const s = run(fullState(), [{ seq: 11, type: "turn_start", text: "x" }, { seq: 12, type: "error", message: "出了意外的错误" }]);
  const last = s.transcript[s.transcript.length - 1];
  assert.equal(last.role, "assistant");
  assert.equal(last.kind, "error");
  assert.equal(last.text, "出了意外的错误");
  assert.equal(s.busy, false);
});

test("test_turn_end_clears_busy", () => {
  const s = run(fullState(), [{ seq: 11, type: "turn_start", text: "x" }, { seq: 12, type: "turn_end", kind: "reply", text: "好" }]);
  assert.equal(s.busy, false);
});

test("test_unknown_event_is_ignored", () => {
  const s = fullState();
  const out = applyEvent(s, { seq: 11, type: "something_new", x: 1 });
  assert.equal(out.transcript, s.transcript);
  assert.equal(out.busy, s.busy);
});

test("test_resync_sets_flag", () => {
  const s = applyEvent(fullState(), { seq: 50, type: "resync" });
  assert.equal(s.needResync, true);
});

test("test_stage_event_adds_stage_file", () => {
  // 正在建模时一个阶段通过：它的 STL 已经导出，模型页签马上可以看（不用等这一轮结束）
  let s = run(fullState({ plan: plan2, stage_files: [] }), [{ seq: 11, type: "turn_start", text: "x" },
    { seq: 12, type: "stage", id: "s1", title: "底板", checks: 5, size: [1, 2, 3], volume: 6 }]);
  assert.deepEqual(s.stage_files, ["s1"]);
  s = applyEvent(s, { seq: 13, type: "stage", id: "s1", title: "底板", checks: 5 });
  assert.deepEqual(s.stage_files, ["s1"]);
  s = applyEvent(s, { seq: 14, type: "stage", id: "s2", title: "立板", checks: 2 });
  assert.deepEqual(s.stage_files, ["s1", "s2"]);
});

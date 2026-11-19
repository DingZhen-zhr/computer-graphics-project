// 静态回放模式下的 api.js（第二版计划 4 Task 5）：根元素带 data-mode="static" 时，读 state.json 和 files/，写操作一律"只读"。
// 这个文件单独一个进程跑（node --test 每个文件一个进程），所以可以放心改全局的 document 和 fetch。
import test from "node:test";
import assert from "node:assert/strict";

const STATE = {
  session: { id: "phone_stand", title: "桌面看视频小支架", demo: true },
  versions: [{ name: "v1" }, { name: "v2" }],
  last_seq: 7,
  static_diffs: { "v1|v2": ["tilt_deg: 65 → 70 (deg)"], "v2|v1": ["tilt_deg: 70 → 65 (deg)"] },
};
const fetched = [];
globalThis.document = { documentElement: { dataset: { mode: "static" } } };
globalThis.fetch = async (url) => {
  fetched.push(String(url));
  if (String(url) !== "state.json") return { ok: false, status: 404, json: async () => ({}), text: async () => "" };
  return { ok: true, status: 200, json: async () => structuredClone(STATE), text: async () => JSON.stringify(STATE) };
};
globalThis.EventSource = class {
  constructor() {
    throw new Error("静态回放不该打开事件流");
  }
};

const api = await import("../api.js");

test("test_static_mode_is_detected", () => {
  assert.equal(api.isStatic(), true);
});

test("test_static_get_state_returns_state_json", async () => {
  const { status, body } = await api.get("/api/sessions/x/state");
  assert.equal(status, 200);
  assert.deepEqual(body, STATE);
  assert.ok(fetched.every((u) => u === "state.json"), fetched.join(","));
});

test("test_static_sessions_list_has_only_the_demo", async () => {
  const { status, body } = await api.get("/api/sessions");
  assert.equal(status, 200);
  assert.deepEqual(body.map((s) => [s.id, s.demo, s.versions]), [["phone_stand", true, 2]]);
});

test("test_static_boot_is_ready_without_key", async () => {
  const { status, body } = await api.get("/api/boot");
  assert.equal(status, 200);
  assert.equal(body.static, true);
  assert.equal(body.ready, true);
  assert.equal(body.settings.theme, "system");
});

test("test_static_diff_reads_precomputed_lines", async () => {
  const { status, body } = await api.get("/api/sessions/phone_stand/diff?a=v1&b=v2");
  assert.equal(status, 200);
  assert.deepEqual(body.lines, ["tilt_deg: 65 → 70 (deg)"]);
  const missing = await api.get("/api/sessions/phone_stand/diff?a=v1&b=v9");
  assert.equal(missing.status, 404);
  assert.ok(missing.body.error);
});

test("test_static_post_and_delete_are_read_only", async () => {
  for (const res of [await api.post("/api/sessions/x/message", { text: "hi" }), await api.post("/api/settings", { theme: "dark" }),
    await api.del("/api/sessions/x")]) {
    assert.equal(res.status, 403);
    assert.match(res.body.error, /只读/);
  }
});

test("test_static_subscribe_does_nothing", () => {
  const stop = api.subscribe("x", 0, () => assert.fail("不该收到事件"), () => assert.fail("不该有状态"));
  assert.equal(typeof stop, "function");
  stop();
});

test("test_static_file_urls_are_relative", () => {
  assert.equal(api.fileUrl("phone_stand", "v1", "view.png"), "files/v1/view.png");
  assert.equal(api.fileUrl("phone_stand", "v2", "stages/s1.stl"), "files/v2/stages/s1.stl");
});

test("test_static_unknown_route_is_404", async () => {
  const { status, body } = await api.get("/api/cases");
  assert.equal(status, 404);
  assert.ok(body.error);
});

import test from "node:test";
import assert from "node:assert/strict";
import { createPlayer, hitAt, loadMotion, MOTION_BROKEN, poseAt, validateMotion } from "../motion-logic.js";

const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
function rotX(deg, tz = 0) {
  const c = Math.cos((deg * Math.PI) / 180); const s = Math.sin((deg * Math.PI) / 180);
  return [1, 0, 0, 0, 0, c, -s, 0, 0, s, c, tz, 0, 0, 0, 1];
}
const joint = { id: "open", label: "盖子翻开", type: "revolute", unit: "deg", lo: 0, hi: 90,
  samples: [{ value: 0, poses: { body: I, lid: rotX(0, 10) }, hits: [] }, { value: 45, poses: { body: I, lid: rotX(45, 10) }, hits: [] },
    { value: 90, poses: { body: I, lid: rotX(90, 10) }, hits: [{ a: "body", b: "lid", volume: 2 }] }] };
const motion = { parts: { body: {}, lid: {} }, rest: { body: I, lid: rotX(0, 10) }, explode: {}, joints: [joint] };
const close = (a, b) => a.every((x, i) => Math.abs(x - b[i]) < 1e-9);

test("poseAt：在取样点上、两点中间、超出范围", () => {
  assert.ok(close(poseAt(joint, 45).lid, rotX(45, 10)));
  assert.ok(close(poseAt(joint, 22.5).lid, rotX(22.5, 10)));   // 球面插值：转一半
  assert.ok(close(poseAt(joint, -10).lid, rotX(0, 10)));
  assert.ok(close(poseAt(joint, 200).lid, rotX(90, 10)));
  assert.deepEqual(hitAt(joint), { value: 90, a: "body", b: "lid" });
});

test("test_motion_player_state_machine", () => {
  let t = 0;
  const frames = [];
  const p = createPlayer((f) => frames.push(f), { now: () => t });
  p.select(joint);
  assert.equal(p.state().value, 0);
  assert.ok(p.play());
  t = 1100;
  p.tick();
  assert.ok(p.state().value > 0 && p.state().value < 90 && p.state().playing);
  p.seek(30);                                   // 播放中拖动：停下，停在拖到的位置
  assert.deepEqual([p.state().playing, p.state().value], [false, 30]);
  p.play();
  p.select({ ...joint, id: "other" });          // 换关节：回到初始位置
  assert.deepEqual([p.state().playing, p.state().value], [false, 0]);
  p.seek(60);
  p.stop();                                     // 切换版本时调用：回到初始位置
  assert.deepEqual([p.state().playing, p.state().value], [false, 0]);
  p.seek(500);
  assert.equal(p.state().value, 90);
});

test("test_reduced_motion_does_not_autoplay", () => {
  const p = createPlayer(null, { reduced: true, now: () => 0 });
  p.select(joint);
  assert.equal(p.play(), false);
  assert.equal(p.state().playing, false);
  p.seek(45);
  assert.equal(p.state().value, 45);
});

test("test_bad_motion_file_falls_back_to_rest", async () => {
  assert.ok(validateMotion(motion));
  assert.equal(validateMotion({ ...motion, joints: [{ id: "j", samples: [{ value: 0, poses: { lid: [1, 2] } }] }] }), false);
  assert.equal(validateMotion(null), false);
  const bad = await loadMotion("x", async () => ({ ok: true, json: async () => ({ parts: 1 }) }));
  assert.deepEqual(bad, { error: MOTION_BROKEN });
  const missing = await loadMotion("x", async () => ({ ok: false }));
  assert.deepEqual(missing, { error: MOTION_BROKEN });
  const thrown = await loadMotion("x", async () => { throw new Error("断网"); });
  assert.deepEqual(thrown, { error: MOTION_BROKEN });
  const ok = await loadMotion("x", async () => ({ ok: true, json: async () => motion }));
  assert.equal(ok.joints[0].id, "open");
});

test("test_play_resumes_from_where_it_paused", () => {
  // 复查第 10 条：暂停或拖动以后再播放，要从当前位置接着走，不跳回一端
  let t = 0;
  const p = createPlayer(null, { now: () => t });
  p.select(joint);
  p.seek(60);
  p.play();
  t = 1;
  p.tick();
  assert.ok(Math.abs(p.state().value - 60) < 1, String(p.state().value));
  t = 2200;                                      // 剩下的 30° 只要三分之一个单程：这时已经到头
  p.tick();
  assert.equal(p.state().value, 90);
  t = 3300;                                      // 接着往回走
  p.tick();
  assert.ok(p.state().value < 90 && p.state().value > 0 && p.state().playing);
  t = 100000;
  for (let i = 0; i < 5; i += 1) { t += 3000; p.tick(); }
  assert.ok(p.state().value >= 0 && p.state().value <= 90);
});

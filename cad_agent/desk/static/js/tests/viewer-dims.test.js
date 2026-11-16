// viewer-dims.js：外形尺寸线的位置、3D 退回截图的判断（第二版计划 3 Task 10）。
import test from "node:test";
import assert from "node:assert/strict";
import { dimSegments, fallbackReason } from "../viewer-dims.js";

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const outside = (p, box) => p[0] < box[0] || p[0] > box[3] || p[1] < box[1] || p[1] > box[4] || p[2] < box[2] || p[2] > box[5];

test("test_dim_segments_lengths", () => {
  const box = [-40, -25, 0, 40, 25, 30];
  const segs = dimSegments(box);
  assert.deepEqual(segs.map((s) => s.axis), ["x", "y", "z"]);
  assert.deepEqual(segs.map((s) => Math.round(dist(s.from, s.to) * 1000) / 1000), [80, 50, 30]);
  assert.deepEqual(segs.map((s) => s.text), ["80", "50", "30"]);
  for (const s of segs) {
    assert.ok(outside(s.from, box) && outside(s.to, box), `${s.axis} 应该在包围盒外侧`);
    assert.ok(outside(s.label, box));
    // 文字放在线的中间附近
    assert.ok(Math.abs(dist(s.from, s.label) - dist(s.to, s.label)) < 1e-6);
    // 两端的短竖线（延伸线）从包围盒连到尺寸线
    assert.equal(s.ext.length, 2);
  }
});

test("test_dim_text_is_rounded", () => {
  const segs = dimSegments([0, 0, 0, 12.3456, 7, 1]);
  assert.deepEqual(segs.map((s) => s.text), ["12.35", "7", "1"]);
});

test("test_viewer_fallback_decision", () => {
  assert.equal(fallbackReason({ webgl: false, stlOk: true }), "这台电脑现在显示不了三维画面，先用截图代替。");
  assert.equal(fallbackReason({ webgl: false, stlOk: false }), "这台电脑现在显示不了三维画面，先用截图代替。");
  assert.equal(fallbackReason({ webgl: true, stlOk: false }), "三维模型没有加载出来，先用截图代替。");
  assert.equal(fallbackReason({ webgl: true, stlOk: true }), null);
});

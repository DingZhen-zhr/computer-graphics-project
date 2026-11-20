import test from "node:test";
import assert from "node:assert/strict";
import { axisLayout, explodedMatrix, isolateOpacity, layoutLabels, materialFor, safeView, snapDirection } from "../view3d/logic.js";

const near = (a, b) => Math.abs(a - b) < 1e-6;
// 相机朝向的四元数（[x, y, z, w]），up 是 +Z
const FRONT = [Math.SQRT1_2, 0, 0, Math.SQRT1_2];   // 从 -Y 看过来：X 向右、Z 向上
const TOP = [0, 0, 0, 1];                           // 从 +Z 往下看：X 向右、Y 向上
const BOTTOM = [1, 0, 0, 0];                        // 从 -Z 往上看：X 向右、Y 向下

test("坐标轴小图：正视、俯视、底视", () => {
  const pos = (q, axis) => axisLayout(q).find((a) => a.axis === axis && a.positive);
  assert.ok(near(pos(FRONT, "X").x, 1) && near(pos(FRONT, "Z").y, -1) && near(pos(FRONT, "Y").depth, -1));
  assert.ok(near(pos(TOP, "X").x, 1) && near(pos(TOP, "Y").y, -1) && near(pos(TOP, "Z").depth, 1));
  assert.ok(near(pos(BOTTOM, "X").x, 1) && near(pos(BOTTOM, "Y").y, 1) && near(pos(BOTTOM, "Z").depth, -1));
  const order = axisLayout(TOP).map((a) => a.depth);
  assert.deepEqual(order, [...order].sort((a, b) => a - b));   // 后面的先画
});

test("test_view_snap_from_below_keeps_up_vector", () => {
  assert.deepEqual(snapDirection("Z", false), [0, 0, -1]);
  const v = safeView(snapDirection("Z", false));
  assert.deepEqual(v.up, [0, 0, 1]);
  assert.ok(Math.abs(v.dir[1]) > 0 && v.dir[2] === -1);   // 偏一点点，视线不和 up 平行
  const front = safeView([0, -1, 0]);
  assert.deepEqual(front.dir, [0, -1, 0]);
});

test("材质：三种质感、深色略提亮", () => {
  const m = materialFor("matte", "c1", "light");
  const metal = materialFor("metal", "c2", "light");
  const pol = materialFor("polished", "c3", "dark");
  assert.ok(m.roughness > metal.roughness && metal.roughness > pol.roughness);
  assert.ok(pol.metalness > m.metalness);
  assert.equal(m.lift, 0);
  assert.ok(pol.lift > 0);
  assert.equal(materialFor("glass", "c4", "light").roughness, m.roughness);
});

test("炸开的平移量", () => {
  const I = [1, 0, 0, 5, 0, 1, 0, 0, 0, 0, 1, 10, 0, 0, 0, 1];
  const m = explodedMatrix(I, [0, 0, 1], 0.5, 200);
  assert.deepEqual([m[3], m[7], m[11]], [5, 0, 110]);
  assert.deepEqual(I[11], 10);   // 原矩阵不变
});

test("单独看和透视的不透明度（六种组合）", () => {
  assert.equal(isolateOpacity("a", null, false), 1);
  assert.equal(isolateOpacity("a", null, true), 0.35);
  assert.equal(isolateOpacity("a", "a", false), 1);
  assert.equal(isolateOpacity("b", "a", false), 0.12);
  assert.equal(isolateOpacity("a", "a", true), 0.9);
  assert.equal(isolateOpacity("b", "a", true), 0.22);
});

test("test_labels_do_not_overlap", () => {
  const pts = [{ id: "a", x: 500, y: 300 }, { id: "b", x: 505, y: 305 }, { id: "c", x: 510, y: 298 }, { id: "d", x: 498, y: 310 }];
  const boxes = layoutLabels(pts, { width: 1200, height: 800 });
  assert.equal(boxes.length, 4);
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i]; const b = boxes[j];
      const apart = a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y;
      assert.ok(apart, `${a.id} 和 ${b.id} 重叠了`);
    }
  }
  assert.ok(boxes.every((b) => b.left));   // 都在屏幕左半边：标签放在左上
  assert.equal(layoutLabels([{ id: "x", x: 10, y: 10, visible: false }], { width: 100 }).length, 0);
});

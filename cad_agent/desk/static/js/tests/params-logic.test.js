// params-logic.js：参数面板的滑块范围、改动、校验（第二版计划 3 Task 11）。
import test from "node:test";
import assert from "node:assert/strict";
import { pendingChanges, sliderRange, validateEdit } from "../params-logic.js";

const p = (name, value, unit) => ({ name, value, unit, source: "user", note: "" });

test("test_slider_range_for_length", () => {
  assert.deepEqual(sliderRange(p("w", 78, "mm")), { min: 39, max: 117, step: 0.8 });
  assert.deepEqual(sliderRange(p("t", 5, "mm")), { min: 2.5, max: 7.5, step: 0.05 });
  assert.deepEqual(sliderRange(p("a", 65, "deg")), { min: 32.5, max: 97.5, step: 0.7 });
});

test("test_slider_range_for_count", () => {
  assert.deepEqual(sliderRange(p("n", 4, "1")), { min: 1, max: 7, step: 1 });
  assert.deepEqual(sliderRange(p("n", 12, "1")), { min: 9, max: 15, step: 1 });
});

test("test_slider_range_for_zero", () => {
  assert.deepEqual(sliderRange(p("off", 0, "mm")), { min: 0, max: 10, step: 0.1 });
});

test("test_slider_range_for_negative_value", () => {
  assert.deepEqual(sliderRange(p("dx", -20, "mm")), { min: -30, max: -10, step: 0.2 });
});

test("test_pending_changes_only_changed", () => {
  const params = [p("w", 78, "mm"), p("h", 40, "mm"), p("n", 4, "1")];
  assert.deepEqual(pendingChanges(params, { w: 80, h: 40, n: 4 }), { w: 80 });
  assert.deepEqual(pendingChanges(params, {}), {});
  assert.deepEqual(pendingChanges(params, { nope: 3 }), {});
});

test("test_validate_rejects_text_and_empty", () => {
  const w = p("w", 78, "mm");
  assert.deepEqual(validateEdit(w, " 80.5 "), { ok: true, value: 80.5 });
  for (const bad of ["", "   ", "abc", "8o", "1e999", "NaN"]) {
    const r = validateEdit(w, bad);
    assert.equal(r.ok, false, bad);
    assert.ok(r.message && /[一-鿿]/.test(r.message), bad);
  }
});

test("test_validate_count_must_be_integer", () => {
  const n = p("n", 4, "1");
  assert.deepEqual(validateEdit(n, "6"), { ok: true, value: 6 });
  const r = validateEdit(n, "4.5");
  assert.equal(r.ok, false);
  assert.match(r.message, /整数/);
  assert.deepEqual(validateEdit(p("k", 1.5, "1"), "2.5"), { ok: true, value: 2.5 });   // 原值本来就不是整数：不限
});

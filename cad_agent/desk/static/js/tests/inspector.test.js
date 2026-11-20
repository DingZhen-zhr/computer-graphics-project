import test from "node:test";
import assert from "node:assert/strict";
import { briefRows, briefSections, checkStatus, groupChecks, paramChangeText } from "../panels-logic.js";

test("briefRows: 来源标签和等你回答", () => {
  const rows = briefRows({ params: [
    { name: "plate_l", value: 100, unit: "mm", source: "user", note: "板长（x 方向）" },
    { name: "plate_t", value: 5, unit: "mm", source: "suggested", note: "板厚" },
    { name: "hole_n", value: 4, unit: "1", source: "suggested", note: "孔数" },
  ], open_questions: ["板厚多少？"] });
  assert.deepEqual(rows.map((r) => [r.label, r.value, r.unit, r.tag, r.waiting]), [
    ["板长", "100", "mm", "你给的", false], ["板厚", "", "mm", null, true], ["孔数", "4", "", "建议", false]]);
});

test("briefSections: 多零件分块", () => {
  const brief = { params: [{ name: "w", value: 40, unit: "mm", source: "user", note: "宽" }, { name: "t", value: 4, unit: "mm", source: "user", note: "盖厚", part: "lid" }],
    parts: [{ id: "body", name: "盒体", features: ["盒体"] }, { id: "lid", name: "盖子", features: ["盖板"] }], relations: ["盖子盖在盒体上"], motions: ["盖子翻开"] };
  assert.deepEqual(briefSections(brief).map((s) => s.title), ["零件", "共用的尺寸", "盖子的尺寸", "怎么连", "会动的地方"]);
});

test("groupChecks: 单零件按步骤、多零件按零件，装配放最后", () => {
  const plan = { stages: [{ id: "s1", title: "板" }, { id: "s2", title: "孔" }] };
  const single = groupChecks([{ id: "a", stage: "s1" }, { id: "b", stage: "s2" }, { id: "valid" }], { plan });
  assert.deepEqual(single.map((g) => [g.group, g.items.length]), [["S1 板", 1], ["S2 孔", 1], ["检查", 1]]);
  const product = { parts: [{ id: "body", name: "盒体" }, { id: "lid", name: "盖子" }] };
  const multi = groupChecks([{ id: "x", part: "assembly" }, { id: "a", part: "lid" }, { id: "b", part: "body" }], { product });
  assert.deepEqual(multi.map((g) => g.group), ["盒体", "盖子", "装配"]);
});

test("test_check_status_has_text", () => {
  for (const c of [{ passed: true }, { passed: false }, {}]) {
    const s = checkStatus(c);
    assert.ok(["量过，对", "没过", "没做"].includes(s.text), JSON.stringify(c));
  }
});

test("参数变化的文字", () => {
  assert.equal(paramChangeText({ label: "孔径", unit: "mm", a: 6, b: 8 }), "孔径：6 → 8 毫米");
  assert.equal(paramChangeText({ name: "n", unit: "1", a: 4, b: 6 }), "n：4 → 6");
});

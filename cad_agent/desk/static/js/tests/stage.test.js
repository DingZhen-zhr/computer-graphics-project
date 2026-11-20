import test from "node:test";
import assert from "node:assert/strict";
import { choicesFor, phaseView, scoreView, TEXT } from "../stage-logic.js";

const session = { id: "s", title: "t", demo: false };
const base = { session, busy: false, phase: "clarify", transcript: [], brief: null, plan: null, versions: [], checks: [], product: null };

test("phaseView: 新会话", () => {
  const v = phaseView(base);
  assert.equal(v.center, "welcome");
  assert.equal(v.title, "新零件");
  assert.equal(v.caption, TEXT.welcome);
});

test("phaseView: 提问", () => {
  const v = phaseView({ ...base, brief: { part: { name: "" } },
    transcript: [{ role: "user", text: "做个支架" }, { role: "assistant", kind: "question", lead: "先问两件事。", questions: ["多厚？", "多宽？"] }] });
  assert.equal(v.center, "brief");
  assert.equal(v.title, "新零件");
  assert.equal(v.subtitle, "还在问你几个问题");
  assert.equal(v.caption, "先问两件事。 多厚？ 多宽？");
});

test("phaseView: 等确认", () => {
  const v = phaseView({ ...base, phase: "confirm", brief: { part: { name: "安装板" } },
    transcript: [{ role: "user", text: "x" }, { role: "assistant", kind: "confirm", lead: "都记下了。" }] });
  assert.deepEqual([v.center, v.title, v.subtitle], ["confirm", "安装板", "都记下了，你看一下"]);
});

test("phaseView: 正在做第几步", () => {
  const v = phaseView({ ...base, busy: true, phase: "modeling", brief: { part: { name: "安装板" } },
    plan: { stages: [{ id: "s1", title: "板", passed: true }, { id: "s2", title: "孔", passed: false }], current: "s2" },
    transcript: [{ role: "user", text: "确认" }, { role: "live" }] });
  assert.deepEqual([v.center, v.subtitle], ["model", "正在做，第 2 步，共 2 步"]);
});

test("phaseView: 做好了", () => {
  const v = phaseView({ ...base, phase: "delivered", brief: { part: { name: "安装板" } },
    versions: [{ name: "v2", size: [100, 60, 5] }], transcript: [{ role: "user", text: "x" }, { role: "assistant", kind: "delivered", text: "做好了。\n检查……" }] });
  assert.deepEqual([v.center, v.subtitle, v.caption], ["model", "第 2 版，100 × 60 × 5 毫米", "做好了。"]);
});

test("phaseView: 没做完", () => {
  const v = phaseView({ ...base, phase: "modeling", brief: { part: { name: "安装板" } },
    transcript: [{ role: "user", text: "x" }, { role: "assistant", kind: "failed", text: "建模已经连续没通过 3 次。" }] });
  assert.deepEqual([v.center, v.subtitle, v.choices], ["failed", "没做完", ["继续"]]);
});

test("test_multipart_subtitle_counts_parts", () => {
  const product = { parts: [{ id: "body", name: "盒体", status: "done" }, { id: "lid", name: "盖子", status: "current" }, { id: "pin", name: "轴", status: "todo" }] };
  const busy = phaseView({ ...base, busy: true, phase: "modeling", product, brief: { part: { name: "工具盒" } }, transcript: [{ role: "live" }] });
  assert.equal(busy.subtitle, "正在做 盖子，第 2 个零件，共 3 个");
  const all = { parts: product.parts.map((p) => ({ ...p, status: "done" })) };
  assert.equal(phaseView({ ...base, busy: true, phase: "modeling", product: all, brief: { part: { name: "工具盒" } }, transcript: [{ role: "live" }] }).subtitle, "正在装起来");
  const done = phaseView({ ...base, phase: "delivered", product: all, brief: { part: { name: "工具盒" } }, versions: [{ name: "v1" }],
    transcript: [{ role: "assistant", kind: "delivered", text: "做好了，3 个零件，存成第 1 版。" }] });
  assert.equal(done.subtitle, "第 1 版，3 个零件");
});

test("test_choices_only_for_single_question_with_options", () => {
  assert.deepEqual(choicesFor({ kind: "question", questions: ["要圆角还是直角？"] }), ["要圆角", "直角"]);
  assert.deepEqual(choicesFor({ kind: "question", questions: ["板厚多少？建议 5 mm。"] }), ["就按建议：5 mm"]);
  assert.deepEqual(choicesFor({ kind: "question", questions: ["多厚？建议 5 mm", "多宽？"] }), []);
  assert.deepEqual(choicesFor({ kind: "question", questions: ["孔放在哪里？"] }), []);
  assert.deepEqual(choicesFor({ kind: "confirm" }), []);
});

test("scoreView", () => {
  assert.equal(scoreView(base), null);
  const s = scoreView({ ...base, phase: "delivered", checks: [{ passed: true }, { passed: true }] });
  assert.deepEqual(s, { text: "2/2", label: "项全部量过，都对" });
  assert.equal(scoreView({ ...base, phase: "modeling", checks: [{ passed: true }, { passed: false }] }).label, "项已经量过");
});

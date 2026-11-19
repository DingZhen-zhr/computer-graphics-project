// 工作台·参数：需求单的参数表，交付之后可以直接改数（输入框或滑块），点"应用"由程序重新验证，不调用模型。
// 失败时显示后端的说明和没通过的检查，旁边"让助手处理"把这次改动作为一条消息发给助手。
import { button, clear, h, sectionHead, status } from "./dom.js";
import { fmtNum } from "./format.js";
import { pendingChanges, sliderRange, validateEdit } from "./params-logic.js";

const NOT_YET = "交付第一个版本之后，就可以在这里直接改数值。";
const BUSY = "正在运行，等这一轮结束再改。";
const DEMO = "示例会话只能看，不能改。";
const ASK = (parts) => `我在参数面板里把 ${parts} 之后，检查没有通过，请帮我处理。`;
let ui = { key: null, edits: {}, errors: {}, result: null, sessionId: null, busyApply: false };

function lockReason(state) {
  if (state.session && state.session.demo) return DEMO;
  if (state.busy || ui.busyApply) return BUSY;
  if (state.phase !== "delivered") return NOT_YET;
  return null;
}

function paramRow(p, locked, rerender) {
  const r = sliderRange(p);
  const edited = Object.prototype.hasOwnProperty.call(ui.edits, p.name) && Number(ui.edits[p.name]) !== Number(p.value);
  const shown = ui.edits[p.name] ?? fmtNum(p.value);
  const input = h("input", { class: "num param-input", value: shown, inputmode: "decimal", disabled: locked, "aria-label": `${p.name} 的数值`,
    "aria-invalid": ui.errors[p.name] ? "true" : null });
  const slider = h("input", { type: "range", min: r.min, max: r.max, step: r.step, value: Number(ui.edits[p.name] ?? p.value), disabled: locked,
    "aria-label": `${p.name} 的滑块` });
  input.addEventListener("change", () => {
    const v = validateEdit(p, input.value);
    if (v.ok) {
      ui.edits[p.name] = v.value;
      delete ui.errors[p.name];
    } else {
      ui.errors[p.name] = v.message;
    }
    rerender();
  });
  slider.addEventListener("input", () => { input.value = fmtNum(slider.value); });
  slider.addEventListener("change", () => {
    ui.edits[p.name] = Number(fmtNum(slider.value));
    delete ui.errors[p.name];
    rerender();
  });
  return h("tr", { class: edited ? "edited" : "" },
    h("td", {}, h("span", { class: "mono pname" }, p.name), p.note ? h("span", { class: "muted note" }, p.note) : null),
    h("td", { class: "num" }, input, ui.errors[p.name] ? h("div", { class: "field-error", role: "alert" }, ui.errors[p.name]) : null),
    h("td", { class: "unit mono muted" }, p.unit === "1" ? "个" : p.unit === "deg" ? "°" : p.unit),
    h("td", { class: "slider" }, slider),
    h("td", {}, h("span", { class: `tag ${p.source === "user" ? "tag-user" : "tag-suggested"}` }, p.source === "user" ? "用户" : "建议")));
}

function resultBlock(state, actions) {
  const r = ui.result;
  if (!r || r.ok) return null;
  const params = (state.brief && state.brief.params) || [];
  const parts = Object.entries(r.values).map(([n, v]) => {
    const old = params.find((p) => p.name === n);
    return `${n} 从 ${fmtNum(old ? old.value : "")} 改成 ${fmtNum(v)}`;
  }).join("、");
  return h("div", { class: "apply-failed", role: "alert" },
    h("p", {}, status("bad", r.text)),
    (r.failed_checks || []).length ? h("ul", { class: "failed-list" }, r.failed_checks.map((c) => h("li", {}, h("span", { class: "mono" }, c.id), `：${c.detail || ""}`))) : null,
    h("div", { class: "card-actions" }, button("让助手处理", async () => {
      if (await actions.send(ASK(parts))) ui.result = null;
    }), h("span", { class: "muted small" }, "数值已经退回原样")));
}

function draw(panel, state, actions) {
  const brief = state.brief || {};
  const params = brief.params || [];
  const locked = lockReason(state);
  const changes = pendingChanges(params, ui.edits);
  const n = Object.keys(changes).length;
  const rerender = () => draw(panel, state, actions);
  const apply = async () => {
    ui.busyApply = true;
    rerender();
    const res = await actions.applyParams(changes);
    ui.busyApply = false;
    if (res.busy) {
      actions.toast(res.text);   // 正在运行：改动留着，等这一轮结束再点"应用"
    } else if (res.ok) {
      ui.edits = {};
      ui.result = null;
      actions.toast(`已存为 ${res.version}`);
      actions.showModel(res.version);
    } else {
      ui.result = { ...res, values: changes };
      ui.edits = {};   // 后端已经退回原来的数值，面板上也显示原值
    }
    rerender();
  };
  if (!params.length) {
    return clear(panel, h("div", { class: "bench-empty static" }, h("p", {}, "需求单里还没有参数。在对话里说说零件的尺寸，参数会列在这里。"),
      button("去对话里说", () => actions.focusInput(), { kind: "text" })));
  }
  clear(panel, h("div", { class: "pane" },
    h("section", { "aria-labelledby": "h-params" }, sectionHead("01", "参数", locked ? "" : '改完点"应用"', "h-params"),
      locked ? h("p", { class: "lock-note muted" }, locked) : null,
      resultBlock(state, actions),
      h("table", { class: "table params-edit" },
        h("thead", {}, h("tr", {}, h("th", {}, "参数"), h("th", { class: "num" }, "数值"), h("th", {}, h("span", { class: "sr-only" }, "单位")), h("th", {}, "调节"), h("th", {}, "来源"))),
        h("tbody", {}, params.map((p) => paramRow(p, !!locked, rerender)))),
      locked ? null : h("div", { class: "apply-row" },
        button(n ? `应用（${n} 处改动）` : "应用", apply, { kind: "primary", disabled: !n || Object.keys(ui.errors).length > 0 }),
        button("还原", () => { ui.edits = {}; ui.errors = {}; ui.result = null; rerender(); }, { disabled: !n && !Object.keys(ui.errors).length }))),
    h("section", { "aria-labelledby": "h-shape" }, sectionHead("02", "组成部分和位置关系", "", "h-shape"),
      h("ul", { class: "plain-list" }, (brief.features || []).map((f) => h("li", {}, f))),
      (brief.relations || []).length ? h("ul", { class: "plain-list muted" }, brief.relations.map((r) => h("li", {}, r))) : null)));
}

export function renderParams(panel, state, actions) {
  const sid = state.session ? state.session.id : null;
  if (sid !== ui.sessionId) ui = { key: null, edits: {}, errors: {}, result: null, sessionId: sid, busyApply: false };
  // 只在参数、阶段、忙不忙变化时重画，免得打断正在输入的数字
  const key = JSON.stringify([state.brief && state.brief.params, state.brief && state.brief.features, state.brief && state.brief.relations,
    state.phase, state.busy, !!(state.session && state.session.demo)]);
  if (key === ui.key && panel.childElementCount) return;
  ui.key = key;
  draw(panel, state, actions);
}

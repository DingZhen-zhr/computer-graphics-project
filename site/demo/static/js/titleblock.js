// 标题栏：工作台右下角一块像图纸标题栏的表格（1px 线分格）：零件、版本、阶段、模型、费用、缓存、日期。
import { clear, h } from "./dom.js";
import { fmtCost, fmtPct } from "./format.js";

const PHASE = { clarify: "澄清", confirm: "等确认", planning: "规划", modeling: "建模", delivered: "已交付" };
const pad = (n) => String(n).padStart(2, "0");

function cell(label, value, cls = "", span = 1) {
  return h("td", { class: cls, colspan: span > 1 ? String(span) : null }, h("span", { class: "tb-label" }, label), h("span", { class: "tb-value" }, value || "—"));
}

function stageText(state) {
  const plan = state.plan;
  if (plan && plan.current) {
    const s = plan.stages.find((x) => x.id === plan.current);
    return s ? `${s.id.toUpperCase()} ${s.title}` : plan.current.toUpperCase();
  }
  if (plan && plan.stages && plan.stages.length) return "完成";
  return PHASE[state.phase] || "";
}

export function renderTitleblock(slot, state, actions) {
  const versions = state.versions || [];
  const usage = state.usage || {};
  const d = new Date();
  const part = (state.brief && state.brief.part && state.brief.part.name) || (state.session ? state.session.title : "");
  clear(slot, h("table", { class: "titleblock", "aria-label": "标题栏" }, h("tbody", {},
    h("tr", {}, cell("零件", part, "tb-part", 2), cell("版本", versions.length ? versions[versions.length - 1].name : ""), cell("阶段", stageText(state))),
    h("tr", {}, cell("模型", actions.modelName(), "tb-model"), cell("费用", fmtCost(state.cost)), cell("缓存", fmtPct(usage.cached_tokens, usage.prompt_tokens)),
      cell("日期", `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`)))));
}

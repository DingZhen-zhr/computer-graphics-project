// 需求单卡片：澄清时就在舞台中间边聊边填；等确认时下面两个按钮；确认后向上飞走、缩小、淡出。
import { $, clear, h } from "./dom.js";
import { briefSections, WAITING } from "./panels-logic.js";

const SUB = {
  brief: "我边聊边记，还没问到的先空着。",
  confirm: "没问题就开始做；想改哪里，直接跟我说。",
};

function rowEl(r) {
  return h("div", { class: "row" }, h("span", {}, r.label),
    r.tag ? h("span", { class: `tag ${r.tag === "你给的" ? "user" : ""}` }, r.tag) : h("span", {}),
    h("span", { class: "v" }, r.waiting ? h("span", { class: "wait" }, WAITING) : (r.unit === "deg" ? `${r.value}°` : `${r.value}${r.unit ? ` ${r.unit}` : ""}`)));
}

export function renderBrief(state, center, actions) {
  const el = $("brief");
  const show = center === "brief" || center === "confirm";
  el.classList.toggle("away", !show);
  el.setAttribute("aria-hidden", String(!show));
  if (!show) return;
  const brief = state.brief || {};
  const name = (brief.part && brief.part.name) || "新零件";
  const demo = !!(state.session && state.session.demo);
  const sections = briefSections(brief).filter((s) => (s.rows && s.rows.length) || (s.items && s.items.length));
  clear(el,
    h("h2", {}, name),
    h("div", { class: "sub" }, SUB[center]),
    sections.map((s) => [h("h3", {}, s.title),
      s.rows ? s.rows.map(rowEl) : h("ul", {}, s.items.map((t) => h("li", {}, t)))]),
    center === "confirm" && !demo ? h("div", { class: "act" },
      h("button", { type: "button", class: "btn-primary", disabled: state.busy, onclick: () => actions.send("确认") }, "没问题，开始做"),
      h("button", { type: "button", class: "btn-glass", onclick: () => actions.focusPrompt() }, "我还要改")) : null);
}

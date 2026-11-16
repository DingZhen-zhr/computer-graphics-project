// 右栏：工作台的四个页签（模型、检查、参数、版本）和右下角的标题栏。各页签的内容由各自的模块画。
import { clear, h } from "./dom.js";

const TABS = [["model", "模型"], ["checks", "检查"], ["params", "参数"], ["versions", "版本"]];
let ui = null;

function setup(root, renderers) {
  const buttons = {};
  const panels = {};
  const bar = h("div", { class: "tabs", role: "tablist", "aria-label": "工作台" });
  for (const [key, label] of TABS) {
    buttons[key] = h("button", { type: "button", role: "tab", id: `tab-${key}`, "aria-controls": `panel-${key}`, class: "tab",
      onclick: () => select(key, true) }, label);
    panels[key] = h("div", { role: "tabpanel", id: `panel-${key}`, "aria-labelledby": `tab-${key}`, class: `panel panel-${key}` });
    bar.append(buttons[key]);
  }
  bar.addEventListener("keydown", (e) => {
    const i = TABS.findIndex(([k]) => k === ui.tab);
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length][0];
      select(next, true);
      buttons[next].focus();
    }
  });
  const titleblock = h("div", { class: "titleblock-slot" });
  clear(root, bar, h("div", { class: "panels" }, Object.values(panels)), titleblock);
  ui = { root, buttons, panels, titleblock, renderers, tab: "model", state: null };
  select("model", false);
}

function select(key, render) {
  ui.tab = key;
  for (const [k] of TABS) {
    const on = k === key;
    ui.buttons[k].setAttribute("aria-selected", on ? "true" : "false");
    ui.buttons[k].tabIndex = on ? 0 : -1;
    ui.panels[k].hidden = !on;
  }
  if (render && ui.state) draw(ui.state);
}

export function showTab(key) {
  if (ui) select(key, true);
}

function draw(state) {
  for (const [key] of TABS) {
    const fn = ui.renderers[key];
    if (fn) fn(ui.panels[key], state, { visible: key === ui.tab });
  }
  if (ui.renderers.titleblock) ui.renderers.titleblock(ui.titleblock, state);
}

export function renderBench(root, state, renderers) {
  if (!ui || ui.root !== root) setup(root, renderers);
  ui.state = state;
  draw(state);
}

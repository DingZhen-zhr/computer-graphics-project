// 右边的抽屉：检查和版本两页。点右边的大数字打开"检查"。
import { clear, formDialog, h } from "./dom.js";
import { fmtTime } from "./format.js";
import { checkStatus, checkValue, groupChecks } from "./panels-logic.js";

let tab = "checks";

function gateBlock(gate) {
  if (!gate || !Array.isArray(gate.mutation) || !gate.mutation.length) return h("p", { class: "small status-none" }, "— 每个尺寸都确认过真的起作用：这次没做");
  const loose = gate.unconstrained || [];
  if (loose.length) return h("p", { class: "small status-bad" }, `✗ 这些尺寸改了检查也不变：${loose.join("、")}`);
  const ok = gate.mutation.filter((m) => m.verdict === "constrained").length;
  return h("p", { class: "small status-ok" }, `✓ 每个尺寸都确认过真的起作用（${ok} 个，改一改检查就会发现）`);
}

function reviewBlock(review) {
  if (!review) return h("p", { class: "small status-none" }, "— 看图审查：这次没做");
  if (review.skipped) return h("p", { class: "small status-none" }, `— 看图审查：没做（${review.skipped}）`);
  const against = (review.items || []).filter((i) => i.verdict === "不符合" || i.verdict === "mismatch");
  if (!against.length) return h("p", { class: "small status-ok" }, "✓ 看图审查：和需求单一致");
  return h("div", {}, h("p", { class: "small status-bad" }, "✗ 看图审查有异议："), against.map((i) => h("p", { class: "small" }, `${i.target}：${i.reason}`)));
}

function checksPage(state) {
  const groups = groupChecks(state.checks, { plan: state.plan, product: state.product });
  if (!groups.length) return h("p", { class: "mute small" }, "还没有量过。开始做之后，每一步量了什么都在这里。");
  return [groups.map((g) => [h("h3", {}, g.group), g.items.map((c) => {
    const s = checkStatus(c);
    return h("div", { class: "check" }, h("span", { class: `status-${s.kind}` }, s.text), h("span", {}, c.id), h("span", { class: "val" }, checkValue(c)),
      c.detail ? h("span", { class: "detail" }, c.detail) : null);
  })]), h("h3", {}, "最后的确认"), gateBlock(state.gate), reviewBlock(state.review)];
}

function versionsPage(state, actions) {
  const versions = [...(state.versions || [])].reverse();
  if (!versions.length) return h("p", { class: "mute small" }, "还没有做好的版本。做好之后，每一版都存在这里，可以下载、对比。");
  const multi = !!state.product;
  const parts = multi ? state.product.parts : [];
  const dlLink = (cls, vName, rel, filename, label) => h("a", {
    class: cls, href: actions.fileUrl(vName, rel), download: filename,
    onclick: (e) => {
      if (actions.readOnly || !actions.download) return;
      e.preventDefault();
      actions.download(vName, rel, filename);
    },
  }, label);
  return versions.map((v) => h("div", { class: "version" },
    v.has_png === false ? h("span", {}) : h("img", { src: actions.fileUrl(v.name, "view.png"), alt: `${v.name} 的截图`, loading: "lazy" }),
    h("div", {},
      h("div", {}, h("b", { class: "num" }, `第 ${v.name.replace(/^v/, "")} 版`), h("span", { class: "mute small" }, `  ${fmtTime(v.created) || ""}`)),
      (v.changes || []).length ? h("div", { class: "small mute" }, v.changes.join("；")) : null,
      h("div", { class: "acts" },
        versions.length > 1 ? h("button", { type: "button", class: "btn-glass btn-small", onclick: () => actions.compare(v.name) }, "对比") : null,
        dlLink("btn-glass btn-small", v.name, multi ? "product.step" : "model.step", `${v.name}.step`, multi ? "下载整个产品 STEP" : "下载 STEP"),
        multi ? null : dlLink("btn-glass btn-small", v.name, "model.stl", `${v.name}.stl`, "下载 STL"),
        parts.map((p) => dlLink("btn-text btn-small", v.name, `parts/${p.id}/model.step`, `${v.name}-${p.id}.step`, `${p.name} STEP`)),
        actions.readOnly ? null : h("button", { type: "button", class: "btn-text btn-small", onclick: () => actions.reveal(v.name) }, "在文件夹中显示"),
        actions.readOnly ? null : h("button", { type: "button", class: "btn-text btn-small", onclick: async () => {
          const r = await formDialog("存为案例", [{ name: "title", label: "名字", value: (state.brief && state.brief.part && state.brief.part.name) || "" },
            { name: "tags", label: "标签（用空格分开）", value: "" }]);
          if (r && r.title.trim()) actions.saveCase(r.title.trim(), r.tags.split(/\s+/).filter(Boolean));
        } }, "存为案例")))));
}

export function showInspectorTab(t) { tab = t; }

export function renderInspector(el, state, actions) {
  const tabBtn = (key, label) => h("button", { type: "button", role: "tab", "aria-selected": String(tab === key),
    onclick: () => { tab = key; renderInspector(el, state, actions); } }, label);
  clear(el,
    h("header", {}, h("h2", {}, tab === "checks" ? "检查" : "版本"),
      h("button", { type: "button", class: "x", "data-close": "", "aria-label": "收起", onclick: actions.close }, "×")),
    h("div", { class: "tabs", role: "tablist" }, tabBtn("checks", "检查"), tabBtn("versions", "版本")),
    tab === "checks" ? checksPage(state) : versionsPage(state, actions));
}

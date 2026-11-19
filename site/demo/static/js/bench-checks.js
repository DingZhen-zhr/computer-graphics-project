// 工作台·检查：最上面一个大数字"通过数 / 总数"；下面三块：01 检查（按阶段分组，没通过的在前）、02 参数扰动验证、03 看图审查。
import { button, clear, h, sectionHead, status } from "./dom.js";
import { fmtNum } from "./format.js";

const VIEWS = [["iso", "等轴测"], ["front", "正视"], ["top", "俯视"], ["right", "右视"]];
const VERDICT = { "符合": "ok", "不符合": "bad", "看不出": "none" };

function checkRows(checks, plan) {
  const titles = Object.fromEntries(((plan && plan.stages) || []).map((s) => [s.id, s.title]));
  const groups = new Map();
  for (const c of checks) {
    const key = c.stage || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  const order = [...groups.keys()].sort((a, b) => (a === "" ? -1 : b === "" ? 1 : a.length - b.length || a.localeCompare(b)));
  return order.map((key) => {
    const rows = groups.get(key).slice().sort((a, b) => Number(a.passed) - Number(b.passed));
    const label = key ? `${key.toUpperCase()} ${titles[key] || ""}`.trim() : "必做检查";
    return h("tbody", {},
      h("tr", { class: "group-row" }, h("th", { colspan: "5", scope: "rowgroup" }, label)),
      rows.map((c) => h("tr", { class: c.passed ? "" : "row-bad" },
        h("td", {}, status(c.passed ? "ok" : "bad", c.passed ? "通过" : "没通过")),
        h("td", { class: "mono", title: c.detail || "" }, c.id),
        h("td", { class: "num" }, fmtNum(c.measured) || "—"),
        h("td", { class: "num" }, fmtNum(c.expected) || "—"),
        h("td", { class: "num muted" }, c.tol === null || c.tol === undefined ? "" : `±${fmtNum(c.tol)}`))));
  });
}

function mutationBlock(gate) {
  if (!gate) return h("p", {}, status("none", "没做"), h("span", { class: "muted" }, "　交付前的终检还没有跑过。"));
  const rows = gate.mutation || [];
  if (!rows.length) return h("p", {}, status("none", "没做"), h("span", { class: "muted" }, "　参数扰动验证关着，或者需求单里没有你给的参数。"));
  const text = { constrained: (m) => `被 ${(m.caught_by || []).join("、")} 约束`, unbuildable: () => "无法单独扰动", unconstrained: () => "没有被约束" };
  const kind = { constrained: "ok", unbuildable: "none", unconstrained: "bad" };
  return h("div", {},
    h("table", { class: "table" }, h("tbody", {}, rows.map((m) => h("tr", {},
      h("td", { class: "mono" }, m.param),
      h("td", {}, status(kind[m.verdict] || "none", (text[m.verdict] || (() => m.verdict))(m))))))),
    (gate.skipped || []).length ? h("p", { class: "muted small" }, `参数超过 12 个，这些没有扰动：${gate.skipped.join("、")}`) : null);
}

function zoom(src, alt) {
  const dlg = document.getElementById("dialog");
  clear(dlg, h("form", { method: "dialog", class: "dialog-body zoom" }, h("img", { src, alt }), h("button", { type: "submit", class: "btn" }, "关闭")));
  dlg.showModal();
}

function reviewBlock(review, fileUrl) {
  if (!review) return h("p", {}, status("none", "没做"), h("span", { class: "muted" }, "　还没有交付过。"));
  if (review.skipped) return h("p", {}, status("none", `没做（${review.skipped}）`));
  const round = review.rounds || review.round;
  const thumbs = round ? h("div", { class: "review-views" }, VIEWS.map(([v, label]) => {
    const src = fileUrl("current", `review/round-${round}/${v}.png`);
    return h("button", { type: "button", class: "view-thumb", "aria-label": `放大${label}图`, onclick: () => zoom(src, label) },
      h("img", { src, alt: label }), h("span", { class: "small muted" }, label));
  })) : null;
  return h("div", {}, thumbs, h("table", { class: "table" }, h("tbody", {}, (review.items || []).map((i) => h("tr", {},
    h("td", {}, status(VERDICT[i.verdict] || "none", i.verdict)), h("td", {}, i.target), h("td", { class: "muted" }, i.reason))))));
}

export function renderChecks(panel, state, actions) {
  const checks = state.checks || [];
  const passed = checks.filter((c) => c.passed).length;
  if (!checks.length && !state.gate) {
    return clear(panel, h("div", { class: "bench-empty static" }, h("p", {}, "还没有检查结果。建模时每个阶段先写检查，运行以后实测的数字会列在这里。"),
      button("去对话里说", () => actions.focusInput(), { kind: "text" })));
  }
  clear(panel, h("div", { class: "pane" },
    h("div", { class: "big-count" }, h("span", { class: `num big ${passed === checks.length ? "ok" : "bad"}` }, `${passed === checks.length ? "✓" : "✗"} ${passed} / ${checks.length}`),
      h("span", { class: "muted small" }, "检查通过")),
    h("section", { "aria-labelledby": "h-checks" }, sectionHead("01", "检查", "", "h-checks"),
      h("table", { class: "table checks" },
        h("thead", {}, h("tr", {}, h("th", {}, "状态"), h("th", {}, "检查"), h("th", { class: "num" }, "实测"), h("th", { class: "num" }, "期望"),
          h("th", { class: "num" }, "容差"))),
        checkRows(checks, state.plan))),
    h("section", { "aria-labelledby": "h-mutation" }, sectionHead("02", "参数扰动验证", "", "h-mutation"), mutationBlock(state.gate)),
    h("section", { "aria-labelledby": "h-review" }, sectionHead("03", "看图审查", "", "h-review"), reviewBlock(state.review, actions.fileUrl))));
}

// 右栏的三个块：02 检查、03 需求单、04 版本。

import { add, clear, fileUrl, h, num } from "./dom.js";

export function renderChecks(el, checks) {
  clear(el);
  if (!checks.length) return el.append(h("p", { class: "empty", text: "还没有运行检查" }));
  const passed = checks.filter((c) => c.passed).length;
  const ordered = [...checks.filter((c) => !c.passed), ...checks.filter((c) => c.passed)];   // 没通过的排在前面
  el.append(
    h("div", { class: `big-number${passed < checks.length ? " bad" : ""}`, "aria-label": `通过 ${passed} 项，共 ${checks.length} 项`, text: `${passed}/${checks.length}` }),
    h("ul", { class: "check-list" }, ordered.map((c) => {
      const values = c.measured === null || c.measured === undefined ? "" : `${num(c.measured)} / ${num(c.expected)}`;
      return h("li", { class: c.passed ? "pass" : "fail", title: c.detail || "" },
        h("span", { class: "state", text: c.passed ? "通过" : "没通过" }),
        h("span", { class: "name mono", text: c.id }),
        h("span", { class: "values mono", text: values }),
      );
    })),
  );
}

export function renderBrief(el, brief) {
  clear(el);
  const params = brief.params || [];
  const part = brief.part || {};
  if (!part.name && !params.length) return el.append(h("p", { class: "empty", text: "还没有需求单" }));
  add(el,
    h("div", { class: "card-head" },
      h("h3", { class: "brief-name", text: part.name || "（还没起名）" }),
      h("span", { class: `confirm-state ${brief.confirmed ? "yes" : "no"}`, text: brief.confirmed ? "已确认" : "未确认" }),
    ),
    part.purpose ? h("p", { class: "brief-purpose", text: part.purpose }) : null,
  );
  if (params.length) {
    el.append(h("table", { class: "param-table" },
      h("thead", {}, h("tr", {}, h("th", { scope: "col", text: "名称" }), h("th", { scope: "col", text: "数值" }), h("th", { scope: "col", text: "来源" }))),
      h("tbody", {}, params.map((p) => h("tr", { title: p.note || "" },
        h("td", { class: "mono", text: p.name }),
        h("td", { class: "mono", text: `${num(p.value)} ${p.unit === "1" ? "" : p.unit}`.trim() }),
        h("td", {}, h("span", { class: `source ${p.source}`, text: p.source === "user" ? "用户" : "建议" })),
      ))),
    ));
  }
  if ((brief.features || []).length) el.append(h("ol", { class: "feature-list" }, brief.features.map((f) => h("li", { text: f }))));
  if ((brief.open_questions || []).length) {
    el.append(h("div", { class: "questions" }, h("strong", { text: "待确认的问题" }), brief.open_questions.map((q) => h("div", { text: q }))));
  }
}

// ui = { selected: [版本名…最多两个], diffs: Map<"a|b", {changes}|"loading"|"error"> }
export function renderVersions(el, state, ui, handlers) {
  clear(el);
  const versions = state.versions;
  if (!versions.length) return el.append(h("p", { class: "empty", text: "交付后在这里列出版本" }));
  const latest = versions[versions.length - 1].name;
  el.append(
    h("div", { class: "version-tabs", role: "group", "aria-label": "版本" }, versions.map((v) =>
      h("button", { class: "version-tab", type: "button", "aria-pressed": String(ui.selected.includes(v.name)), onclick: () => handlers.toggle(v.name) },
        v.name === latest ? h("span", { class: "current", title: "当前版本" }) : null, v.name))),
    h("p", { class: "version-hint", text: "点一个版本，上面的模型就换成它；再点另一个，比较两个版本。" }),
    h("ul", { class: "version-links" }, versions.map((v) =>
      h("li", {},
        h("span", { class: "vname", text: v.name }),
        h("a", { href: fileUrl(v.name, "model.step"), download: `${v.name}.step`, text: "STEP" }),
        v.has_stl ? h("a", { href: fileUrl(v.name, "model.stl"), download: `${v.name}.stl`, text: "STL" }) : null,
        v.has_png ? h("a", { href: fileUrl(v.name, "view.png"), target: "_blank", rel: "noopener", text: "截图" }) : null,
      ))),
  );
  if (ui.selected.length === 2) {
    const [a, b] = [...ui.selected].sort((x, y) => Number(x.slice(1)) - Number(y.slice(1)));
    const diff = ui.diffs.get(`${a}|${b}`);
    const changes = diff && diff.changes;
    el.append(h("div", { class: "diff" },
      h("h3", { class: "diff-title", text: `${a} → ${b} 的参数变化` }),
      changes ? h("ul", { class: "diff-list" }, changes.length ? changes.map((c) => h("li", { class: "mono", text: c })) : h("li", { text: "参数没有变化" }))
        : h("p", { class: "muted", text: diff === "error" ? "读取版本变化失败" : "正在读取…" }),
      h("div", { class: "diff-images" },
        [a, b].map((name) => h("figure", {}, h("img", { src: fileUrl(name, "view.png"), alt: `${name} 的截图` }), h("figcaption", { text: name }))),
      ),
    ));
  }
}

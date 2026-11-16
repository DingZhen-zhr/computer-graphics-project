// 工作台·版本：每个版本一行（缩略图、版本号、时间、变化、检查通过数）；勾两个版本对比参数和截图；下载、在文件夹中显示、存为案例。
import { button, clear, formDialog, h, sectionHead, status } from "./dom.js";
import { fmtTime } from "./format.js";

let ui = { sessionId: null, picked: [], diff: null, key: null };

function versionRow(v, state, actions, rerender) {
  const on = ui.picked.includes(v.name);
  const demo = !!(state.session && state.session.demo);
  const pick = h("input", { type: "checkbox", checked: on, "aria-label": `选 ${v.name} 来对比` });
  pick.addEventListener("change", () => {
    ui.picked = pick.checked ? [...ui.picked.filter((x) => x !== v.name), v.name].slice(-2) : ui.picked.filter((x) => x !== v.name);
    ui.diff = null;
    rerender();
  });
  const saveCase = async () => {
    const got = await formDialog(`把 ${v.name} 存为案例`, [{ name: "title", label: "标题", value: (state.brief && state.brief.part && state.brief.part.name) || "" },
      { name: "tags", label: "标签（用逗号或空格分开）", value: "", placeholder: "比如：安装板 孔阵列" }], "存为案例");
    if (!got) return;
    const tags = got.tags.split(/[\s,，、]+/).map((t) => t.trim()).filter(Boolean);
    await actions.saveCase(got.title.trim(), tags.length ? tags : [got.title.trim()]);
  };
  return h("li", { class: `version${on ? " picked" : ""}` },
    h("label", { class: "v-pick" }, pick),
    h("img", { class: "v-thumb", src: actions.fileUrl(v.name, "view.png"), alt: `${v.name} 的截图`, loading: "lazy" }),
    h("div", { class: "v-body" },
      h("div", { class: "v-head" }, h("span", { class: "v-name mono" }, v.name), h("span", { class: "muted small" }, fmtTime(v.created)),
        v.total ? status(v.passed === v.total ? "ok" : "bad", `检查 ${v.passed}/${v.total}`) : null),
      h("p", { class: "v-changes" }, (v.changes || []).length ? v.changes.join("；") : "参数没有变化"),
      h("div", { class: "v-actions" },
        h("a", { class: "btn small", href: actions.fileUrl(v.name, "model.step"), download: `${v.name}.step` }, "下载 STEP"),
        v.has_stl ? h("a", { class: "btn small", href: actions.fileUrl(v.name, "model.stl"), download: `${v.name}.stl` }, "下载 STL") : null,
        h("a", { class: "btn btn-text small", href: actions.fileUrl(v.name, "model.py"), download: `${v.name}.py` }, "源文件"),
        demo ? null : button("在文件夹中显示", () => actions.reveal(v.name), { kind: "text", small: true }),
        demo ? null : button("存为案例", saveCase, { kind: "text", small: true }))));
}

function compareBlock(state, actions, rerender) {
  if (ui.picked.length < 2) return h("p", { class: "muted small" }, "勾选两个版本，可以对比参数和截图。");
  const [a, b] = ui.picked.slice().sort((x, y) => Number(x.slice(1)) - Number(y.slice(1)));
  if (!ui.diff || ui.diff.a !== a || ui.diff.b !== b) {
    ui.diff = { a, b, lines: null };
    actions.diff(a, b).then((lines) => { if (ui.diff && ui.diff.a === a && ui.diff.b === b) { ui.diff.lines = lines; rerender(); } });
  }
  const lines = ui.diff.lines;
  return h("div", { class: "compare" },
    h("p", { class: "mono" }, `${a} → ${b}`),
    lines === null ? h("p", { class: "muted" }, "正在对比……")
      : lines.length ? h("ul", { class: "plain-list mono" }, lines.map((l) => h("li", {}, l))) : h("p", { class: "muted" }, "参数没有变化。"),
    h("div", { class: "compare-shots" }, [a, b].map((n) => h("figure", {}, h("img", { src: actions.fileUrl(n, "view.png"), alt: `${n} 的截图` }),
      h("figcaption", { class: "mono small" }, n)))));
}

function draw(panel, state, actions) {
  const versions = (state.versions || []).slice().reverse();
  const rerender = () => draw(panel, state, actions);
  if (!versions.length) {
    return clear(panel, h("div", { class: "bench-empty static" },
      h("p", {}, "还没有版本。第一个零件交付后，每一版都会列在这里，可以两两对比、下载和存为案例。"),
      button("去对话里说", () => actions.focusInput(), { kind: "text" })));
  }
  ui.picked = ui.picked.filter((n) => versions.some((v) => v.name === n));
  const list = h("section", { "aria-labelledby": "h-versions" }, sectionHead(ui.picked.length === 2 ? "02" : "01", "版本", `共 ${versions.length} 版`, "h-versions"),
    h("ol", { class: "versions" }, versions.map((v) => versionRow(v, state, actions, rerender))));
  const compare = h("section", { "aria-labelledby": "h-compare" }, sectionHead(ui.picked.length === 2 ? "01" : "02", "对比", "", "h-compare"),
    compareBlock(state, actions, rerender));
  // 勾了两个版本时，对比放在最上面，不用往下翻
  clear(panel, h("div", { class: "pane" }, ui.picked.length === 2 ? [compare, list] : [list, compare]));
}

export function renderVersions(panel, state, actions) {
  const sid = state.session ? state.session.id : null;
  if (sid !== ui.sessionId) ui = { sessionId: sid, picked: [], diff: null, key: null };
  const key = JSON.stringify([state.versions, state.brief && state.brief.part, !!(state.session && state.session.demo)]);
  if (key === ui.key && panel.childElementCount) return;
  ui.key = key;
  draw(panel, state, actions);
}

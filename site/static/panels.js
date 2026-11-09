// 右栏下半部分：02 检查、03 需求单、04 版本。

import { h, clear, fmtNum, fileUrl } from "./dom.js";

const BASIC = new Set(["valid", "single_solid", "positive_volume"]);
const TYPE_LABEL = { bbox: "尺寸", count: "计数", angle: "角度", point_inside: "有材料", point_outside: "无材料", distance: "距离", volume: "体积" };
const SOURCE_LABEL = { user: "用户", suggested: "建议" };

function valueText(c) {
  if (c.type === "point_inside" || c.type === "point_outside") return c.passed ? "符合" : "不符合";
  if (c.measured === null || c.measured === undefined) return c.passed ? "通过" : "没通过";
  return c.expected === null || c.expected === undefined ? fmtNum(c.measured, 2) : `${fmtNum(c.measured, 2)} / ${fmtNum(c.expected, 2)}`;
}

export function renderChecks(el, metaEl, checks) {
  if (!checks?.length) {
    metaEl.textContent = "";
    clear(el, h("div", { class: "empty" }, "还没有运行过。建模后，程序会逐条测量模型，和需求单对照。"));
    return;
  }
  const passed = checks.filter((c) => c.passed).length;
  const basic = checks.filter((c) => BASIC.has(c.id));
  const own = checks.filter((c) => !BASIC.has(c.id)).sort((a, b) => Number(a.passed) - Number(b.passed));
  const allOk = passed === checks.length;
  metaEl.textContent = "程序实测 · 实测 / 期望";
  const basicOk = basic.every((c) => c.passed);
  clear(el,
    h("div", { class: "score" }, h("span", { class: "big" }, String(passed)), h("span", { class: "of" }, `/${checks.length}`)),
    h("div", { class: `score-line ${allOk ? "ok" : "bad"}` }, allOk ? "全部通过" : `${checks.length - passed} 项没通过`),
    h("ul", { class: "check-list" },
      own.map((c) => h("li", { class: c.passed ? "" : "bad", title: c.detail || "" },
        h("span", { class: "dot", "aria-hidden": "true" }),
        h("span", { class: "cid" }, c.id, h("span", { class: "ctype" }, TYPE_LABEL[c.type] || c.type)),
        h("span", { class: "cval" }, valueText(c)))),
      basic.length
        ? h("li", { class: `basic ${basicOk ? "" : "bad"}` }, h("span", { class: "dot", "aria-hidden": "true" }),
            h("span", {}, `基础检查 ${basic.filter((c) => c.passed).length}/${basic.length}`, h("span", { class: "ctype" }, "实体有效 · 只有一个实体 · 体积大于 0")),
            h("span", { class: "cval" }, basicOk ? "通过" : "没通过"))
        : null));
}

export function renderBrief(el, metaEl, brief) {
  const params = brief?.params || [];
  const features = brief?.features || [];
  const questions = brief?.open_questions || [];
  if (!params.length && !features.length && !questions.length) {
    metaEl.textContent = "";
    clear(el, h("div", { class: "empty" }, "需求单还是空的。我问清楚尺寸后，会把每个参数和它的来源记在这里。"));
    return;
  }
  const users = params.filter((p) => p.source === "user").length;
  metaEl.textContent = brief.confirmed ? `已确认 · 用户给的 ${users} 项` : `未确认 · 用户给的 ${users} 项`;
  clear(el,
    params.length
      ? h("table", { class: "params" },
          h("thead", {}, h("tr", {}, h("th", {}, "参数"), h("th", {}, "数值"), h("th", {}, "来源"), h("th", {}, "说明"))),
          h("tbody", {}, params.map((p) => h("tr", {},
            h("td", { class: "pname" }, p.name),
            h("td", { class: "pval" }, `${fmtNum(p.value)}${p.unit === "1" ? "" : " " + p.unit}`),
            h("td", {}, h("span", { class: `badge ${p.source}` }, SOURCE_LABEL[p.source] || p.source)),
            h("td", { class: "pnote" }, p.note || "")))))
      : null,
    features.length ? [h("div", { class: "sub-head" }, "组成部分"), h("ol", { class: "features" }, features.map((f) => h("li", {}, f)))] : null,
    questions.length ? h("div", { class: "open-q" }, "还要问清楚：", h("ul", {}, questions.map((q) => h("li", {}, q)))) : null);
}

const noImage = (cls) => (e) => e.target.replaceWith(h("div", { class: `noimg ${cls}` }));

function thumb(v, cls = "") {
  if (v?.has_stl) return h("img", { "data-stl": fileUrl(v.name, "model.stl"), "data-png": v.has_png ? fileUrl(v.name, "view.png") : null, alt: `${v.name} 的模型`, class: cls, onerror: noImage(cls) });
  return v?.has_png ? h("img", { src: fileUrl(v.name, "view.png"), alt: `${v.name} 的截图`, loading: "lazy", class: cls, onerror: noImage(cls) }) : h("div", { class: `noimg ${cls}` });
}

function paramDiff(a, b) {
  const before = new Map((a.params || []).map((p) => [p.name, p]));
  const after = new Map((b.params || []).map((p) => [p.name, p]));
  const rows = [];
  for (const [name, p] of after) {
    const old = before.get(name);
    if (!old) rows.push({ name, from: null, to: p });
    else if (old.value !== p.value || old.unit !== p.unit) rows.push({ name, from: old, to: p });
  }
  for (const [name, p] of before) if (!after.has(name)) rows.push({ name, from: p, to: null });
  return rows;
}

const unitOf = (p) => (p.unit === "1" ? "" : ` ${p.unit}`);

export function renderVersions(el, metaEl, versions, ui) {
  if (!versions?.length) {
    metaEl.textContent = "";
    clear(el, h("div", { class: "empty" }, "每次交付都会存成一个版本（源文件、STEP、STL、截图、检查报告），可以两两对比。"));
    return;
  }
  metaEl.textContent = `${versions.length} 个版本`;
  const byName = new Map(versions.map((v) => [v.name, v]));
  const shown = byName.get(ui.shown) || versions[versions.length - 1];
  const nodes = versions.map((v) => h("button", {
    class: "vnode", type: "button", "aria-pressed": String(v.name === shown.name), onclick: () => ui.showVersion(v.name),
    title: `在上面的 3D 视图里显示 ${v.name}`,
  }, thumb(v), h("div", { class: "vname" }, v.name === versions[versions.length - 1].name ? h("span", { class: "square", "aria-hidden": "true" }) : null, v.name),
     h("div", { class: "vsub" }, `检查 ${v.passed}/${v.total}${v.changes?.length && v.name !== "v1" ? ` · ${v.changes.length} 处改动` : ""}`)));

  let compare = null;
  if (versions.length >= 2) {
    const b = shown.name === versions[0].name ? versions[1] : shown;
    const a = versions[versions.indexOf(b) - 1];
    const rows = paramDiff(a, b);
    compare = h("div", { class: "compare" },
      h("figure", {}, thumb(a), h("figcaption", {}, a.name, h("a", { href: fileUrl(a.name, "model.step"), download: `${a.name}.step` }, "STEP"))),
      h("figure", {}, thumb(b), h("figcaption", {}, b.name, h("a", { href: fileUrl(b.name, "model.step"), download: `${b.name}.step` }, "STEP"))),
      h("div", { class: "diff-box" },
        h("div", { class: "sub-head", style: "margin-top:0" }, `${a.name} → ${b.name} 的参数变化`),
        rows.length
          ? h("ul", { class: "diff-list" }, rows.map((r) => h("li", {},
              h("span", { class: "dname" }, r.name),
              h("span", { class: "dval" },
                r.from ? `${fmtNum(r.from.value)}${unitOf(r.from)}` : "新增",
                " → ",
                r.to ? h("b", {}, `${fmtNum(r.to.value)}${unitOf(r.to)}`) : "删除"))))
          : h("div", { class: "empty" }, "参数没有变化"),
        h("div", { class: "compare-pick" }, "点上面的版本卡片，可以换一个版本对比，并在 3D 里查看。")));
  }
  clear(el, h("div", { class: "timeline" }, nodes), compare);
}

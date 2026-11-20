// 造页面元素的小工具。文字一律走 textContent，不拼 HTML：模型说什么都不会被当成标签。

export const $ = (id) => document.getElementById(id);

// SVG 元素要用 SVG 的命名空间：从页面里那个空的 <svg id="svg-ns"> 上取（免得在脚本里写网址）
export function svgEl(tag, attrs = {}) {
  const el = document.createElementNS($("svg-ns").namespaceURI, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false || child === "") continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}

// 按钮：kind 是 "primary"（强调色实心）| "normal"（玻璃）| "text"（界面清单第 3 条）
export function button(label, onclick, { kind = "normal", small = false, ...attrs } = {}) {
  const cls = [kind === "primary" ? "btn-primary" : kind === "text" ? "btn-text" : "btn-glass", small ? "btn-small" : ""].filter(Boolean).join(" ");
  return h("button", { type: "button", class: cls, onclick, ...attrs }, label);
}

// 小节标题：等宽编号 + 标题 + 可选的说明；下面的尺寸线由样式画
export function sectionHead(no, title, meta = "", id = "") {
  return h("div", { class: "section-head" },
    h("span", { class: "section-no" }, no),
    h("h2", { class: "section-title", id: id || null }, title),
    meta ? h("span", { class: "section-meta" }, meta) : null);
}

// 状态：文字加符号，颜色只是辅助（界面清单第 5 条）
export function status(kind, text) {
  const mark = { ok: "✓", bad: "✗", none: "—" }[kind] || "—";
  return h("span", { class: `status ${kind}` }, `${mark} ${text}`);
}

// ---- 线条图标：从 index.html 的 <template id="icons"> 里复制（currentColor，读屏跳过） ----
export function icon(name) {
  const tpl = $("icons");
  const found = tpl ? tpl.content.querySelector(`[data-icon="${name}"]`) : null;
  return found ? found.cloneNode(true) : h("span", { class: "icon-missing", "aria-hidden": "true" });
}

// ---- 提示条和确认框 ----
let toastTimer = null;
export function toast(text) {
  const el = $("toast");
  if (!el) return;
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

// 确认框（用页面自己的 <dialog>，不用系统的 confirm）。返回 Promise<boolean>
export function confirmDialog(message, okLabel = "确定") {
  const dlg = $("dialog");
  return new Promise((resolve) => {
    const done = (v) => {
      dlg.close();
      resolve(v);
    };
    clear(dlg, h("form", { method: "dialog", class: "dialog-body", onsubmit: (e) => { e.preventDefault(); done(true); } },
      h("p", {}, message),
      h("div", { class: "dialog-actions" },
        button("取消", () => done(false)),
        h("button", { type: "submit", class: "btn-primary" }, okLabel))));
    dlg.oncancel = (e) => {
      e.preventDefault();
      done(false);
    };
    dlg.showModal();
    dlg.querySelector(".btn-glass").focus();   // 默认焦点在"取消"上，免得回车误删
  });
}

// 一组输入框的对话框：fields = [{name, label, value}]。确定返回 {name: value}，取消返回 null
export function formDialog(title, fields, okLabel = "保存") {
  const dlg = $("dialog");
  return new Promise((resolve) => {
    const inputs = fields.map((f) => h("input", { id: `dlg-${f.name}`, value: f.value || "", placeholder: f.placeholder || null }));
    const done = (ok) => {
      dlg.close();
      resolve(ok ? Object.fromEntries(fields.map((f, i) => [f.name, inputs[i].value])) : null);
    };
    clear(dlg, h("form", { class: "dialog-body", onsubmit: (e) => { e.preventDefault(); done(true); } },
      h("h3", {}, title),
      fields.map((f, i) => h("label", { class: "field", for: `dlg-${f.name}` }, h("span", {}, f.label), inputs[i])),
      h("div", { class: "dialog-actions" }, button("取消", () => done(false)), h("button", { type: "submit", class: "btn-primary" }, okLabel))));
    dlg.oncancel = (e) => {
      e.preventDefault();
      done(false);
    };
    dlg.showModal();
    if (inputs[0]) inputs[0].focus();
  });
}

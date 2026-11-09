// 小工具：用 DOM 方法建节点（一律 textContent，不拼 HTML，模型说的话里有什么都不会被当成代码执行）。

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  append(el, children);
  return el;
}

// 和 el.append 的区别：null、undefined、false 会被跳过（原生 append(null) 会写出文字 "null"）
export function add(el, ...children) {
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) append(el, child);
    else el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(el) {
  el.replaceChildren();
  return el;
}

// 数字：最多 4 位小数，去掉多余的 0；没有就是 "—"
export function num(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return String(Number(Number(v).toFixed(4)));
}

export function yuan(v) {
  return v === null || v === undefined ? null : `¥${Number(v).toFixed(2)}`;
}

export function fileUrl(version, name) {
  return `/files/${encodeURIComponent(version)}/${name}`;
}

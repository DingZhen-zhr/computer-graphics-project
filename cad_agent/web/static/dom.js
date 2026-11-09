// 小工具：造 DOM、格式化数字。文字一律用 textContent 放进去，不拼 HTML，模型说什么都不会被当成标签。

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
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false || child === "") continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el, ...children) {
  el.replaceChildren(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
}

export function fmtNum(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const n = Number(value);
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(digits).replace(/0+$/, "").replace(/\.$/, "");
}

export function fmtCost(value) {
  if (value === null || value === undefined) return null;
  return value < 0.01 ? `¥${value.toFixed(4)}` : `¥${value.toFixed(3)}`;
}

export function fmtPercent(ratio) {
  return ratio === null || ratio === undefined ? null : `${Math.round(ratio * 100)}%`;
}

export function fmtTokens(n) {
  if (!n) return "0";
  return n >= 10000 ? `${(n / 10000).toFixed(1)} 万` : String(n);
}

// 相对路径：本地服务和静态演示站（GitHub Pages 的子路径）都能用
export const fileUrl = (version, name) => `files/${encodeURIComponent(version)}/${name}`;

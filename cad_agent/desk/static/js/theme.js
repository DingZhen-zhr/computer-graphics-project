// 外观：浅色（图纸）、深色（蓝图）、跟随系统。写到根元素的 data-theme 上；切换后立刻存进设置。
import { post } from "./api.js";

export const THEMES = ["system", "light", "dark"];
export const THEME_LABELS = { system: "跟随系统", light: "浅色", dark: "深色" };
const listeners = new Set();
let current = "system";

export function currentTheme() {
  return current;
}

// 颜色只从 tokens.css 读（3D 材质也用它），脚本里不写颜色值
export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function applyTheme(theme) {
  current = THEMES.includes(theme) ? theme : "system";
  document.documentElement.dataset.theme = current;
  for (const fn of listeners) fn(current);
}

export function onThemeChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

// 跟随系统时，系统切换深浅也要通知（3D 材质要换色）
if (typeof window !== "undefined" && window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (current === "system") for (const fn of listeners) fn(current);
  });
}

export async function saveTheme(theme) {
  applyTheme(theme);
  return post("/api/settings", { theme: current });
}

export function nextTheme(theme) {
  return THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
}

// 抽屉：同一时间只开一个；点遮罩或按 Esc 关；打开时焦点移进去，关上时回到打开它的按钮。
import { $ } from "./dom.js";

let open = null;
let opener = null;
const closers = new Set();

export function openDrawer(id, from = document.activeElement) {
  closeAll();
  const el = $(id);
  if (!el) return;
  el.classList.add("on");
  el.removeAttribute("inert");
  $("scrim").classList.add("on");
  open = id;
  opener = from;
  const first = el.querySelector("button, [href], input, select, textarea, [tabindex]");
  if (first) setTimeout(() => first.focus(), 0);
}

export function closeAll() {
  if (open) {
    const el = $(open);
    el.classList.remove("on");
    el.setAttribute("inert", "");
    $("scrim").classList.remove("on");
    open = null;
    if (opener && opener.focus) opener.focus();
    opener = null;
  }
  for (const fn of closers) fn();
}

export const isOpen = (id) => open === id;
export function onEscape(fn) { closers.add(fn); }

export function setupDrawers() {
  for (const el of document.querySelectorAll(".drawer")) el.setAttribute("inert", "");
  $("scrim").addEventListener("click", closeAll);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAll(); });
  for (const btn of document.querySelectorAll("[data-close]")) btn.addEventListener("click", closeAll);
}

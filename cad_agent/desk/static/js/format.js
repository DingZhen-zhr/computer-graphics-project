// 数字、长度、费用、用量、时间、百分比的写法。纯逻辑，不碰页面。
// 长度最多保留两位小数并去掉末尾的 0（界面清单第 4 条）。

export function fmtNum(v) {
  if (v === null || v === undefined || v === "" || Number.isNaN(Number(v))) return "";
  const n = Math.round(Number(v) * 100) / 100;
  return String(Object.is(n, -0) ? 0 : n);
}

export function fmtLen(v, unit) {
  const n = fmtNum(v);
  if (n === "") return "";
  if (unit === "deg") return `${n}°`;
  if (!unit || unit === "1") return n;
  return `${n} ${unit}`;
}

export function fmtCost(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "";
  const n = Number(v);
  if (n > 0 && n < 0.01) return "<¥0.01";
  return `¥${n.toFixed(2)}`;
}

function trim(text) {
  return text.includes(".") ? text.replace(/0+$/, "").replace(/\.$/, "") : text;
}

export function fmtTokens(n) {
  const v = Number(n) || 0;
  if (v >= 1e6) return `${trim((v / 1e6).toFixed(2))}M`;
  if (v >= 1e3) return `${trim((v / 1e3).toFixed(1))}k`;
  return String(v);
}

export function fmtPct(a, b) {
  if (!b) return "";
  return `${Math.round((Number(a) / Number(b)) * 100)}%`;
}

const pad = (n) => String(n).padStart(2, "0");

export function fmtTime(iso, now = new Date()) {
  if (!iso) return "";
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return "";
  const minutes = (now.getTime() - t.getTime()) / 60000;
  if (minutes >= 0 && minutes < 1) return "刚刚";
  if (minutes >= 0 && minutes < 60) return `${Math.floor(minutes)} 分钟前`;
  const day = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((day(now) - day(t)) / 86400000);
  const hm = `${pad(t.getHours())}:${pad(t.getMinutes())}`;
  if (diffDays === 0) return `今天 ${hm}`;
  if (diffDays === 1) return `昨天 ${hm}`;
  if (t.getFullYear() === now.getFullYear()) return `${t.getMonth() + 1}月${t.getDate()}日`;
  return `${t.getFullYear()}年${t.getMonth() + 1}月${t.getDate()}日`;
}

// format.js（第二版计划 3 Task 8）。
import test from "node:test";
import assert from "node:assert/strict";
import { fmtCost, fmtLen, fmtNum, fmtPct, fmtTime, fmtTokens } from "../format.js";

test("fmtNum", () => {
  assert.equal(fmtNum(60), "60");
  assert.equal(fmtNum(12.50), "12.5");
  assert.equal(fmtNum(3.14159), "3.14");
  assert.equal(fmtNum(0.005), "0.01");
  assert.equal(fmtNum(-2), "-2");
  assert.equal(fmtNum(null), "");
  assert.equal(fmtNum(undefined), "");
});

test("fmtLen", () => {
  assert.equal(fmtLen(60, "mm"), "60 mm");
  assert.equal(fmtLen(65, "deg"), "65°");
  assert.equal(fmtLen(4, "1"), "4");
  assert.equal(fmtLen(12.345, "mm"), "12.35 mm");
  assert.equal(fmtLen(null, "mm"), "");
});

test("fmtCost", () => {
  assert.equal(fmtCost(0.1234), "¥0.12");
  assert.equal(fmtCost(null), "");
  assert.equal(fmtCost(undefined), "");
  assert.equal(fmtCost(0), "¥0.00");
  assert.equal(fmtCost(0.004), "<¥0.01");
});

test("fmtTokens", () => {
  assert.equal(fmtTokens(1234567), "1.23M");
  assert.equal(fmtTokens(8200), "8.2k");
  assert.equal(fmtTokens(999), "999");
  assert.equal(fmtTokens(2000000), "2M");
  assert.equal(fmtTokens(0), "0");
});

test("fmtPct", () => {
  assert.equal(fmtPct(89, 100), "89%");
  assert.equal(fmtPct(1, 0), "");
  assert.equal(fmtPct(1, 3), "33%");
});

test("fmtTime", () => {
  const now = new Date(2026, 10, 11, 15, 30, 0);
  const iso = (d) => new Date(d).toISOString();
  assert.equal(fmtTime(iso(new Date(2026, 10, 11, 15, 29, 40)), now), "刚刚");
  assert.equal(fmtTime(iso(new Date(2026, 10, 11, 15, 10)), now), "20 分钟前");
  assert.equal(fmtTime(iso(new Date(2026, 10, 11, 9, 5)), now), "今天 09:05");
  assert.equal(fmtTime(iso(new Date(2026, 10, 10, 22, 0)), now), "昨天 22:00");
  assert.equal(fmtTime(iso(new Date(2026, 9, 3, 8, 0)), now), "10月3日");
  assert.equal(fmtTime(iso(new Date(2025, 9, 3, 8, 0)), now), "2025年10月3日");
  assert.equal(fmtTime("", now), "");
  assert.equal(fmtTime("不是时间", now), "");
});

// api.js 里不碰浏览器的部分（第二版计划 3 Task 8）。
import test from "node:test";
import assert from "node:assert/strict";
import { backoffDelays, configure, eventsUrl } from "../api.js";

test("test_reconnect_backoff_sequence", () => {
  const d = backoffDelays();
  assert.deepEqual(d.slice(0, 6), [1000, 2000, 4000, 8000, 8000, 8000]);
  assert.ok(d.length >= 6 && d.every((x) => x <= 8000));
});

test("test_events_url_carries_since_and_token", () => {
  configure({ token: "abc 123" });
  assert.equal(eventsUrl("20261111-1", 42), "/api/sessions/20261111-1/events?since=42&t=abc%20123");
  assert.equal(eventsUrl("a/b", 0), "/api/sessions/a%2Fb/events?since=0&t=abc%20123");
});

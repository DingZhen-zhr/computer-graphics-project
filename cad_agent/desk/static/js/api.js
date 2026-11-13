// 和本机服务说话：每个请求带上本次启动的令牌；事件流断了按 1、2、4、8、8… 秒重连，接着上次收到的 seq。

let token = "";

export const OFFLINE = "连不上卡尺的本机服务。可以稍等一下再试，或者重新打开卡尺。";

export function configure(opts) {
  token = String((opts && opts.token) || "");
  // 只存在这个标签页自己的 sessionStorage 里（别的网站读不到）：按 F5 重新加载时服务端的小页面靠它重新进来
  try {
    if (token) sessionStorage.setItem("caliper.token", token);
  } catch { /* 存不了：重新加载时只能从窗口重开 */ }
  // 令牌不留在地址栏里，免得被复制出去
  if (typeof window !== "undefined" && window.history && window.location.search.includes("t=")) {
    const url = new URL(window.location.href);
    url.searchParams.delete("t");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }
}

export function tokenParam() {
  return `t=${encodeURIComponent(token)}`;
}

async function request(method, path, body) {
  const init = { method, headers: { "X-Caliper-Token": token } };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  try {
    const res = await fetch(path, init);
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { error: "服务返回的内容看不懂。" };
    }
    return { status: res.status, body: data };
  } catch {
    return { status: 0, body: { error: OFFLINE } };
  }
}

export const get = (path) => request("GET", path);
export const post = (path, body = {}) => request("POST", path, body);
export const del = (path) => request("DELETE", path);

export function backoffDelays(n = 12) {
  return Array.from({ length: n }, (_, i) => Math.min(1000 * 2 ** i, 8000));
}

export function eventsUrl(sessionId, since) {
  return `/api/sessions/${encodeURIComponent(sessionId)}/events?since=${since}&${tokenParam()}`;
}

// 订阅一个会话的事件。返回取消订阅的函数。onStatus("open" | "retrying")
export function subscribe(sessionId, since, onEvent, onStatus) {
  let last = since;
  let es = null;
  let attempt = 0;
  let timer = null;
  let closed = false;
  const delays = backoffDelays();

  const open = () => {
    if (closed) return;
    es = new EventSource(eventsUrl(sessionId, last));
    es.onopen = () => {
      attempt = 0;
      onStatus && onStatus("open");
    };
    es.onmessage = (msg) => {
      let ev;
      try {
        ev = JSON.parse(msg.data);
      } catch {
        return;
      }
      if (ev.seq) last = Math.max(last, ev.seq);
      onEvent(ev);
    };
    es.onerror = () => {
      es.close();
      if (closed) return;
      onStatus && onStatus("retrying");
      timer = setTimeout(open, delays[Math.min(attempt, delays.length - 1)]);
      attempt += 1;
    };
  };
  open();
  return () => {
    closed = true;
    clearTimeout(timer);
    if (es) es.close();
  };
}

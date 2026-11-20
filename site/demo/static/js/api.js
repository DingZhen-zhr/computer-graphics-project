// 和本机服务说话：每个请求带上本次启动的令牌；事件流断了按 1、2、4、8、8… 秒重连，接着上次收到的 seq。
// 静态回放（GitHub Pages 上的在线示例，根元素带 data-mode="static"）：没有服务，读导出的 state.json 和 files/，
// 写操作一律返回"只读"，不开事件流。

let token = "";
let tokenHeader = "";   // 请求头的名字由服务端写在页面的 <html data-token-header> 上，main.js 取来传进来

export const OFFLINE = "连不上 Datum 的本机服务。可以稍等一下再试，或者重新打开 Datum。";
export const READ_ONLY = "这是只读的在线示例，不能修改。想自己做零件，请先安装 Datum。";
const STATIC_MISSING = "在线示例里没有这一项。";
const STATIC_OFFLINE = "在线示例的数据没有加载出来，可以刷新页面再试。";
let staticState = null;

export function isStatic() {
  return typeof document !== "undefined" && !!document.documentElement && document.documentElement.dataset.mode === "static";
}

export function configure(opts) {
  token = String((opts && opts.token) || "");
  tokenHeader = String((opts && opts.tokenHeader) || "");
  if (isStatic()) return;
  // 只存在这个标签页自己的 sessionStorage 里（别的网站读不到）：按 F5 重新加载时服务端的小页面靠它重新进来
  try {
    if (token) sessionStorage.setItem("datum.token", token);
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
  const init = { method, headers: tokenHeader ? { [tokenHeader]: token } : {} };
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

// ---- 静态回放 ----
function loadStatic() {
  if (!staticState) {
    staticState = fetch("state.json").then((res) => {
      if (!res.ok) throw new Error(String(res.status));
      return res.json();
    });
    staticState.catch(() => { staticState = null; });   // 失败了下次再试
  }
  return staticState;
}

function staticBoot() {
  return { static: true, ready: true, version: "", platform: "web", providers: [], key: { source: null },
    settings: { theme: "system", provider: "", model: "" } };
}

async function staticGet(path) {
  let st;
  try {
    st = await loadStatic();
  } catch {
    return { status: 0, body: { error: STATIC_OFFLINE } };
  }
  const [route, query] = path.split("?");
  if (route === "/api/boot") return { status: 200, body: staticBoot() };
  if (route === "/api/sessions") {
    const s = st.session || {};
    return { status: 200, body: [{ id: s.id, title: s.title, demo: true, updated: "", versions: (st.versions || []).length }] };
  }
  if (/^\/api\/sessions\/[^/]+\/state$/.test(route)) return { status: 200, body: st };
  if (/^\/api\/sessions\/[^/]+\/diff$/.test(route)) {
    const q = new URLSearchParams(query || "");
    const lines = (st.static_diffs || {})[`${q.get("a")}|${q.get("b")}`];
    return lines ? { status: 200, body: { lines } } : { status: 404, body: { error: STATIC_MISSING } };
  }
  return { status: 404, body: { error: STATIC_MISSING } };
}

const readOnly = () => Promise.resolve({ status: 403, body: { error: READ_ONLY } });

export const get = (path) => (isStatic() ? staticGet(path) : request("GET", path));
export const post = (path, body = {}) => (isStatic() ? readOnly() : request("POST", path, body));
export const del = (path) => (isStatic() ? readOnly() : request("DELETE", path));

// 一个版本里的文件：本机服务要带令牌；在线示例是导出目录里的相对路径
export function fileUrl(sessionId, version, name) {
  if (isStatic()) return `files/${version}/${name}`;
  return `/files/${encodeURIComponent(sessionId)}/${version}/${name}?${tokenParam()}`;
}

export function backoffDelays(n = 12) {
  return Array.from({ length: n }, (_, i) => Math.min(1000 * 2 ** i, 8000));
}

export function eventsUrl(sessionId, since) {
  return `/api/sessions/${encodeURIComponent(sessionId)}/events?since=${since}&${tokenParam()}`;
}

// 订阅一个会话的事件。返回取消订阅的函数。onStatus("open" | "retrying")
export function subscribe(sessionId, since, onEvent, onStatus) {
  if (isStatic()) return () => {};   // 在线示例不会变，没有事件
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

// 首次引导：选模型服务 → 填密钥并测试连接 → 完成。顶上一条尺寸线标出走到第几步；任何一步都能点"先看看示例"跳过。
import { get, post } from "./api.js";
import { button, clear, h, status } from "./dom.js";

const KEY_NOTE = "密钥只保存在这台电脑的系统钥匙串里（Windows 的凭据管理器、Mac 的钥匙串），不会写进任何文件，也不会发到模型服务以外的地方。";
const ENV_NOTE = (name) => `已经从环境变量 ${name} 读到密钥，不用再填。`;
const STEPS = ["模型服务", "密钥", "完成"];
const BLURB = {
  deepseek: "默认的服务，Datum 主要按它调过。",
  glm: "智谱的 OpenAI 兼容接口。",
  kimi: "月之暗面的 OpenAI 兼容接口。",
  qwen: "阿里云百炼的 OpenAI 兼容接口。",
  openai: "OpenAI 官方接口，能看图。",
  claude: "Anthropic 官方接口，能看图。",
  custom: "其他 OpenAI 兼容的服务，自己填地址和模型名。",
};

function ruler(at) {
  return h("ol", { class: "ruler steps", "aria-label": "引导进度" }, STEPS.map((label, i) =>
    h("li", { class: `tick${i < at ? " done" : ""}${i === at ? " current" : ""}`, "aria-current": i === at ? "step" : null },
      h("span", { class: "tick-mark" }), h("span", { class: "tick-label" }, `${i + 1} ${label}`))));
}

export function renderOnboarding(el, actions) {
  const st = { step: 0, boot: actions.boot(), provider: actions.boot().settings.provider, custom: { base_url: "", model: "" }, result: null, busy: false };
  const draw = () => {
    const providers = st.boot.providers;
    const skip = button("先看看示例", () => actions.openDemo(), { kind: "text" });
    let body;
    if (st.step === 0) {
      body = [
        h("h1", { class: "page-title" }, "先选一个模型服务"),
        h("p", { class: "muted" }, "Datum 用你自己的大模型账号来理解需求、写建模代码。以后可以在设置里换。"),
        h("div", { class: "choice-list", role: "radiogroup", "aria-label": "模型服务" }, providers.map((p) => {
          const on = p.id === st.provider;
          return h("button", { type: "button", role: "radio", "aria-checked": String(on), class: `choice${on ? " on" : ""}`,
            onclick: () => { st.provider = p.id; draw(); } }, h("span", { class: "choice-name" }, p.name), h("span", { class: "muted small" }, BLURB[p.id] || ""));
        })),
        st.provider === "custom" ? h("div", { class: "field-row" },
          h("label", { class: "field" }, h("span", {}, "接口地址"), h("input", { value: st.custom.base_url, placeholder: "服务商文档里的地址，一般以 /v1 结尾",
            oninput: (e) => { st.custom.base_url = e.target.value; } })),
          h("label", { class: "field" }, h("span", {}, "模型名"), h("input", { value: st.custom.model, oninput: (e) => { st.custom.model = e.target.value; } }))) : null,
        st.result ? h("p", { role: "status" }, status(st.result.ok ? "ok" : "bad", st.result.message)) : null,
        h("div", { class: "page-actions" }, button("下一步", async () => {
          const body2 = { provider: st.provider, model: "", base_url: "" };
          if (st.provider === "custom") Object.assign(body2, { base_url: st.custom.base_url.trim(), model: st.custom.model.trim() });
          const res = await post("/api/settings", body2);
          if (res.status !== 200) {
            st.result = { ok: false, message: res.body.error };
            return draw();
          }
          st.boot = (await get("/api/boot")).body;
          actions.setBoot(st.boot);
          st.step = 1;
          st.result = null;
          draw();
        }, { kind: "primary" }), skip),
      ];
    } else if (st.step === 1) {
      const key = st.boot.key;
      const input = h("input", { type: "password", class: "key-input", autocomplete: "off", spellcheck: "false", "aria-label": "密钥" });
      const test = async () => {
        st.busy = true;
        st.result = null;
        draw();
        if (key.source !== "env") {
          const v = input.value;
          if (v.trim()) {
            const saved = await post("/api/key", { provider: st.provider, key: v });
            if (saved.status !== 200) {
              st.busy = false;
              st.result = { ok: false, message: saved.body.error };
              return draw();
            }
          }
        }
        st.boot = (await get("/api/boot")).body;
        actions.setBoot(st.boot);
        const res = await post("/api/test-connection", {});
        st.busy = false;
        st.result = res.status === 200 ? res.body : { ok: false, message: res.body.error };
        draw();
      };
      body = [
        h("h1", { class: "page-title" }, "填上密钥"),
        key.source === "env" ? h("p", {}, status("ok", ENV_NOTE(key.env)))
          : [h("label", { class: "field wide" }, h("span", {}, key.source ? `已经存了一个（${key.hint}），要换就填新的` : `${(st.boot.providers.find((p) => p.id === st.provider) || {}).name || ""} 的 API key`), input),
            h("p", { class: "muted small note-block" }, KEY_NOTE)],
        st.result ? h("p", { role: "status" }, status(st.result.ok ? "ok" : "bad", st.result.message)) : null,
        h("div", { class: "page-actions" },
          button(st.busy ? "正在测试……" : "测试连接", test, { disabled: st.busy }),
          button("下一步", () => { st.step = 2; draw(); }, { kind: "primary", disabled: !st.boot.ready }),
          button("上一步", () => { st.step = 0; draw(); }, { kind: "text" }), skip),
      ];
    } else {
      body = [
        h("h1", { class: "page-title" }, "可以开始了"),
        h("p", { class: "muted" }, "说说你想做什么零件，Datum 会先问清楚尺寸，再一个阶段一个阶段地建模，每一步都由程序实测。"),
        h("div", { class: "page-actions" }, button("开始第一个零件", () => actions.start(), { kind: "primary" }), skip),
      ];
    }
    clear(el, h("div", { class: "page-narrow onboarding" }, ruler(st.step), body));
  };
  draw();
}

// 设置页：占满工作区，左边小节目录。每一项改了就存（设置文件里没有密钥；密钥走钥匙串）。
import { del, get, post } from "./api.js";
import { button, clear, confirmDialog, h, sectionHead, status } from "./dom.js";
import { saveTheme } from "./theme.js";

const GATES = [
  ["staged", "分阶段", "把零件拆成几个阶段，一个阶段验证通过了再做下一个。关掉后退回到一次做完的老流程。"],
  ["mutation_check", "参数扰动验证", '交付前把每个参数改掉 20% 试一次，确认检查真的管得住它。关掉后交付更快，但"参数没起作用"这类问题不会被发现。'],
  ["visual_review", "看图审查", "交付前让模型只看渲染图再核对一遍形状。需要能看图的模型。"],
  ["cases", "案例库", "规划时参考以前做成功的相似零件。"],
];
const SECTIONS = [["service", "模型服务"], ["key", "密钥"], ["vision", "看图审查"], ["price", "价格"], ["flow", "流程"], ["look", "外观"], ["data", "数据"], ["about", "关于"]];
const SOURCE = { env: "环境变量", keyring: "系统钥匙串" };

function field(label, control, hint = "") {
  return h("label", { class: "field" }, h("span", {}, label), control, hint ? h("span", { class: "muted small" }, hint) : null);
}

function block(id, no, title, ...children) {
  return h("section", { id: `set-${id}`, class: "set-block", "aria-labelledby": `h-set-${id}` }, sectionHead(no, title, "", `h-set-${id}`), children);
}

export function renderSettings(el, actions) {
  let boot = actions.boot();
  let note = {};   // 各小节最近一次操作的结果：{小节: {ok, message}}
  const save = async (patch, where) => {
    const res = await post("/api/settings", patch);
    if (res.status !== 200) {
      note[where] = { ok: false, message: res.body.error };
    } else {
      boot = (await get("/api/boot")).body;
      actions.setBoot(boot);
      note[where] = { ok: true, message: "已保存。" };
    }
    draw();
  };
  const shout = (where) => (note[where] ? h("p", { class: "set-note", role: "status" },
    status(note[where].ok === null ? "none" : note[where].ok ? "ok" : "bad", note[where].message)) : null);

  function service(s, prov) {
    const list = h("datalist", { id: "models-list" }, (prov.models || []).map((m) => h("option", { value: m })));
    return block("service", "01", "模型服务",
      field("服务", h("select", { onchange: (e) => save({ provider: e.target.value, model: "", base_url: "" }, "service") },
        boot.providers.map((p) => h("option", { value: p.id, selected: p.id === s.provider }, p.name)))),
      field("模型名", h("input", { value: s.model, placeholder: prov.models[0] || "填模型名", list: "models-list", onchange: (e) => save({ model: e.target.value.trim() }, "service") }),
        "留空就用预设里的第一个"),
      list,
      field("接口地址", h("input", { value: s.base_url, placeholder: prov.base_url || "服务商文档里的地址，一般以 /v1 结尾", onchange: (e) => save({ base_url: e.target.value.trim() }, "service") }),
        "留空就用预设的地址"),
      shout("service"));
  }

  function key(s) {
    const k = boot.key;
    const input = h("input", { type: "password", autocomplete: "off", spellcheck: "false", "aria-label": "新的密钥" });
    const run = async (fn, where) => {
      note[where] = { ok: null, message: "正在处理……" };
      draw();
      note[where] = await fn();
      boot = (await get("/api/boot")).body;
      actions.setBoot(boot);
      draw();
    };
    return block("key", "02", "密钥",
      h("p", {}, "来源：", h("strong", {}, k.source ? SOURCE[k.source] : "还没有"), k.hint ? h("span", { class: "mono" }, `　${k.hint}`) : null),
      k.source === "env" ? h("p", { class: "muted small" }, `来自环境变量 ${k.env}，要换就改环境变量；这里不能删。`) : null,
      k.source === "env" ? null : field(k.source ? "更换" : "填上密钥", input),
      h("div", { class: "page-actions" },
        k.source === "env" ? null : button(k.source ? "更换" : "保存", () => run(async () => {
          const r = await post("/api/key", { provider: s.provider, key: input.value });
          return r.status === 200 ? { ok: true, message: "已存进系统钥匙串。" } : { ok: false, message: r.body.error };
        }, "key")),
        k.source === "keyring" ? button("删除", async () => {
          if (!(await confirmDialog("从系统钥匙串里删除这个服务的密钥？删除后要重新填才能用。", "删除"))) return;
          run(async () => {
            const r = await del(`/api/key?provider=${encodeURIComponent(s.provider)}`);
            return r.status === 200 ? { ok: true, message: "已删除。" } : { ok: false, message: r.body.error };
          }, "key");
        }) : null,
        button("测试连接", () => run(async () => {
          const r = await post("/api/test-connection", {});
          return r.status === 200 ? r.body : { ok: false, message: r.body.error };
        }, "key"))),
      shout("key"));
  }

  function vision(s, prov) {
    const on = s.vision === "on" || (s.vision === "auto" && prov.vision === "yes");
    const why = s.vision === "on" ? "测试识图通过了，或者你手动打开了。" : s.vision === "off" ? "你手动关掉了。"
      : prov.vision === "yes" ? "这个服务的文档写明能看图。" : '还不知道这个模型能不能看图，先按不能处理。可以点"测试识图"试一下（会花一点点钱）。';
    const reviewProv = boot.providers.find((p) => p.id === (s.review_provider || s.provider)) || prov;
    return block("vision", "03", "看图审查",
      h("p", {}, status(on ? "ok" : "none", on ? "开着" : "关着"), h("span", { class: "muted" }, `　${why}`)),
      h("div", { class: "page-actions" }, button("测试识图", async () => {
        note.vision = { ok: null, message: "正在测试……" };
        draw();
        const r = await post("/api/test-vision", {});
        note.vision = r.status === 200 ? r.body : { ok: false, message: r.body.error };
        boot = (await get("/api/boot")).body;
        actions.setBoot(boot);
        draw();
      })),
      field("审查用的服务", h("select", { onchange: (e) => save({ review_provider: e.target.value === s.provider ? "" : e.target.value, review_model: "" }, "vision") },
        boot.providers.map((p) => h("option", { value: p.id, selected: p.id === (s.review_provider || s.provider) }, p.name))), "不选就和上面的服务一样"),
      field("审查用的模型", h("input", { value: s.review_model, placeholder: reviewProv.models[0] || "", onchange: (e) => save({ review_model: e.target.value.trim() }, "vision") })),
      shout("vision"));
  }

  let priceDraft = null;   // 正在填的三个价格（重画页面时不丢）
  function price(s) {
    const p = s.pricing || {};
    const keys = ["input_hit", "input_miss", "output"];
    const names = ["输入（命中缓存）的价格", "输入（没命中）的价格", "输出的价格"];
    const draft = priceDraft || keys.map((k) => (p[k] ?? "") === "" ? "" : String(p[k]));
    const inputs = keys.map((k, i) => h("input", { class: "num", inputmode: "decimal", value: draft[i], "aria-label": names[i], dataset: { key: k } }));
    const commit = () => {
      const vals = inputs.map((i) => i.value.trim());
      priceDraft = vals;
      if (vals.some((v) => v !== "" && (Number.isNaN(Number(v)) || Number(v) < 0))) {
        note.price = { ok: false, message: "价格要填不小于 0 的数（元 / 百万 token）。" };
        return draw();
      }
      if (vals.every((v) => v === "")) {
        priceDraft = null;
        return save({ pricing: null }, "price");
      }
      if (vals.some((v) => v === "")) {
        note.price = null;
        return undefined;   // 还没填完：等三个都填了再存
      }
      priceDraft = null;
      return save({ pricing: { input_hit: Number(vals[0]), input_miss: Number(vals[1]), output: Number(vals[2]) } }, "price");
    };
    inputs.forEach((i) => i.addEventListener("change", commit));
    return block("price", "04", "价格",
      h("p", { class: "muted small" }, "照你用的模型的价目页填，不填就只显示 token 数。单位是元 / 每百万 token，三个都填了才会存。"),
      h("div", { class: "field-row" }, field("输入（命中缓存）", inputs[0]), field("输入（没命中）", inputs[1]), field("输出", inputs[2])),
      shout("price"));
  }

  function flow(s) {
    return block("flow", "05", "流程", GATES.map(([k, label, text]) => h("label", { class: "toggle" },
      h("input", { type: "checkbox", checked: !!s.gates[k], onchange: (e) => save({ gates: { ...s.gates, [k]: e.target.checked } }, "flow") }),
      h("span", { class: "toggle-text" }, h("strong", {}, label), h("span", { class: "muted small" }, text)))), shout("flow"));
  }

  function look(s) {
    return block("look", "06", "外观", h("div", { class: "radio-row", role: "radiogroup", "aria-label": "外观" },
      [["light", "浅色（图纸）"], ["dark", "深色（蓝图）"], ["system", "跟随系统"]].map(([v, label]) => h("label", { class: "radio" },
        h("input", { type: "radio", name: "theme", value: v, checked: s.theme === v, onchange: async () => { await saveTheme(v); boot = (await get("/api/boot")).body; actions.setBoot(boot); draw(); } }),
        label))));
  }

  function data() {
    return block("data", "07", "数据",
      h("p", {}, "会话、案例和设置都在：", h("span", { class: "mono path" }, boot.data_dir)),
      h("div", { class: "page-actions" }, button("打开文件夹", async () => { const r = await post("/api/open-data", {}); if (r.status !== 200) actions.toast(r.body.error); })));
  }

  function about() {
    return block("about", "08", "关于", h("table", { class: "table about" }, h("tbody", {},
      [["卡尺", boot.version], ["SimpleCADAPI", boot.sca_version || "没装好"], ["Python", boot.python]].map(([k, v]) => h("tr", {}, h("td", {}, k), h("td", { class: "mono" }, v))))),
      h("p", { class: "muted small" }, "更新到最新版：在终端里运行 ", h("code", {}, "caliper update")));
  }

  function draw() {
    const s = boot.settings;
    const prov = boot.providers.find((p) => p.id === s.provider) || boot.providers[0];
    const nav = h("nav", { class: "set-nav", "aria-label": "设置的小节" }, h("ol", {}, SECTIONS.map(([id, label], i) => h("li", {},
      h("a", { href: `#set-${id}`, onclick: (e) => { e.preventDefault(); document.getElementById(`set-${id}`).scrollIntoView(); } },
        h("span", { class: "mono" }, String(i + 1).padStart(2, "0")), label)))),
    button("返回", () => actions.close(), { kind: "text" }));
    const scrollTop = el.querySelector(".set-body")?.scrollTop || 0;
    clear(el, h("div", { class: "settings" }, nav, h("div", { class: "set-body" },
      h("h1", { class: "page-title" }, "设置"), service(s, prov), key(s), vision(s, prov), price(s), flow(s), look(s), data(), about())));
    el.querySelector(".set-body").scrollTop = scrollTop;
  }
  draw();
}

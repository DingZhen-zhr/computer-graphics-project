# 卡尺桌面端 · 界面清单

> 第二版计划 3「界面这部分开工之前」要求的文件：上半部分是 `ui-consistency:finding-patterns` 梳理出来的写法，
> 下半部分是计划原文的"界面清单"（逐字照抄）。Task 8 到 Task 12 每做完一个画面逐条对照；走查结果记在各任务的进度里。

## 一、梳理结果（finding-patterns，2026-11-11）

桌面端各画面 against "单页工作台"（三栏 + 顶栏 + 页签；决定种类的依据：计划 3 的页面结构）——
参照页是旧网页 `cad_agent/web/static/`（同一种页面里唯一已经存在的一页；计划 4 会退役它），
1 个成员 / 1 个候选，范围是 `cad_agent/web/static/` 和 `cad_agent/desk/static/`，读于 2026-11-11。

只有参照页一个成员，所以下面没有一条是"多数页面的约定"；每一条写明是什么定下来的：
计划原文（用户已经议定的设计，最高一级）、或者是参照页里值得沿用的写法（参照页本身）。
参照页的视觉数值（白底、`#0071E3` 蓝、圆角卡片、毛玻璃、阴影）**一律不沿用**：计划 3 的 Global Constraints 换掉了整套视觉。

- [ ] 主题 —— 只有一份：`cad_agent/desk/static/css/tokens.css`（`:root` 浅色、`[data-theme="dark"]` 深色、`[data-theme="system"]` 跟随系统），根元素上的 `data-theme` 由 `theme.js` 写 —— 计划 Task 2 的 Interfaces。没有 `DESIGN.md`。
- [ ] 间距 —— 基数 4（`--s-1` 到 `--s-6` 是 4、8、12、16、24、32，都是 4 的整数倍）；页面上只写 `var(--s-n)`，不写别的像素间距 —— 计划 Task 2。控件高度：按钮 28px、小按钮 24px（`base.css`）。
- [ ] 字 —— 正文 14px / 行高 1.6 / `--font-ui`（`base.css` 的 `body`）；小节标题 13px、粗 600、字距 .06em；小节编号 11px 等宽 `--ink-2`；小字 12px（`.small`）；数字、参数名、工具调用、代码用 `--font-mono` 加等宽数字（`.mono`、`.num`）—— 计划 Global Constraints + `base.css`。字号单位 px（不随系统文字缩放，记作事实）。
- [ ] 造 DOM —— 只用 `dom.js` 的 `h(tag, attrs, ...children)` 和 `clear(el, ...children)`；文字一律走 `textContent`，**不用 `innerHTML`**，模型说什么都不会被当成标签 —— 参照页（`web/static/dom.js`，参照页 5 个脚本里 `innerHTML` 出现 0 次）。
- [ ] 小节 —— `<section aria-labelledby="…">` 里一个 `.section-head`：`<span class="section-no">01</span><h2 class="section-title" id="…">…</h2>` 加可选的 `.section-meta`；下面的尺寸线由 `.section-head` 的下边线和两端短竖线画出 —— 计划界面清单第 2 条（写法）+ 参照页（元素和 `aria-labelledby`，4 个小节 4 个都这样）。
- [ ] 标题层级 —— 页面上只有一个 `h1`（顶栏的产品名不是标题，用普通文字）；工作台各页签和设置页各节的标题是 `h2`；卡片里的小标题是 `h3` —— 参照页（`h1` 零件名、`h2` 四个小节）。
- [ ] 按钮 —— 一律是 `<button type="button">`，三种 class：`btn btn-primary`、`btn`、`btn btn-text`；一个画面里 `btn-primary` 最多一个；开关类按钮用 `aria-pressed` 表示当前状态 —— 计划界面清单第 3 条 + 参照页（`aria-pressed` 的写法）。
- [ ] 图标 —— 内联的 `<svg>`，`aria-hidden="true"`，颜色用 `currentColor`；只有图标的按钮要有 `aria-label` 和 `title` —— 参照页（3 个图标按钮都这样）。
- [ ] 实时区域 —— 对话列表 `role="log" aria-live="polite"`；连接断开那一行和提示条 `role="status" aria-live="polite"` —— 参照页。
- [ ] 3D 视图 —— three.js r160 从 `/static/vendor/three/` 取（import map 把 `three` 指到 `three.module.js`）；材质颜色从 CSS 变量读（`getComputedStyle`），换主题时更新 —— 计划 Task 10 + 界面清单第 1 条。
- [ ] 出错 —— 接口返回的 `{"error": "中文说明"}` 原样给用户看，再给一个下一步；前端自己不拼异常文字、不显示堆栈 —— 计划界面清单第 7 条；后端已保证错误体是中文（Task 6 的 `test_error_bodies_are_chinese_json`）。
- [ ] 不从参照页照抄：它的配色和圆角卡片、毛玻璃登录框、`fmtTokens` 的"万"写法（计划规定 `1.23M`、`8.2k`）、`fmtCost` 的三四位小数（计划规定 `¥0.12`）、每 1.5 秒一次的轮询（改成 SSE 推送）。

## 二、界面清单（计划原文，每个画面都要满足）

1. 颜色只用 `tokens.css` 里的变量，页面和脚本里不出现颜色的字面值（3D 材质的颜色也从变量读）。
2. 每个小节的标题是同一个写法：等宽的小号编号加标题，下面一条带两端短竖线的尺寸线。
3. 按钮只有三种：主要（强调色描边加强调色文字）、普通（主线色描边）、文字按钮（无边框）。一个画面里主要按钮最多一个。
4. 数字一律等宽、右对齐，带单位；长度保留到小数点后最多 2 位，去掉末尾的 0。
5. 状态用文字加符号表示（`✓ 通过`、`✗ 没通过`、`— 没做`），颜色只是辅助，不单靠颜色区分。
6. 空状态写一句说明加一个可以点的下一步，不留白。
7. 出错时说清发生了什么、接下来可以怎么做；不显示原始的异常文字和堆栈。
8. 可以点的东西都能用键盘到达，焦点有看得见的描边（强调色，2px）。
9. 浅色和深色都看过；文字和底色的对比度不低于 4.5:1。
10. 1100×700 和 1600×1000 两个窗口大小都看过。

## 梳理花了多少

打开项目文件 4 个（`web/static/dom.js`、`index.html`、`style.css` 的计数、`desk/static/css/base.css`），搜索 5 次；读了技能的 `finding-patterns`、`values` 两份说明和 `words.md`、`checklist.md`。没有用子代理。

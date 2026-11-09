# CAD 建模智能体（AICG Project 3）

一个命令行 CAD 建模智能体：用自然语言说需求，它会追问、整理成需求单、等你确认，然后用 [SimpleCADAPI](https://pypi.org/project/simplecadapi/)（下面简称 SCA）按特征建模，由程序自动测量检查；检查不过会自动修改重试（最多 3 次），通过后导出 STEP 文件和截图，并且支持多轮修改。

核心思路：**程序管流程，模型只做判断**。需求单是否确认、检查是否通过、能不能交付，都由程序判定；模型只负责理解需求、写每个特征的几行建模代码、写检查项。所以换任何大模型都能用，只要改配置文件。

## 安装

要求：Windows 或其他系统，Python 3.10–3.13。在项目目录里执行（PowerShell）：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

这会装好 `simplecadapi[editor,verify]==2.2.7`、`openai`、`pyyaml` 和测试用的 `pytest`。所有命令都用 `.venv\Scripts\python`，不要往系统 Python 里装包。

## 配置模型

1. 把示例配置复制一份：

   ```powershell
   Copy-Item config.example.toml config.toml
   ```

   `config.toml` 里是模型地址、模型名、key 所在的环境变量名、超时和重试上限。默认用 DeepSeek；换成 GLM、通义、Kimi 等任何 OpenAI 兼容接口，只改 `[llm]` 里的 `base_url`、`model`、`api_key_env`，不用改代码。`config.toml` 已在 `.gitignore` 里，不会被提交。

   还有几项可选的设置（都在 `config.example.toml` 里用注释写出来了，不写就和以前完全一样）：

   - `extra_body`（写在 `[llm]` 里）：原样作为请求的 `extra_body` 发给接口，程序不认识里面的内容。比如 DeepSeek 实测可以这样关掉思考（`docs/llm-api-notes.md` 第 4 节）：`extra_body = {thinking = {type = "disabled"}}`。
   - `[llm.pricing]`：`input_hit`、`input_miss`、`output` 三项，单位是 元 / 百万 token，**照模型服务的价目页自己填**（代码里不放任何价格）。填了以后每轮结束会显示本轮的大概费用，评测报告里也会有费用。
   - `[llm.clarify]`（澄清阶段，需求单还没确认）和 `[llm.modeling]`（建模阶段，需求单已确认）：可以单独换 `model`、`temperature`、`extra_body`、`pricing`，没写的项沿用 `[llm]`；`extra_body` 是整体替换，不合并。一轮开始时按需求单有没有确认决定用哪个模型，这一轮里不换。例如只让澄清阶段不思考：

     ```toml
     [llm.clarify]
     extra_body = {thinking = {type = "disabled"}}
     ```

2. **API key 只放在环境变量里，不写进任何文件。** 在 PowerShell 里这样设置（把引号里换成你自己的 key；只对当前这个终端窗口有效）：

   ```powershell
   $env:DEEPSEEK_API_KEY="这里换成你的key"
   ```

   如果 `api_key_env` 改成了别的名字，就设置那个名字的变量。没设置时程序会提示“请先设置环境变量 …”并退出。

## 运行

```powershell
.venv\Scripts\python -m cad_agent --config config.toml
```

启动时会打印 Python、simplecadapi、模型名的版本，并写进会话日志。然后直接说出你想做的零件，例如：

> 做一个放在桌上看视频的小支架

典型过程：

1. **澄清**：助手会追问影响能不能用的关键尺寸（比如手机多大），并给出建议值；你可以直接回答“可以”。
2. **确认**：需求单完整后，助手把需求单展示给你，标出每个参数是“用户给的”还是“智能体建议”的。回复「确认」才会开始建模；如果回复里夹带了修改（比如“可以，但角度改成 70”），不算确认，会把这句话原样交给助手处理。
3. **建模和检查**：助手写特征和检查项，程序运行并测量。检查不过会自动修改重试，最多 3 次，仍不过就停下来把原因告诉你。
4. **交付**：全部检查通过且每个你给的尺寸都有检查时，程序自动导出 STEP 和截图，并显示检查结果表和文件路径。
5. **修改**：直接提出修改（比如“支撑角度改成 70 度”），助手只改你提到的条目，之前的检查会保留，用来确认没改的需求依然满足。

### 命令

| 命令 | 作用 |
|---|---|
| `/view` | 用 `sca edit` 在浏览器里打开当前会话的模型（退出本程序时自动关闭编辑器） |
| `/diff` | 对比最近两个版本：参数变化 + 两张截图的路径 |
| `/versions` | 列出所有已交付的版本和各自的变化 |
| `/help` | 显示命令说明 |
| `/quit` | 退出（也可以按 Ctrl+C 或 Ctrl+Z 回车） |

## 会话目录

每次运行在 `sessions/<日期-时间>/` 下留下全部记录（目录位置可在配置的 `sessions_dir` 里改）：

```text
sessions/20261109-153000/
  log.jsonl          每条用户消息、模型回复、工具调用、结果、耗时、token，以及启动时的软件和模型版本
  brief.json         当前需求单
  features.json      当前的特征列表（slug、角色、代码）
  checks.json        当前的检查项
  model.py           当前工作中的模型（marimo notebook，参数化源文件，可以用 sca edit 打开）
  versions/
    v1/  model.py  model.step  view.png  checks.json  brief.json  changes.md
    v2/  ...
```

## 评测

`benchmarks/` 里有 3 个开发任务（手机支架、法兰盘、带加强筋的 L 形安装支架）和 2 个留出任务（电路板小盒、阶梯轴；只用来测，不许为它们调提示词），每个任务有一句话的初始需求、“用户心里的完整需求”、修改请求和人工写的验收检查。评测时由一个模拟用户（也是大模型）扮演提需求的人：

```powershell
.venv\Scripts\python -m benchmarks.run --config config.toml                      # 开发任务各跑 1 遍
.venv\Scripts\python -m benchmarks.run --config config.toml --set dev --repeat 3  # 开发任务各跑 3 遍
.venv\Scripts\python -m benchmarks.run --config config.toml --set holdout         # 留出任务（--set all 两组都跑）
.venv\Scripts\python -m benchmarks.run --tasks phone_stand flange --config config.toml
```

结果写到 `benchmarks/results/<时间>/results.json` 和 `results.md`：`results.md` 开头是按任务汇总的表（成功次数 / 遍数、平均费用、平均耗时、平均模型调用、平均输入和其中命中缓存、平均输出和其中思考），后面是每一遍的明细。费用按 `config.toml` 里的 `[llm.pricing]` 算，没填价目表时费用显示 `-`。评测会调用真实的大模型，需要先设置好 API key，会产生费用。

两次评测结果的前后对比（Markdown 表和总费用之比）：

```powershell
.venv\Scripts\python -m benchmarks.compare 旧目录\results.json 新目录\results.json --out compare.md
```

第 1.1 版的完整评测结果、成功标准的对照和没做到的地方见 `docs/results-v1.1.md`。

## 网页演示

演示时用网页界面代替命令行。

- 左边：对话。需要提问时，问题按编号列出，并有"逐条回答"按钮；请确认时，显示需求单和"确认"按钮；交付时，显示版本卡片和下载链接。
- 顶部：五步流程（澄清 → 确认 → 建模 → 检查 → 交付），实时标出走到了哪一步；右上角是本次会话的费用和缓存命中率。
- 右边四块：
  - 01 模型：可以拖动旋转的 3D，z 轴朝上；可以切换线框、截图，标出外形尺寸和体积。
  - 02 检查：程序逐条实测，和期望值对照。
  - 03 需求单：每个参数的来源，分"用户"和"建议"。
  - 04 版本：各版本的缩略图，以及相邻两版的参数变化对比。

两种启动方式：

```powershell
start_web.bat                                                        # 实时模式：接真实大模型（双击也行）
.venv\Scripts\python -m cad_agent.web --config config.toml            # 同上，可加 --port 8765、--no-browser

start_replay.bat                                                     # 回放模式：只读回放 demo\phone_stand 这次真实会话
.venv\Scripts\python -m cad_agent.web --replay <会话目录>              # 回放任意会话目录（sessions\ 下的都行）
```

- 两种模式都会自动打开浏览器，地址是 `http://127.0.0.1:8765/`，端口被占用时会自动换下一个。服务只监听本机。
- 页面不依赖外网：three.js 已经放在 `cad_agent/web/static/vendor/three/`（r160，MIT 许可），字体用系统字体。
- 回放模式不需要 API key，也不花钱，适合预览界面；演示时网络出了问题，也可以拿它当后备。
- 旧会话的版本没有 `model.stl` 时，先运行 `.venv\Scripts\python scriptsackfill_stl.py <会话目录>` 补出来（只在本地用 SCA，不调用大模型）。

演示前检查几件事：

1. 环境变量里的 API key 已经设置好，`config.toml` 里的模型和价目表是对的。
2. 网络通：要能连上模型服务，页面本身不需要外网。
3. 先完整跑一遍手机支架：
   1. 点欢迎页的第一个例子；
   2. 回答问题，点"确认"，等交付 v1；
   3. 发"支撑角度改成 70 度"，等交付 v2；
   4. 在 04 版本里看参数对比。
4. 出任何错，页面都不会卡死，服务也不会退出；真出了问题，点右上角的"新会话"就能重新开始。

## 测试

单元测试用脚本化的假模型，不花钱，不需要 key：

```powershell
.venv\Scripts\python -m pytest -q                # 全部测试
.venv\Scripts\python -m pytest -q -m "not sca"   # 跳过需要真实运行 SCA 的较慢测试
```

## 常见问题

- **项目路径里有中文**：SCA 运行模型一律在英文临时目录里进行，产物再复制回会话目录，所以中文路径下 STEP 和截图都能正常生成。唯一的限制是 notebook 的**文件名**必须是英文（程序固定用 `model.py`）。如果某台机器上中文路径仍然出问题，把配置里的 `sessions_dir` 改成纯英文路径（例如 `D:/cad-sessions`）。
- **模型 API 断网或限流**：会先自动重试（间隔 1 秒、2 秒），仍然失败就告诉你，需求单和已写好的特征都不会丢，稍后重发上一句话就行。
- **运行报错**：给模型看的是翻译后的简短信息（哪个特征、什么问题、相关数值），完整过程可以在 `log.jsonl` 里查。

## 项目结构

```text
cad_agent/
  cli.py  config.py  brief.py  notebook.py  session.py  tools.py  tool_specs.py
  agent/    loop.py（主循环）  state.py（状态消息）  api_docs.py（查 SCA 文档）  prompts/（系统提示词、SCA 速查表）
  checks/   spec.py（检查项格式）  engine.py（测量）
  sandbox/  guard.py（静态检查）  runner.py（子进程入口）  execute.py（启动子进程、超时）
  llm/      client.py（OpenAI 兼容接口）  fake.py（测试用假模型）
benchmarks/ tasks/*.yaml  sim_user.py  run.py
scripts/    probe_sca.py（SCA 摸底脚本）
docs/       设计文档、实施计划、sca-api-notes.md（实测过的 SCA 用法）、deviations.md、progress.md
tests/
```

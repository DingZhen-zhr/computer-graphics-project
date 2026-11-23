# 迁到 Mac：给自己看的步骤 + 给 AI 工具的开场话

2026-11-23 从 Windows（Claude Code）迁到 Apple 芯片 Mac（Codex / Antigravity）。AI 工具要遵守的规则在仓库根目录 `AGENTS.md`（Antigravity 还会读 `GEMINI.md`，它只是指向 `AGENTS.md`）。

## 一、在 Windows 上带走的东西

代码都在 GitHub 上了。git 里**没有**的只有这些，已经打包成 `build/mac-transfer.zip`（约 27 MB）：

- `config.toml`、`config-e2.toml`：模型配置（里面没有 key）
- `benchmarks/results/`：历次评测的原始记录，**含账本 `ledger-v3.json`**。花费上限靠它算，一定要带上。

用 U 盘、网盘或微信把这个 zip 传到 Mac 上。

**不要带的：** `.venv`（Mac 上重新建）、API key（到 Mac 上重新填，见第三节）。

## 二、Mac 上搭环境（在"终端"里一行一行粘贴）

1. 装命令行工具（带 git）。弹窗就点"安装"：

   ```sh
   xcode-select --install
   ```

2. 装 uv：

   ```sh
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   装完关掉终端再开一个。

3. 装 Node 22（测试里要用）：到 https://nodejs.org 下载 22 版的 macOS 安装包，双击装上。装完 `node -v` 应该显示 `v22.` 开头。

4. 取代码，放在纯英文路径下：

   ```sh
   mkdir -p ~/Projects && cd ~/Projects
   git clone https://github.com/DingZhen-zhr/computer-graphics-project.git datum
   cd datum
   ```

5. 把 `mac-transfer.zip` 解压到这个文件夹里（假设 zip 在"下载"里）：

   ```sh
   unzip ~/Downloads/mac-transfer.zip -d ~/Projects/datum
   ```

   解压后 `~/Projects/datum/config.toml` 和 `~/Projects/datum/benchmarks/results/ledger-v3.json` 都应该在。

6. 建开发环境：

   ```sh
   uv venv --python 3.12
   uv pip install -e ".[dev]"
   ```

7. 自己先确认一下能跑（约半分钟，不花钱）：

   ```sh
   PYTHONUTF8=1 .venv/bin/python -m pytest -q -m "not sca"
   ```

   最后一行是"xxx passed"就行。有失败也没关系，交给 AI 工具去查（见第四节第 1 段）。

## 三、API key（只有花钱的那几步才需要）

- **不要把 key 发给 Codex、Antigravity 或任何对话框。**
- 评测命令（`benchmarks.run`）从环境变量读 key。要跑的时候，在**你自己**的终端里先设好，再让 AI 工具跑，或者你自己照它给的命令跑：

  ```sh
  export DEEPSEEK_API_KEY='你的key'
  ```

  （变量名以 `config.toml` 里 `api_key_env` 那一行为准。）关掉终端它就没了，不会留在文件里。
- 桌面端 Datum 里用的 key：打开 Datum → 设置页里填，会存进 Mac 钥匙串。
- 剩下的钱：实际已花约 ¥14.75，上限 ¥20，只剩约 ¥5。

## 四、给 AI 工具的开场话（一次贴一段，做完一段再贴下一段）

每次开新对话都先让它读规则。下面每一段直接复制粘贴。

### 1. 验证迁移

```text
这是一个从 Windows 迁到 Mac 的课程项目。先完整读一遍仓库根目录的 AGENTS.md，再读 docs/progress.md 的最后三节。然后照 AGENTS.md"剩下的事"第 1 条做：确认 .venv 已经建好，先跑快速全量，再跑完整全量（含真实 SCA，大约 10 分钟，在前台跑，命令超时设 20 分钟）。不要改任何源文件。有失败的话，把失败的测试名和报错原样列给我，说明你判断是 Mac 特有的问题还是代码问题、打算怎么改，等我同意再改。都通过的话，在 docs/progress.md 末尾加一节"迁到 Mac"，写测试数量和 macOS 版本，然后提交，提交信息：docs: 迁到 Mac，测试全部通过 [skip ci]
```

### 2. 计划 6 Task 6（花钱验证，约 ¥1.5–3）

```text
先读 AGENTS.md。现在做计划 6（docs/superpowers/plans/2026-11-23-datum-6-teacher-lessons.md）的 Task 6。照 Step 1 先停下来问我，把要跑的命令、最多花多少、预计花多少、现在是不是空闲时段都告诉我。我说"可以"之前不要运行任何会调用模型的命令。key 我会自己在终端里设好环境变量，不要让我把 key 发给你。
```

（它问你的时候：先在你自己的终端里 `export DEEPSEEK_API_KEY=...`，再回答"可以"。如果它的终端和你的终端不是同一个，让它把完整命令给你，你自己在设了 key 的终端里跑，跑完告诉它。）

### 3. 计划 6 Task 7（收尾）

```text
先读 AGENTS.md。现在做计划 6 的 Task 7：跑一次完整全量，在 docs/progress.md 追加计划 6 的小结，用计划给的提交信息提交。最后单独问我要不要推送，我同意了才推。
```

### 4. Mac 人工清单（这一项主要是你自己做）

```text
先读 AGENTS.md。我要照 docs/mac-checklist.md 在这台 Mac 上人工检查界面。请你一项一项带着我做：每次只告诉我下一项要运行什么命令、要点哪里、要看什么，等我说看到了什么，你再帮我把那一项改成 [x] 并写上我说的话。我没说看到的项不要替我勾。全部做完后，照计划 5 Task 6 Step 5 更新 README 里关于 Mac 的那一句，提交：docs: Mac 人工清单做完 [skip ci]
```

### 5. 计划 5 Task 4（演示预演，可选，约 ¥1）

```text
先读 AGENTS.md。现在做计划 5（docs/superpowers/plans/2026-11-20-datum-5-release.md）的 Task 4：演示预演。照 Step 1 先停下来问我要不要做，告诉我账本余额。我说"可以"之前不要调用模型。我不要的话就在 docs/progress.md 里记"跳过"。
```

### 6. 计划 5 Task 6（发布）

```text
先读 AGENTS.md。现在做计划 5 的 Task 6：发布。照计划一步一步来：推送、打 v3.0.0 标签、安装验证，每一步之前都单独停下来问我。安装验证就用这台 Mac：用 README 里 Mac 的那一行命令从 GitHub 实际装一次，跑 datum doctor，打开窗口。最后照 Step 6 写"3.0 小结"并提交。
```

## 五、AI 工具常见的跑偏，看到就叫停

- 测试失败后去改测试、放宽断言、加 `skip`：叫它撤回，按 AGENTS.md 改实现。
- 没问你就跑 `benchmarks.run` 或别的会调模型的命令：马上停掉（Ctrl+C）。
- 让你把 key 贴给它：不要贴。
- 一次改好几个任务、攒在一个提交里：叫它拆开。
- 开始"顺手优化"计划外的东西：叫它停，只做计划里的。
- 把 Windows 命令（`.venv\Scripts\...`）原样在 Mac 上跑：提醒它看 AGENTS.md 的"Mac 上的命令"表。

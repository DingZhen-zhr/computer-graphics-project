# 迁到 Mac：你只需要做这几件事

2026-11-23 从 Windows（Claude Code）迁到 Apple 芯片 Mac（Codex / Antigravity）。AI 要做的事和规矩都写在仓库根目录的 `AGENTS.md` 里，它自己会读、自己会照着清单一件件往下做。

## 一、在 Windows 上：把一个压缩包传到 Mac

`build/mac-transfer.zip`（约 27 MB）用 U 盘、网盘、微信或 AirDrop 传到 Mac 的"下载"文件夹。里面是 git 里没有的配置和评测记录（含花费账本），没有 key。

## 二、在 Mac 上：取代码

打开"终端"，粘贴这一行回车：

```sh
mkdir -p ~/Projects && cd ~/Projects && git clone https://github.com/DingZhen-zhr/computer-graphics-project.git datum
```

如果弹出"需要安装命令行开发者工具"，点"安装"，装完再粘贴一次。

## 三、交给 AI

在 Codex 或 Antigravity 里打开 `~/Projects/datum` 文件夹，发这一段：

```text
这个项目刚从 Windows 迁到这台 Mac。先完整读一遍仓库根目录的 AGENTS.md，然后照它"怎么接着做"一节，从"剩下的事"清单里第一个没做完的开始，一件接一件做下去。Windows 上带来的压缩包在 ~/Downloads/mac-transfer.zip。只在 AGENTS.md 写明要停下来问我的地方停。
```

之后每次开新对话，只要说：

```text
读 AGENTS.md，接着做。
```

## 四、它会停下来找你的地方

- 装 Node 22（它会让你去 nodejs.org 下载安装包，双击装上）
- 测试在 Mac 上有失败，要你同意怎么改
- 花钱跑真实模型之前（两次，共约 ¥2–4）
- 推送、打标签、更新主页之前
- Mac 界面检查：要你亲眼看、告诉它看到了什么

## 五、两条规矩

- **DeepSeek 的 key 不要发给 AI。** 要花钱的时候，在你自己的"终端"里先运行 `export DEEPSEEK_API_KEY='你的key'`，再跟它说"可以"。关掉终端 key 就没了，不会留在文件里。
- 剩下的钱：实际已花约 ¥14.75，上限 ¥20。

## 六、看到这些就叫停

- 测试失败后去改测试、放宽断言、加 `skip`：叫它撤回，改实现。
- 没问你就跑 `benchmarks.run` 或别的会调用模型的命令：马上按 Ctrl+C。
- 让你把 key 贴给它：不要贴。
- 开始"顺手优化"计划外的东西：叫它停。
- 在 Mac 上跑 `.venv\Scripts\...` 这种 Windows 命令：提醒它看 AGENTS.md 的"Mac 上的命令"表。

# 卡尺第二版 · 计划 2：模型接口与设置 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 让内核能逐字输出、能中途停止、能发图片；接上 Claude 官方接口；把模型服务做成预设；key 存进系统钥匙串；交付前做一次独立的看图审查；评测脚本能设花费上限。

**Architecture：** `LLM` 接口加两个可选的回调参数（片段到达、是否该停），两个实现（OpenAI 兼容、Anthropic）对内呈现同一个接口和同一套用量字段。设置从"项目里的 `config.toml`"扩展成"用户数据目录里的 `settings.toml` + 钥匙串里的 key"，两条路都产出同一个 `Config`。看图审查是主循环在交付前发起的一次独立模型调用，建模用的上下文一点不带。

**Tech Stack：** 在计划 1 的基础上新增两个依赖：`anthropic`（Claude 官方 SDK）、`keyring`（系统钥匙串）。用户已同意。

**Spec：** `docs/superpowers/specs/2026-11-10-caliper-v2-design.md`（第 3.6 节第 (3) 项、第 4 节、第 6.3 节、第 7.3 节）。

**前置：** 计划 1 全部完成。

**执行规则：** 见项目根目录 `CLAUDE.md`。

## Global Constraints

- 计划 1 的 Global Constraints 全部继续有效。**本计划不调用任何付费的模型接口**：所有测试用假的 HTTP 服务端或假客户端。
- key 的规矩不放松：不打印、不写日志、不写进任何文件和测试；测试里用的假 key 一律是 `test-key-0000` 这类明显的假值；钥匙串的测试用内存里的假后端，不碰真实的系统钥匙串。
- 代码里不写任何价格。各服务的地址和模型名只写在 `cad_agent/providers.toml` 里，写之前对照官方文档核实；拿不准的模型名留空。
- Claude 接口的字段名、流式事件、缓存标记、图片格式，以 Anthropic 官方文档为准，先写进 `docs/llm-api-notes.md` 第 8 节再用，不凭记忆写。没有用真实接口验证过的地方，在笔记和 README 里写明"未用真实接口验证"。
- `LLM.chat` 新增的参数都是可选的；不传时，发给接口的请求和现在逐字相同，旧测试不动。
- 本计划末尾"原文照抄"一节里 ```text、```json 框起来的内容逐字照抄。
- 偏离记录接着计划 1 的编号。每个任务收尾：全部测试通过 → 提交 → 在 `docs/progress.md` 追加一段（标题写"第二版 计划 2 Task N"）。

## Review Focus

1. 逐字输出到一半网络断了：已经显示的片段不能当成完整回复；这一次调用按失败处理并照常重试，重试成功后片段从头再来，界面不出现两份。→ Task 2 `test_stream_broken_midway_retries_from_scratch`
2. 用户在沙盒运行期间点了停止：子进程被结束，本轮以"已停止"结束，已经写下的特征和检查都在，下一轮能接着做。→ Task 2 `test_stop_during_sandbox_run`
3. 审查模型没有按要求调用 `submit_review`，或者返回的条目缺了一半：不能当成"全部符合"，也不能让程序崩；没提到的条目按"看不出"算。→ Task 6 `test_review_reply_without_tool_call`、`test_missing_items_are_unreviewable`
4. 环境变量和钥匙串里都有 key 且不一样：用环境变量的；界面显示"来自环境变量"，不显示也不覆盖钥匙串里的那个。→ Task 3 `test_env_wins_over_keyring`
5. 系统没有可用的钥匙串后端（比如精简版系统）：保存 key 时给出中文说明并告诉用户可以改用环境变量，不崩，也不退回到明文文件。→ Task 3 `test_no_keyring_backend`
6. 评测跑到一半花费到了上限：当前这个任务跑完后停，已经完成的结果照常写出，没跑的任务在结果里标成"因预算跳过"。→ Task 7 `test_budget_stops_between_tasks`

---

## 文件结构（新增和改动）

```
docs/llm-api-notes.md                   新增第 8、9 节（Task 1）
cad_agent/providers.toml                服务预设（Task 1）
cad_agent/llm/client.py                 on_delta、should_stop、流式（Task 2）
cad_agent/llm/fake.py                   ScriptedLLM 支持片段和停止（Task 2）
cad_agent/sandbox/execute.py            运行中可以被停止（Task 2）
cad_agent/agent/loop.py                 停止、片段回调（Task 2）
cad_agent/paths.py                      数据目录（Task 3）
cad_agent/keystore.py                   钥匙串（Task 3）
cad_agent/llm/providers.py              读预设（Task 3）
cad_agent/settings.py                   settings.toml ↔ Config（Task 3）
cad_agent/llm/anthropic_client.py       Claude 适配层（Task 4）
cad_agent/llm/factory.py                按接口类型造客户端（Task 4）
cad_agent/llm/vision.py                 图片消息、识图测试（Task 5）
cad_agent/review.py                     看图审查（Task 6）
cad_agent/agent/prompts/reviewer.md     审查者提示词（Task 6）
benchmarks/run.py                       --budget、--cases（Task 7）
```

---

### Task 1：查文档，写笔记和预设

**Files：** Modify `docs/llm-api-notes.md`、`pyproject.toml`；Create `cad_agent/providers.toml`、`tests/test_providers_file.py`

本任务查官方文档，不调用接口。

- [ ] **Step 1：** 在 `docs/llm-api-notes.md` 追加两节，标题照抄：`## 8. Claude 接口（查文档，未用真实接口验证）`、`## 9. 各服务的地址和模型名（查文档）`。
  - 第 8 节逐条写清并附上文档出处：系统提示词怎么传；工具定义的格式；模型发起工具调用、程序回工具结果各是什么内容块；一次回复里多个工具调用怎么排；图片内容块的格式；用量有哪几个字段、缓存命中和缓存写入分别叫什么、`input_tokens` 含不含缓存部分；缓存标记怎么加、最多几个；流式有哪些事件、文字片段和工具参数片段各在哪个事件里；思考内容在多轮里要不要原样放回；`max_tokens` 是不是必填；限流和服务端错误的状态码。
  - 第 9 节一张表：服务、接口类型、地址、建议的模型名、key 的环境变量名、能不能识图、出处。服务有：DeepSeek、智谱 GLM、Kimi、通义千问、OpenAI、Claude。
- [ ] **Step 2：** 写测试 `tests/test_providers_file.py`：`test_providers_file_shape`——`providers.toml` 能解析；有 7 个预设，id 依次是 `deepseek`、`glm`、`kimi`、`qwen`、`openai`、`claude`、`custom`；每个有 `name`、`kind`（`openai` 或 `anthropic`）、`base_url`、`models`（数组，可以为空）、`api_key_env`、`vision`（`yes`、`no`、`unknown` 之一）；`deepseek` 的 `vision` 是 `unknown`；`custom` 的 `base_url` 是空文字；文件里没有任何价格数字相关的键。
- [ ] **Step 3：** 写 `providers.toml`（内容来自第 9 节）；`pyproject.toml` 的 `package-data` 加 `"providers.toml"`，依赖加 `anthropic` 和 `keyring`（版本下限取当前最新的稳定版，装好后把实际版本写进笔记）。运行 `.venv\Scripts\python -m pip install -e ".[dev]"`。
- [ ] **Step 4：** 运行全部测试，提交：`chore: Claude 接口笔记与服务预设`。

---

### Task 2：逐字输出与停止

**Files：** Modify `cad_agent/llm/client.py`、`cad_agent/llm/fake.py`、`cad_agent/sandbox/execute.py`、`cad_agent/agent/loop.py`、`cad_agent/tools.py`；Test `tests/test_streaming.py`、`tests/test_stop.py`

**Interfaces：**
- Produces：
  ```python
  # llm/client.py
  class LLMStopped(Exception): ...                 # 用户要求停止；不是 LLMError，不重试
  class LLM(Protocol):
      def chat(self, messages: list[dict], tools: list[dict], *,
               on_delta: Callable[[str], None] | None = None,
               should_stop: Callable[[], bool] | None = None) -> LLMReply: ...
  # sandbox/execute.py
  def run_job(..., should_stop: Callable[[], bool] | None = None) -> RunResult: ...
  # 被停止时返回 RunResult(ok=False, error={"cell": None, "type": "Stopped", "message": "已按你的要求停止"})
  # agent/loop.py
  Kind = Literal["reply", "question", "confirm", "delivered", "failed", "stopped"]
  class Agent:
      on_delta: Callable[[str], None] | None = None      # 界面设置；有文字片段时调用
      def request_stop(self) -> None: ...                 # 线程安全；置标志
  ```
  - `OpenAICompatLLM.chat`：`on_delta` 和 `should_stop` 都是 `None` 时走现在的非流式请求，一个字节都不变。任意一个不为 `None` 时用流式请求（带上让服务端在最后返回用量的选项，写法先查 SDK 文档并记进笔记第 2 节）：每个文字片段调用 `on_delta`；工具调用的名字和参数片段自己拼起来；每收到一个片段检查 `should_stop()`，为真就关掉连接并抛 `LLMStopped`。返回的 `LLMReply` 和非流式时的内容相同。思考内容的片段不传给 `on_delta`。
  - 流式中途出错：按现有规则重试（1 秒、2 秒，共 3 次）；重试前调用 `on_delta("\x00")` 表示"前面的片段作废"。这个约定写进 `LLM` 的文档注释。
  - `ScriptedLLM`：有 `on_delta` 时，把这条回复的 `content` 按每 4 个字符一段依次送出；送每一段之前检查 `should_stop`。
  - `run_job` 给了 `should_stop` 时，每 0.2 秒看一次，为真就结束子进程树。`ToolBox` 加成员 `should_stop: Callable[[], bool] | None = None`，分阶段和旧流程里所有调用 `run_job` 的地方都带上它。
  - 主循环：每一轮开始时清掉停止标志；调用模型时传 `on_delta=self.on_delta`、`should_stop=...`；每个工具调用之前也检查。发现要停：本轮以 `stopped` 结束，文字是 `已停止。已经写下的内容都保留着，可以接着说。`；照常保存状态、折叠本轮。

- [ ] **Step 1：** 写测试 `tests/test_streaming.py`（用 `httpx2`/`httpx` 的假传输层造流式响应，写法照 `tests/test_llm.py`）：
  - `test_non_streaming_request_is_unchanged`：不传回调时，请求体里没有 `stream`。
  - `test_stream_text_deltas`：三个文字片段依次到达，`on_delta` 收到的拼起来等于 `reply.content`。
  - `test_stream_tool_calls_are_assembled`：两个工具调用的参数被分成多段，最后 `reply.tool_calls` 的名字、id、参数都对。
  - `test_stream_usage_is_read_from_the_last_chunk`：用量和费用与非流式相同。
  - `test_reasoning_deltas_are_not_forwarded`。
  - `test_stream_broken_midway_retries_from_scratch`（Review Focus 1）：第一次连接发了两个片段后断开，第二次完整；`on_delta` 收到的序列是 两个片段、`"\x00"`、完整的全部片段；只返回一次回复。
  - `test_stop_raises_llm_stopped`：第二个片段之后 `should_stop` 变真 → 抛 `LLMStopped`，没有重试。
  - `test_scripted_llm_emits_deltas`。
- [ ] **Step 2：** 写测试 `tests/test_stop.py`：
  - `test_stop_between_tool_calls`：第一条回复有三个工具调用，执行完第一个后置停止标志 → `turn.kind == "stopped"`，后两个没有执行，第一个的效果保留。
  - `test_stop_during_llm_call`：`ScriptedLLM` 送片段时被停 → `stopped`，这条回复没有进历史。
  - `test_stop_during_sandbox_run`（Review Focus 2，标记 `sca`）：真实 `run_job` 跑一个 `while True: pass` 的特征，0.5 秒后置标志 → 2 秒内返回，`error["type"] == "Stopped"`，临时目录被清掉。
  - `test_next_turn_after_stop_works`：停止之后再发一条消息，标志已清，快照里有之前写下的特征。
  - `test_stopped_turn_is_logged_and_compacted`。
- [ ] **Step 3：** 运行，确认失败；实现；运行全部测试，提交：`feat: 逐字输出和中途停止`。

---

### Task 3：数据目录、钥匙串、预设、设置文件

**Files：** Create `cad_agent/paths.py`、`cad_agent/keystore.py`、`cad_agent/llm/providers.py`、`cad_agent/settings.py`、`tests/test_paths.py`、`tests/test_keystore.py`、`tests/test_settings.py`；Modify `cad_agent/config.py`、`cad_agent/sandbox/execute.py`

**Interfaces：**
- Produces：
  ```python
  # paths.py
  def app_home() -> Path: ...          # 环境变量 CALIPER_HOME；否则 Windows 是 %LOCALAPPDATA%\Caliper，Mac 是 ~/Library/Application Support/Caliper，其他系统是 ~/.caliper
  def settings_path() -> Path: ...     # app_home() / "settings.toml"
  def sessions_dir() -> Path: ...      # app_home() / "sessions"
  def cases_dir() -> Path: ...         # app_home() / "cases"
  def logs_dir() -> Path: ...
  def is_ascii_path(p: Path) -> bool: ...
  def work_root() -> Path | None: ...  # 系统临时目录是纯英文路径时返回 None；否则 Windows 返回 C:\ProgramData\Caliper\work（不存在就建），其他系统返回 /tmp
  # keystore.py
  SERVICE = "caliper"
  class KeyStoreError(Exception): ...  # 中文信息
  def get_key(provider_id: str, env_name: str) -> str | None: ...       # 先环境变量，后钥匙串；都没有返回 None
  def key_source(provider_id: str, env_name: str) -> Literal["env", "keyring", None]: ...
  def key_hint(provider_id: str, env_name: str) -> str | None: ...      # "…" 加最后 4 位；key 不到 8 位时只返回 "…"
  def set_key(provider_id: str, key: str) -> None: ...                  # 只写钥匙串
  def delete_key(provider_id: str) -> None: ...                         # 钥匙串里没有也不报错
  # llm/providers.py
  @dataclass(frozen=True)
  class Provider:
      id: str; name: str; kind: Literal["openai", "anthropic"]; base_url: str
      models: tuple[str, ...]; api_key_env: str; vision: Literal["yes", "no", "unknown"]
  def load_providers() -> list[Provider]: ...
  def get_provider(provider_id: str) -> Provider: ...                   # 不存在抛 ConfigError
  # settings.py
  @dataclass
  class Settings:
      provider: str = "deepseek"
      model: str = ""                 # 空的时候用预设的第一个模型
      base_url: str = ""              # 空的时候用预设的地址
      temperature: float = 0.2
      vision: Literal["auto", "on", "off"] = "auto"     # auto：看预设，unknown 当作不能
      review_provider: str = ""       # 空的时候和 provider 相同
      review_model: str = ""
      pricing: Pricing | None = None
      theme: Literal["system", "light", "dark"] = "system"
      gates: Gates = field(default_factory=Gates)
      run_timeout_s: float = 60
  def load_settings(path: Path | None = None) -> Settings: ...          # 文件不存在返回默认值
  def save_settings(s: Settings, path: Path | None = None) -> None: ... # 先写临时文件再改名
  def to_config(s: Settings) -> Config: ...
  ```
  - `Config` 新增字段：`kind: Literal["openai", "anthropic"] = "openai"`、`provider: str = ""`、`vision: bool = False`、`review: PhaseOverride`（和 `clarify`、`modeling` 同类，另多一个可选的 `base_url`、`kind`、`api_key_env`，用来让审查走另一家服务）。`Phase` 加 `"review"`。配置文件里对应 `[llm] kind`、`[llm] vision`、`[llm.review]`。都不写时和现在相同。
  - `to_config`：`sessions_dir`、`cases_dir` 用 `paths` 里的；`api_key_env` 用预设的。
  - `settings.toml` 里没有任何 key。`save_settings` 自己写 TOML（只有文字、数字、布尔和一层小节，不引入新依赖）。
  - `run_job` 建临时目录时用 `tempfile.mkdtemp(prefix="cad-agent-", dir=work_root())`。

- [ ] **Step 1：** 写测试 `tests/test_paths.py`：`test_caliper_home_env_wins`、`test_default_home_per_platform`（用 monkeypatch 改 `sys.platform` 和环境变量）、`test_is_ascii_path`、`test_work_root_none_for_ascii_temp`、`test_work_root_fallback_for_non_ascii_temp`（把临时目录改成带中文的路径 → 返回的路径是纯英文的）。
- [ ] **Step 2：** 写测试 `tests/test_keystore.py`（共用夹具：把 `keyring` 的后端换成一个内存里的字典后端）：
  - `test_set_get_delete_round_trip`。
  - `test_env_wins_over_keyring`（Review Focus 4）：两边都有时 `get_key` 返回环境变量的，`key_source == "env"`；`set_key` 之后钥匙串里是新值，环境变量不变。
  - `test_key_hint_shows_only_last_four`：`"sk-abcdefgh1234"` → `"…1234"`；7 位的 key → `"…"`；返回值里不含 key 的其他部分。
  - `test_blank_key_is_rejected`（空白或只有空格 → `KeyStoreError`）。
  - `test_no_keyring_backend`（Review Focus 5）：后端抛"没有可用后端"的异常时，`set_key` 抛 `KeyStoreError`，信息里有"环境变量"和预设的变量名说明；`get_key` 返回 `None` 而不是抛异常。
  - `test_key_never_in_exception_text`：各种失败情况下，异常文字里都没有 key。
- [ ] **Step 3：** 写测试 `tests/test_settings.py`：`test_defaults_when_no_file`；`test_round_trip`（含价格、开关、中文路径下的文件）；`test_unknown_keys_are_reported`（中文 `ConfigError`，写明哪个键）；`test_to_config_uses_preset`（`provider="glm"`、其余默认 → `base_url`、`model`、`api_key_env`、`kind` 来自预设）；`test_to_config_overrides`；`test_vision_auto`（预设 `yes` → 真；`unknown`、`no` → 假；`on` 强制为真）；`test_review_can_use_another_provider`；`test_settings_file_has_no_key`（保存后的文件里搜不到 `key` 这个词以外的任何密钥字段——断言文件的键集合就是预期的那几个）；`test_config_file_still_works`（旧的 `config.toml` 读出来 `kind == "openai"`、`vision` 为假）。
- [ ] **Step 4：** 运行，确认失败；实现；运行全部测试，提交：`feat: 数据目录、钥匙串、服务预设和设置文件`。

---

### Task 4：Claude 适配层

**Files：** Create `cad_agent/llm/anthropic_client.py`、`tests/test_anthropic_client.py`；Modify `cad_agent/llm/factory.py`

**Interfaces：**
- Consumes：笔记第 8 节；`LLM`、`LLMReply`、`ToolCall`、`LLMError`、`LLMStopped`、`Pricing`、`call_cost`。
- Produces：
  ```python
  class AnthropicLLM:
      def __init__(self, *, base_url: str, api_key: str, model: str, temperature: float = 0.2,
                   extra_body: dict | None = None, pricing: Pricing | None = None, max_tokens: int = 8192) -> None: ...
      def chat(self, messages, tools, *, on_delta=None, should_stop=None) -> LLMReply: ...
  def to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]: ...   # 返回（系统提示词, 消息列表）
  def to_anthropic_tools(tools: list[dict]) -> list[dict]: ...
  # factory.py
  def make_llm(config: Config, phase: Phase, api_key: str) -> LLM: ...             # 按这个阶段的 kind 造 OpenAICompatLLM 或 AnthropicLLM
  ```
  转换规则（字段名以笔记第 8 节为准）：
  - 所有 `role == "system"` 的消息按顺序用空行连起来，作为系统提示词。
  - `assistant` 消息：有文字就是一个文字块；每个 `tool_calls` 是一个工具调用块，参数从 JSON 文字还原成对象（还原不了时放进 `{"__raw__": 原文}`）。
  - `tool` 消息变成 user 消息里的工具结果块；连续的几条 `tool` 消息合并进同一条 user 消息；紧跟其后的 `user` 消息也并进去（这个接口要求 user 和 assistant 交替）。
  - 其他连续的同角色消息合并成一条。
  - 图片（内部写法见 Task 5）转成这个接口的图片块。
  - 缓存标记加在两处：系统提示词的末尾、第一条 user 消息的末尾（就是本轮的快照）。
  - 用量换算成内部六项：`prompt_tokens` = 没命中的输入 + 缓存命中 + 缓存写入；`cached_tokens` = 缓存命中；`completion_tokens`、`total_tokens` 照算；`reasoning_tokens` 拿不到就是 0。
  - 重试、不重试的状态码和 `OpenAICompatLLM` 的规则一致；错误信息里不含 key。
  - 流式、停止的行为和 Task 2 的约定一致。

- [ ] **Step 1：** 写测试 `tests/test_anthropic_client.py`（假传输层）：
  - `test_system_messages_are_joined`、`test_tool_calls_become_blocks`、`test_tool_results_are_merged_into_one_user_message`、`test_user_after_tool_results_is_merged`、`test_consecutive_users_are_merged`（对应程序补的"【程序自动运行了 build】"和"【阶段已通过】"消息）、`test_bad_tool_arguments_keep_raw`。
  - `test_tools_are_converted`：名字、说明、参数原样带过去。
  - `test_reply_is_parsed`：文字和两个工具调用。
  - `test_usage_is_normalized`：给定一组原始用量，六项数字和上面的规则一致；有价目表时费用按"命中 / 没命中 / 输出"算，缓存写入按没命中算。
  - `test_cache_markers_are_on_system_and_first_user`。
  - `test_streaming_text_and_tool_args`、`test_stop_raises_llm_stopped`。
  - `test_retry_rules`（429、5xx 重试；401、400 不重试）、`test_error_text_has_no_key`。
  - `test_make_llm_picks_client_by_kind`、`test_make_llm_review_phase_can_use_another_kind`。
- [ ] **Step 2：** 运行，确认失败；实现；在笔记第 8 节末尾写上"本适配层只经过假服务端测试，未用真实接口验证"。
- [ ] **Step 3：** 运行全部测试，提交：`feat: Claude 官方接口的适配层`。

---

### Task 5：图片消息与识图测试

**Files：** Create `cad_agent/llm/vision.py`、`tests/test_vision.py`；Modify `cad_agent/llm/client.py`（只在需要转换时）

**Interfaces：**
- Produces：
  ```python
  def image_part(png_path: Path) -> dict: ...        # {"type": "image_url", "image_url": {"url": "data:image/png;base64,…"}}
  def text_part(text: str) -> dict: ...              # {"type": "text", "text": text}
  def tiny_test_image() -> bytes: ...                # 程序生成的 64×64 PNG：左半红、右半蓝
  VISION_QUESTION: str                               # 见"原文照抄"
  def test_vision(llm: LLM) -> tuple[bool, str]: ... # （能不能识图, 给用户看的一句话）
  ```
  - 内部约定：消息的 `content` 可以是文字，也可以是由 `text_part`、`image_part` 组成的数组。`OpenAICompatLLM` 原样发出；`AnthropicLLM` 转成它的图片块。
  - `test_vision`：发一条带 `tiny_test_image()` 和 `VISION_QUESTION` 的 user 消息，不带工具。回答里同时有"红"和"蓝"（或 red 和 blue，不分大小写）算能识图。接口报错（比如不接受图片）算不能，原因放进第二项，不抛异常。
  - 日志里不记图片的内容，只记"图片 <字节数>"。

- [ ] **Step 1：** 写测试：`test_image_part_is_data_url`；`test_tiny_test_image_is_valid_png`（用 Pillow 读回来是 64×64，左半、右半的颜色对）；`test_test_vision_true`、`test_test_vision_false_on_wrong_answer`、`test_test_vision_false_on_api_error`（都用假客户端）；`test_openai_client_sends_image_parts_as_is`；`test_anthropic_client_converts_image_parts`；`test_images_are_not_written_to_logs`（主循环日志里搜不到 base64 的前 50 个字符）。
- [ ] **Step 2：** 运行，确认失败；实现；运行全部测试，提交：`feat: 图片消息和识图测试`。

---

### Task 6：看图审查

**Files：** Create `cad_agent/review.py`、`cad_agent/agent/prompts/reviewer.md`、`tests/test_review.py`、`tests/test_review_loop.py`；Modify `cad_agent/sandbox/execute.py`、`cad_agent/sandbox/runner.py`、`cad_agent/agent/loop.py`、`cad_agent/agent/delivery.py`

**Interfaces：**
- Consumes：`image_part`、`text_part`（Task 5）；`docs/sca-api-notes.md` 第 22 节的四个视角。
- Produces：
  ```python
  # sandbox：run_job(..., render_views: Path | None = None)；RunResult.view_paths: dict[str, Path]
  VIEWS = ("iso", "front", "top", "right")
  MAX_REVIEW_ROUNDS = 2
  @dataclass(frozen=True)
  class ReviewItem:
      target: str                                    # 组成部分的名字，或位置关系的原文
      verdict: Literal["match", "mismatch", "unreviewable"]
      reason: str
  @dataclass
  class ReviewResult:
      items: list[ReviewItem]
      overall: str
      @property
      def objections(self) -> list[ReviewItem]: ...  # verdict == "mismatch" 的
      @property
      def passed(self) -> bool: ...                  # 没有 mismatch
      def to_dict(self) -> dict: ...
  def review_targets(brief: Brief) -> list[str]: ...           # 各组成部分的原文，后面接各条位置关系的原文
  def review_messages(brief: Brief, views: dict[str, Path]) -> list[dict]: ...
  def parse_review(reply: LLMReply, targets: list[str]) -> ReviewResult: ...
  def run_review(llm: LLM, brief: Brief, views: dict[str, Path]) -> tuple[ReviewResult, LLMReply]: ...
  def objection_note(result: ReviewResult) -> str: ...         # 退回给建模模型的 user 消息，见"原文照抄"
  ```
  - `render_views` 给了目录时，子进程在检查通过后渲染四张图 `iso.png`、`front.png`、`top.png`、`right.png`；某一张渲染失败只是少这一张，不算运行失败。
  - `review_messages`：一条 system（`reviewer.md` 全文）和一条 user（文字部分见"原文照抄"，后面依次接四张图，每张图前面有一行视角名）。建模过程里的任何消息都不带。
  - `run_review` 调用模型时只给一个工具 `submit_review`（说明见"原文照抄"）。
  - `parse_review`：模型没有调用 `submit_review`，或者参数不是合法的格式 → 每个 target 都是 `unreviewable`，`overall` 写 `审查没有给出有效的结论`。调用了但少了某些 target → 少的按 `unreviewable`。`verdict` 写了别的值 → 按 `unreviewable`。多出来的、不在 targets 里的条目丢掉。
  - `Agent.__init__` 加仅限关键字的参数 `review_llm: LLM | None = None`。
  - 主循环：build 的结果可以交付时，如果分阶段、`gates.visual_review` 为真、`review_llm` 不是 `None`、本次交付的审查轮数不到 `MAX_REVIEW_ROUNDS`：
    1. 跑一次带 `render_views` 的沙盒（图存到会话目录的 `review/round-<n>/`）；一张图都没渲染出来就跳过审查。
    2. `run_review`；用量和费用计入本轮；写日志 `{"kind": "review", "round", "passed", **result.to_dict()}`。
    3. 通过：照常交付。
    4. 没通过且这是第 1 轮：不交付；往上下文里加一条 user 消息 `objection_note(result)`；`toolbox.build_failures += 1`；继续本轮（到失败上限时照常以 `failed` 结束）。
    5. 没通过且这是第 2 轮：照常交付，交付文字和版本目录里带上异议。
  - 审查轮数在每次交付之后、以及每条新的用户消息开始时清零。
  - 交付：版本目录里写 `review.json`（审查结果；没审查时是 `{"skipped": "<原因>"}`，原因是 `模型不能识图`、`已关闭`、`没有渲染出图片`、`审查调用失败` 之一）。`delivery_text` 再加两个仅限关键字的可选参数 `review: ReviewResult | None = None`、`review_skipped: str | None = None`：两个都是 `None` 时不加任何内容（旧流程和关掉审查的开关时就是这样）；否则多一行，见"原文照抄"E。
  - `cli.build_agent`、`web` 的 `build_live_agent`：`config.gates.visual_review` 为真且审查阶段的设置 `vision` 为真时，造一个 `review_llm` 传进去；否则传 `None`。

- [ ] **Step 1：** 写测试 `tests/test_review.py`：
  - `test_reviewer_prompt_is_verbatim`、`test_submit_review_spec_is_verbatim`、`test_user_text_is_verbatim`（`<…>` 填好之后逐行相等）。
  - `test_review_targets`。
  - `test_review_messages_have_no_modeling_context`：只有两条消息；user 的内容里有四个图片块；文字里没有任何特征代码。
  - `test_parse_all_match`、`test_parse_mismatch`、`test_review_reply_without_tool_call`（Review Focus 3）、`test_missing_items_are_unreviewable`（Review Focus 3）、`test_unknown_verdict_and_extra_targets`。
  - `test_objection_note_format`。
  - `test_render_views_real`（标记 `sca`）：真实沙盒渲染一个方块，四张图都在、都是合法的 PNG、互不相同。
- [ ] **Step 2：** 写测试 `tests/test_review_loop.py`（分阶段的假流程 + 假审查模型）：
  - `test_review_pass_then_deliver`：`review.json` 里全部 `match`，日志里有 `review`，审查的 token 计入了本轮。
  - `test_review_mismatch_goes_back_once`：第 1 轮不符合 → 没交付，建模模型下一次收到的消息里有 `objection_note` 的文字；它改完再 build → 第 2 轮符合 → 交付。
  - `test_second_mismatch_still_delivers_with_objections`：交付文字里有"看图审查有异议"那一行和异议内容，`turn.kind == "delivered"`。
  - `test_no_review_without_vision`：`review_llm=None` → 不渲染四视图，`review.json` 是 `{"skipped": "模型不能识图"}`，交付文字里有"未做看图审查"那一行。
  - `test_review_off_by_gate`、`test_review_skipped_when_nothing_rendered`。
  - `test_review_rounds_reset_after_delivery`。
  - `test_review_llm_error_does_not_block_delivery`：审查模型调用失败 → 当作跳过（原因 `审查调用失败`），照常交付，日志里记下错误（不含 key）。
  - `test_legacy_flow_has_no_review`。
- [ ] **Step 3：** 运行，确认失败；实现；运行全部测试，提交：`feat: 交付前的独立看图审查`。

---

### Task 7：评测脚本的花费上限和案例开关

**Files：** Modify `benchmarks/run.py`、`README.md`；Test `tests/test_benchmarks_budget.py`

**Interfaces：**
- Produces：`python -m benchmarks.run` 新增 `--budget <元>` 和 `--cases on|off`（默认 `on`）。
  - `--budget`：配置里没有价目表时直接报错退出（中文，返回码 2）。每跑完一个任务，把这个任务的费用（智能体的加上模拟用户的）累加；累计达到上限后不再开始新任务，没跑的任务在结果里记成 `{"task", "skipped_for_budget": true}`，汇总表的"成功"列写 `因预算跳过`。结果文件照常写出；最后打印一行 `已花费 ¥<x>，上限 ¥<y>`。
  - `--cases off`：造智能体时 `gates` 的 `cases` 设为假。
  - `run_benchmarks(..., budget: float | None = None)`。

- [ ] **Step 1：** 写测试：`test_budget_requires_pricing`；`test_budget_stops_between_tasks`（Review Focus 6：三个任务、每个花 ¥0.6、上限 ¥1 → 跑了两个，第三个标成跳过，`results.json` 里三条都有）；`test_budget_counts_sim_user_cost`；`test_without_budget_nothing_changes`；`test_cases_flag_turns_gate_off`；`test_summary_shows_skipped_for_budget`。
- [ ] **Step 2：** 运行，确认失败；实现。
- [ ] **Step 3：** README"评测"一节加上这两个参数，并加一小节"¥15 以内的评测套餐"：
  ```powershell
  .venv\Scripts\python -m benchmarks.run --config config.toml --set v2 --repeat 1 --budget 15
  ```
  写明：这条命令会调用真实模型、会花钱；由用户自己决定什么时候运行；跑之前先填价目表；结果出来之前，不能说第二版的成功率是多少。
- [ ] **Step 4：** 运行全部测试，提交：`feat: 评测脚本加花费上限和案例开关`。

---

## 做完之后

- `docs/progress.md` 最后写一段"计划 2 小结"，其中单独列出"没有用真实接口验证的部分"：Claude 适配层、DeepSeek 以外各服务的预设、识图测试、看图审查在真模型上的效果。
- 不要运行任何会调用真实模型的命令。

---

## 原文照抄

### A. 审查者的系统提示词

写入 `cad_agent/agent/prompts/reviewer.md`（Task 6）。

```text
你是一名零件图纸的审查员。你只看图，不建模。
你会拿到一份需求清单和同一个零件的四张渲染图：等轴测图、正视图（从正前方看）、俯视图（从正上方看）、右视图（从右边看）。零件底面贴在桌面上，长的方向是左右方向。
请对清单里的每一项，只根据图上看得见的东西，判断零件是否符合：
- 符合：图上能清楚看到这一项，而且和描述一致。
- 不符合：图上能清楚看到它和描述不一致，或者按描述应该看得见的东西在图上没有。
- 看不出：这四个视角看不到它（比如在内部、被挡住、太小），或者你没有把握。
规则：
- 拿不准时选"看不出"，不要猜。只有确实看到了矛盾才选"不符合"。
- 不要评价尺寸的具体数值，尺寸由程序另外测量。你只判断形状、有没有、在哪一边、怎么连接。
- 每一项的理由写一句话，说出你在哪张图上看到了什么。
- 必须调用 submit_review 提交结论，清单里的每一项都要有，target 原样照抄清单里的文字。不要用别的方式回答。
```

### B. 审查时 user 消息的文字部分

```text
零件：<零件名>（<用途>）
请逐项审查下面的清单。
组成部分：
<每个组成部分一行：- <原文>>
位置关系：
<每条位置关系一行：- <原文>；没有时这一段写一行：- （没有）>
```

用途为空时第一行不带括号。每张图前面的一行文字，依次是：

```text
等轴测图：
正视图：
俯视图：
右视图：
```

某一张图没渲染出来时，对应的那一行改成 `<视角名>（这张图没有渲染出来）`，后面不接图片。

### C. submit_review 的工具说明

```json
{
  "name": "submit_review",
  "description": "提交审查结论。清单里的每一项都要有一条，target 原样照抄清单里的文字。",
  "parameters": {
    "type": "object",
    "properties": {
      "items": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "target": {"type": "string", "description": "清单里的原文"},
            "verdict": {"type": "string", "enum": ["match", "mismatch", "unreviewable"], "description": "match：符合；mismatch：不符合；unreviewable：看不出"},
            "reason": {"type": "string", "description": "一句话：在哪张图上看到了什么"}
          },
          "required": ["target", "verdict", "reason"]
        }
      },
      "overall": {"type": "string", "description": "一句话的总体印象"}
    },
    "required": ["items", "overall"]
  }
}
```

### D. 退回给建模模型的消息

审查没通过、退回建模模型时，往上下文里加的 user 消息：

```text
【看图审查没有通过（程序生成）】
一位只看渲染图、没看过你的代码的审查者认为下面这些地方和需求单不一致：
<每条异议一行：- <target>：<reason>>
请对照需求单检查这些地方。确实做错了就改对应的特征，然后 build；如果你确认模型是对的，就补一条能证明这一点的检查，然后 build。
```

### E. 交付文字里的一行

加在"参数扰动验证"那一行之后。审查通过时：

```text
看图审查：通过（<n> 项符合，<m> 项看不出）。
```

审查两轮后仍有异议时（每条异议另起一行，前面两个空格）：

```text
看图审查有异议，请你自己看一下模型：
  - <target>：<reason>
```

没有做审查时：

```text
未做看图审查（<原因>）。
```

### F. 识图测试的问题

```text
这张图片左半边和右半边各是什么颜色？只回答两个颜色的名字。
```

`test_vision` 返回的第二项：能识图时是 `这个模型能看图，看图审查已经可以用了。`；回答不对时是 `这个模型没有认出测试图片，看图审查不会启用。`；接口报错时是 `这个模型不接受图片（<错误的前 80 个字符>），看图审查不会启用。`

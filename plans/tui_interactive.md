# 计划：TUI 交互模式（类 Claude Code 体验）

## 目标

把 funeralai 从「一次性命令行工具」变成「持久化 TUI agent」。用户启动后进入交互循环，像和 agent 对话一样使用：粘贴 URL、拖文件、自然语言描述意图，agent 理解并执行分析。

本质定位：**这不是一个带 REPL 的工具，而是一个会分析 AI 产品的 agent。**

## 用户体验流程

```
$ funeralai

  ██  ██  ██        ████    ██
  ██████████████    ██    ██  ██
  ...
  吹牛逼可以，但你要有一个过得去的产品。

  未检测到 API 密钥。粘贴你的 API key 开始：
  > sk-xxxxx
  ✓ 检测到 OpenAI，已保存

  ─────────────────────────────────────

  葬AI v0.1.0 | openai (gpt-4o)

  > https://github.com/owner/repo
  检测到 GitHub 仓库，正在实查...
  ├─ API 元数据 ✓
  ├─ Clone + 代码统计 ✓
  ├─ 红旗检查 ✓
  提取结构化事实...
  判断中...

  ═══════════════════════════════════
    葬AI 分析报告 — owner/repo
  ═══════════════════════════════════
  ...（完整报告）...

  > 用 deepseek 再看看
  切换到 deepseek，重新分析 owner/repo...

  > /vote gemini,deepseek,qwen
  对 owner/repo 发起三模型投票...

  > ~/Desktop/某BP.pdf
  检测到本地文件，开始分析...

  > exit
```

## 技术方案

### 依赖选择

- **prompt_toolkit**：交互输入（历史记录、补全、Ctrl+C 处理、多行粘贴）
- 不引入 rich/textual/curses — 当前 ANSI 手写渲染已经够用，保持轻量

### 新增/修改文件

#### 1. `funeralai/config.py`（新增）— API Key 持久化

```python
CONFIG_DIR = ~/.config/funeralai/
CONFIG_FILE = config.json

# 结构：
{
  "default_provider": "openai",
  "keys": {
    "openai": "sk-xxx",
    "deepseek": "sk-xxx"
  }
}

# 读取优先级：环境变量 > config.json
def load_config() -> dict
def save_config(config: dict)
def get_api_key(provider: str) -> str | None  # 先查 env，再查 config
def detect_provider_from_key(key: str) -> str | None  # 从 key 前缀推断 provider
```

#### 2. `funeralai/setup.py`（新增）— 首次配置引导

两级引导策略：

```python
def run_setup() -> dict:
    """首次运行引导。"""
    # Step 1: 检查环境变量，有任何一个 API key 就跳过引导
    existing = scan_env_keys()
    if existing:
        return existing  # 直接用，不打扰用户

    # Step 2: 极简引导 — 只要一个 key
    print("未检测到 API 密钥。粘贴你的 API key 开始：")
    key = input("> ").strip()

    # Step 3: 自动检测 provider
    provider = detect_provider_from_key(key)
    if provider:
        save_and_confirm(provider, key)
        return {"provider": provider, "api_key": key}

    # Step 4: 检测失败才展示完整选单
    provider = show_provider_menu()
    save_and_confirm(provider, key)
    return {"provider": provider, "api_key": key}
```

#### 3. `funeralai/session.py`（新增）— TUI 交互主循环

```python
class Session:
    provider: str
    api_key: str
    model: str | None

    # Agent 状态
    last_input: str | None          # 上次分析的原始输入
    last_input_type: str | None     # "file" / "github" / "web" / "text"
    last_result: dict | None        # 上次分析结果（支持「用 deepseek 再看看」跳过重复实查）
    last_inspection: dict | None    # 上次 GitHub/Web 实查数据
    analyses: list[dict]            # 本次会话所有分析记录

    def run(self):
        """主循环：prompt_toolkit PromptSession"""
        session = PromptSession(
            history=FileHistory('~/.config/funeralai/history'),
        )

        while True:
            try:
                user_input = session.prompt("  > ")
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input.strip():
                continue

            intent = self.parse_intent(user_input)
            self.dispatch(intent)

    def parse_intent(self, raw: str) -> Intent:
        """规则意图识别 — 不过 LLM"""
        raw = raw.strip()

        # 1. 斜杠命令（优先级最高）
        if raw.startswith("/"):
            return self._parse_slash_command(raw)

        # 2. 退出
        if raw.lower() in ("exit", "quit", "q"):
            return Intent("exit")

        # 3. URL 提取（从整个输入中扫描，支持「分析一下 https://xxx.com」）
        urls = extract_urls(raw)
        if urls:
            url = urls[0]
            if is_github_url(url):
                return Intent("analyze_github", url=url)
            return Intent("analyze_web", url=url)

        # 4. 文件路径（清理引号/转义 → expanduser → 检查 exists）
        path = try_resolve_path(raw)
        if path:
            return Intent("analyze_file", path=path)

        # 5. Provider 切换（「用 deepseek」「switch to gemini」）
        provider = try_match_provider_switch(raw)
        if provider:
            return Intent("switch_provider", provider=provider)

        # 6. 投票（「投票 a,b,c」）
        vote_providers = try_match_vote(raw)
        if vote_providers:
            return Intent("vote", providers=vote_providers)

        # 7. 重新分析（「再来一次」「retry」）
        if is_retry(raw):
            return Intent("retry")

        # 8. 纯文本 — 够长才当材料分析（>100字符），短文本提示用户
        if len(raw) > 100:
            return Intent("analyze_text", text=raw)

        return Intent("unclear", raw=raw)

    def dispatch(self, intent: Intent):
        """分发执行，复用现有 analyzer/inspector/scraper"""
        if intent.type == "unclear":
            self._hint(intent.raw)
            return
        # ... 各 handler 复用 analyzer.analyze / analyze_vote 等

    def _hint(self, raw: str):
        """短文本无法识别意图时，给出友好提示"""
        print("  可以粘贴 URL、拖入文件、或直接贴文章内容开始分析")
        print("  输入 /help 查看更多用法")
```

#### 斜杠命令

```python
def _parse_slash_command(self, raw: str) -> Intent:
    parts = raw[1:].split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    commands = {
        "help": Intent("help"),
        "provider": Intent("switch_provider", provider=arg),
        "vote": Intent("vote", providers=arg.split(",")),
        "history": Intent("show_history"),
        "clear": Intent("clear_screen"),
        "config": Intent("show_config"),
        "model": Intent("switch_model", model=arg),
    }
    return commands.get(cmd, Intent("unknown_command", raw=raw))
```

#### 错误恢复（agent 式）

```python
def _handle_analysis_error(self, error: Exception):
    """不只报错，还建议下一步"""
    msg = str(error)
    if "API" in msg or "密钥" in msg or "key" in msg.lower():
        print(f"  错误: {msg}")
        print("  API key 可能过期了。输入 /config 重新设置")
    elif "rate" in msg.lower() or "429" in msg:
        print(f"  错误: {msg}")
        if self.last_input:
            print("  触发限流了。要换个 provider 试试吗？（如：用 deepseek）")
    else:
        print(f"  分析出错: {msg}")
```

#### 4. `funeralai/cli.py`（修改）— 入口分流

```python
def main():
    args = parser.parse_args()
    if args.command is None:
        # 无子命令 → TUI 交互模式
        from funeralai.session import start_session
        return start_session()
    # 有子命令 → 保持原有 CLI 行为不变
    ...
```

`start_session()` 封装 welcome + setup 检查 + Session 初始化 + run，保持 cli.py 精简。

#### 5. `funeralai/analyzer.py`（小改）— _resolve_provider 支持 config

```python
def _resolve_provider(provider, api_key):
    # 现有逻辑不变：先查显式参数 → 再查环境变量
    # 新增最后一级：env 和参数都没有时，从 config.json 读取
    ...
    try:
        from funeralai.config import load_config, get_api_key
        config = load_config()
        default_provider = config.get("default_provider")
        if default_provider:
            key = get_api_key(default_provider)
            if key:
                return default_provider, key
    except Exception:
        pass

    raise RuntimeError(...)
```

### 意图识别规则（parse_intent）

纯规则，不过 LLM：

| 输入示例 | 识别结果 |
|---------|---------|
| `https://github.com/owner/repo` | GitHub 分析 |
| `https://example.com` | Web 分析 |
| `/path/to/file.md` | 本地文件分析 |
| `articles/test.md` | 本地文件分析（相对路径） |
| `~/Desktop/bp.pdf` | 本地文件分析（展开 ~） |
| `用 deepseek 分析` | 切换 provider + 重新分析上次输入 |
| `投票 gemini,deepseek,qwen` | 投票模式 |
| `再来一次` / `retry` | 重复上次分析 |
| `/help` | 显示帮助 |
| `/provider gemini` | 切换 provider |
| `/vote g,d,q` | 投票模式 |
| `/history` | 显示会话分析历史 |
| `/config` | 显示/编辑配置 |
| `/clear` | 清屏 |
| `/model gpt-4o-mini` | 切换模型 |
| `exit` / `quit` / `q` | 退出 |
| `分析一下 https://xxx.com` | 提取 URL → Web 分析 |
| `（一大段文字）` | 当作材料直接分析（>100 字符） |
| `（短文字）` | 提示"可以粘贴 URL、拖入文件、或贴文章内容" |

### 拖拽文件支持

macOS Terminal 拖拽文件会输入转义路径如：
- `/Users/xxx/file.md`
- `'/Users/xxx/file with spaces.md'`（带引号）
- `/Users/xxx/file\ with\ spaces.md`（反斜杠转义）

`parse_intent` 里统一清理：strip 引号 + 去转义 + expanduser + resolve。

### 进度反馈

分析过程输出树状进度，让用户感觉 agent 在"想"：

```
  检测到 GitHub 仓库，正在实查...
  ├─ API 元数据 ✓
  ├─ Clone + 代码统计 ✓
  ├─ 红旗检查 ✓
  提取结构化事实...
  判断中...
```

复用现有 `_progress()` 函数但格式升级为树状。

### 不做的事

- 不引入 LLM 做意图识别 — 规则匹配够用，速度快，无额外消耗
- 不做 streaming LLM 输出 — 两步分析（提取+判断）需要完整 JSON 才能解析，streaming 会破坏 parse_json()
- 不做多窗口/面板布局 — 保持单流滚动，简单可靠
- 不做会话持久化到磁盘 — 退出即清空，命令历史通过 prompt_toolkit FileHistory 保留
- 不做「对话式追问」— 分析完就是完了，不需要"你还想知道什么"。用户想追问自己会说

### 新增依赖

```toml
# pyproject.toml
dependencies = ["openai>=1.0", "prompt_toolkit>=3.0"]
```

prompt_toolkit 是唯一新增依赖，纯 Python，无 C 扩展，安装轻量。

## 实现顺序

1. `config.py` — API key 持久化读写 + provider 自动检测
2. `setup.py` — 首次配置引导（环境变量检测 → 极简 key 粘贴 → fallback 完整选单）
3. `session.py` — TUI 主循环 + 意图识别 + 分发 + 错误恢复
4. `cli.py` 修改 — 入口分流（无子命令 → session）
5. `analyzer.py` 小改 — _resolve_provider 支持 config.json
6. `welcome.py` 小改 — 品牌 banner 适配 TUI 首屏
7. 测试 + 边界情况（拖拽文件、中文路径、Ctrl+C、API 失败恢复）

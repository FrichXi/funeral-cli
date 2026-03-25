# funeralai CLI 完整封装计划

## Context

funeralai 的分析引擎已完整就位（~2674 行 Python），支持三条分析流水线（本地文件 / GitHub 仓库 / Web URL），8 个 LLM provider，多模型投票，批量分析。但用户 `pip install funeralai` 之后无法使用——CLI 入口不存在。

目标：封装一个完整的 CLI 产品。用户安装后，不论是 `funeralai`（交互会话）还是 `funeralai analyze <目标>`（一次性命令），都能得到流畅的端到端体验：主动引导配置 → 自动识别输入 → 执行分析 → 输出报告。

参考 opencode 的交互体验设计（自动检测输入类型、主动引导配置、状态栏、命令面板、错误恢复提示），技术栈保持 Python + prompt_toolkit。

## 用户体验设计（借鉴 opencode）

### UX 原则

从 opencode 提取的 5 个核心体验模式：

| opencode 模式 | funeralai 适配 |
|---|---|
| **自动检测** — 粘贴内容自动识别类型并执行 | 粘贴 URL 自动区分 GitHub/Web，拖入文件自动识别路径，长文本直接当材料 |
| **主动引导** — 首次运行自动检测环境、引导配置 | 扫描环境变量 → 无则主动提示粘贴 API key → 自动识别 provider → 持久化 |
| **状态感知** — 始终展示当前上下文（provider、model、会话状态） | 状态栏显示 `葬AI v0.1.0 | deepseek (deepseek-chat)` |
| **错误恢复** — 出错时不只报错，还建议下一步操作 | API 过期 → 提示 `/config`；限流 → 建议换 provider；缺依赖 → 给安装命令 |
| **命令面板** — 斜杠命令快速访问所有功能 | `/help /provider /model /vote /history /config /clear` |

### 一次性 CLI 体验

```
$ funeralai analyze https://github.com/owner/repo
使用 deepseek (deepseek-chat)
GitHub 仓库实查...
├─ API 元数据 ✓
├─ Clone + 代码统计 ✓
├─ 红旗检查 ✓
提取中...

──── 使用体验调查 (回车跳过, q 结束) ────
  分析对象: repo
  [1/3] 你亲手用过这个产品吗？...
  > 用过，核心功能能跑通
  [2/3] 有没有让你眼前一亮的地方？...
  > q

判断中...
═══════════════════════════════════════
  葬AI 分析报告 — owner/repo
═══════════════════════════════════════
  ...（完整彩色报告）...
```

```
$ funeralai analyze articles/*.md --format json --quiet
[{"file": "001.md", "result": {...}}, ...]

$ funeralai analyze https://example.com --vote gemini,deepseek,qwen
多模型投票 — gemini, deepseek, qwen, 并发 3
  [1/3] ✓ gemini
  [2/3] ✓ deepseek
  [3/3] ✓ qwen
═══════════════════════════════════════
  葬AI 多模型投票报告 — example.com
═══════════════════════════════════════
  ...
```

### TUI 交互体验

```
$ funeralai

  ██  ██  ██        ████    ██
  ██████████████    ██    ██  ██
  ...
  吹牛逼可以，但你要有一个过得去的产品。

  未检测到 API 密钥。粘贴你的 API key 开始：
  > sk-xxxxx
  ✓ 检测到 OpenAI，已保存到 ~/.config/funeralai/config.json

  葬AI v0.1.0 | openai (gpt-4o)

  > https://github.com/owner/repo
  检测到 GitHub 仓库，正在实查...
  （3 核心问题 + 最多 2 补充追问）
  （4 路并行判断）
  ═══════════════════════════════════
    葬AI 分析报告 — owner/repo
  ═══════════════════════════════════
  ...

  > 用 deepseek 再看看
  ✓ 切换到 deepseek (deepseek-chat)
  重新分析上次输入...

  > /vote gemini,deepseek,qwen
  对上次输入发起 3 模型投票...

  > ~/Desktop/某BP.pdf
  检测到本地文件: 某BP.pdf
  ...

  > exit
  再见
```

## 文件清单（6 个文件，按实现顺序）

### Step 1: `funeralai/config.py` — 配置持久化

**路径**: `/Users/xixiangyu/Documents/Funeral CLI/funeralai/config.py`
**参考**: 旧项目同名文件（可直接复用，逻辑完全适配新 analyzer）
**约 102 行**

持久化 API key 和 provider 到 `~/.config/funeralai/config.json`。

```python
# 数据模型
{
  "default_provider": "openai",
  "keys": { "openai": "sk-xxx", "deepseek": "sk-xxx" }
}
```

关键接口：

| 函数 | 作用 | 调用方 |
|------|------|--------|
| `load_config() -> dict` | 读配置，损坏返回 `{}` | setup/session/cli |
| `save_config(config: dict)` | 写配置，自动建目录 | setup |
| `get_api_key(provider: str) -> str \| None` | 环境变量优先，其次 config | session/cli |
| `save_api_key(provider, key)` | 保存 key + 设为默认 provider | setup |
| `get_default_provider() -> tuple[str, str] \| None` | **analyzer.py:249 的 fallback 入口** | analyzer |
| `detect_provider_from_key(key) -> str \| None` | 前缀推断（sk-ant- → anthropic, sk- → openai） | setup |
| `scan_env_keys() -> tuple[str, str] \| None` | 扫描所有 8 个 PROVIDERS 的环境变量 | setup |

**关键约束**: `get_default_provider()` 的签名不可变——`analyzer.py` 第 249 行已经写死导入它。

**验证**: `python -c "from funeralai.config import load_config; print(load_config())"`

---

### Step 2: `funeralai/setup.py` — 首次运行引导

**路径**: `/Users/xixiangyu/Documents/Funeral CLI/funeralai/setup.py`
**参考**: 旧项目同名文件（可直接复用）
**约 134 行**

主动检测环境，引导用户配置 API key。借鉴 opencode 的「零配置启动」理念：有环境变量就静默跳过，没有才主动引导。

```
run_setup() -> (provider_name, api_key)
  │
  ├─ 1. scan_env_keys()         → 有任一环境变量? 静默返回，不打扰
  ├─ 2. get_default_provider()  → config.json 里有? 静默返回
  └─ 3. 交互引导（仅 TTY stdin）:
       ├─ "未检测到 API 密钥。粘贴你的 API key 开始："
       ├─ detect_provider_from_key(key)
       │     ├─ 成功 → save_api_key() → "✓ 检测到 {provider}，已保存"
       │     └─ 失败 → _show_provider_menu() → 编号/名称选择 → save
       └─ return (provider, key)
```

**非 TTY 场景**（管道/CI）: 抛 RuntimeError，提示 `请设置环境变量（如 OPENAI_API_KEY）`

**Provider 选单**: 8 个 provider 按常用度排序（OpenAI → Anthropic → Gemini → DeepSeek → 通义千问 → Kimi → MiniMax → 智谱），显示默认模型名

**验证**: `python -c "from funeralai.setup import run_setup; print(run_setup())"`

---

### Step 3: `funeralai/welcome.py` — 品牌界面

**路径**: `/Users/xixiangyu/Documents/Funeral CLI/funeralai/welcome.py`
**参考**: 旧项目同名文件（可直接复用）
**约 319 行**

两种显示模式 + 三种终端宽度自适应：

| 条件 | 显示 |
|------|------|
| 首次运行 / 版本升级 | 大号「葬AI」像素字 banner + 标语 + 版本 |
| 后续运行, 宽屏 ≥100列 | 双栏 Dashboard：左侧 logo + 版本，右侧快速开始命令表 |
| 后续运行, 中屏 60-99列 | 单栏 Dashboard：logo → 分隔线 → 命令表 |
| 后续运行, 窄屏 <60列 | 纯文本最小化 |
| 非 TTY stdout | 无输出 |

版本标记文件 `~/.config/funeralai/.welcome_shown` 控制 banner 只显示一次。

**依赖**: `from funeralai.output import _use_color, _display_width`（新项目 output.py 已有这两个函数）

**Dashboard 命令表内容**（TUI + CLI 双入口，都要展示）:
```
funeralai analyze <file>         分析本地文件 (.md/.txt/.pdf)
funeralai analyze <url>          分析 GitHub 仓库或网页
funeralai analyze *.md           批量分析多个文件
funeralai analyze f.md --vote g,d,q  多模型投票
funeralai analyze --help         查看全部选项
```

**验证**: `python -c "from funeralai.welcome import show_welcome; show_welcome('0.1.0')"`

---

### Step 4: `funeralai/session.py` — TUI 交互主循环 ★

**路径**: `/Users/xixiangyu/Documents/Funeral CLI/funeralai/session.py`
**参考**: 旧项目同名文件为模板，适配新 analyzer API
**约 750 行，项目最核心的新文件**

#### 架构概览

```
start_session() → int
  ├─ show_welcome()
  ├─ run_setup() → (provider, api_key)
  └─ Session(provider, api_key).run()
       └─ 主循环: prompt → parse_intent → dispatch → 输出
```

#### Session 状态模型

```python
class Session:
    provider: str                    # 当前 provider 名
    api_key: str                     # 当前 API key
    model: str | None                # 覆盖模型（None = provider 默认）
    last_input: str | None           # 原始输入（URL/路径/文本）
    last_input_type: str | None      # "file" / "github" / "web" / "text"
    last_text: str | None            # 发给 analyzer 的完整拼接文本（缓存）
    last_inspection: dict | None     # GitHub/Web 实查数据（缓存）
    analyses: list[dict]             # 本次会话所有分析结果
```

`last_text` 缓存是关键设计：「用 deepseek 再看看」时复用缓存文本，跳过重复的 GitHub clone 或网页抓取，只重跑 LLM 分析。

#### 主循环

```python
def run(self):
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
    except ImportError:
        self._run_basic()  # fallback 到 input()
        return

    session = PromptSession(
        history=FileHistory(str(Path.home() / ".config" / "funeralai" / "history"))
    )
    self._show_status_bar()  # "葬AI v0.1.0 | deepseek (deepseek-chat)"

    while True:
        try:
            user_input = session.prompt("\n  > ")
        except KeyboardInterrupt:
            continue   # Ctrl+C 清空当前输入
        except EOFError:
            break      # Ctrl+D 退出
        if not user_input.strip():
            continue
        intent = self.parse_intent(user_input)
        self._dispatch(intent)
        if intent.type == "exit":
            break
```

#### 意图识别（纯规则，不过 LLM）

**`parse_intent(raw: str) -> Intent`**，严格优先级顺序：

| # | 匹配规则 | Intent | 说明 |
|---|----------|--------|------|
| 1 | `/` 开头 + 已知命令词 | 斜杠命令 | `_is_slash_command()` 排除 `/Users/xxx` 路径 |
| 2 | `exit` / `quit` / `q` | exit | |
| 3 | `help` / `?` / `帮助` | help | |
| 4 | 正则 `https?://` 提取 URL | analyze_github 或 analyze_web | GitHub 正则单独匹配 `github.com/owner/repo` |
| 5 | 文件路径（绝对/相对/带引号/带转义） | analyze_file | `_clean_path()` strip 引号 + 去 `\ ` 转义 → `expanduser` → `exists` |
| 6 | `用/使用/切换到/use/switch to + provider名` | switch_provider | 正则匹配，验证 provider 存在 |
| 7 | `投票/vote + 逗号分隔 providers` | vote | 验证 ≥2 个有效 provider |
| 8 | `再来一次` / `重新分析` / `retry` / `again` / `redo` | retry | 精确匹配 |
| 9 | 文本 > 100 字符 | analyze_text | 直接当材料分析 |
| 10 | 其他短文本 | unclear | 上下文友好提示 |

**路径识别关键细节**:
- macOS 拖拽文件可能产生 `'/path/to/file with spaces.md'` 或 `/path/to/file\ with\ spaces.md`
- 支持从自然语言中提取路径：「分析这个 /Users/xxx/file.md」→ 找到 `/` 后取到行尾检查
- 相对路径：`articles/test.md` → 基于 cwd 解析

**斜杠命令清单**:

| 命令 | 作用 |
|------|------|
| `/help` `/h` | 显示帮助（输入示例 + 命令列表） |
| `/provider <name>` | 切换 provider |
| `/model <name>` | 切换模型 |
| `/vote <a,b,c>` | 对上次输入发起多模型投票 |
| `/history` | 查看本次会话分析历史 |
| `/config` | 查看当前配置（provider/model/已保存 key） |
| `/clear` | 清屏 + 重新显示状态栏 |
| `/exit` `/quit` `/q` | 退出 |

#### 分发表

```python
_DISPATCH = {
    "exit":            _handle_exit,
    "help":            _handle_help,
    "analyze_github":  _handle_analyze_github,
    "analyze_web":     _handle_analyze_web,
    "analyze_file":    _handle_analyze_file,
    "analyze_text":    _handle_analyze_text,
    "switch_provider": _handle_switch_provider,
    "switch_model":    _handle_switch_model,
    "vote":            _handle_vote,
    "retry":           _handle_retry,
    "show_history":    _handle_history,
    "clear_screen":    _handle_clear,
    "show_config":     _handle_config,
    "unknown_command": _handle_unknown_command,
    "unclear":         _handle_unclear,
}
```

#### 分析处理器

**GitHub URL 处理**:
```
_handle_analyze_github(intent)
  → "检测到 GitHub 仓库，正在实查..."
  → inspector.inspect_github(url) → (inspection, readme, report)
  → text = "## 项目 README\n\n{readme}\n\n{report}"
  → 缓存 last_input / last_text / last_inspection
  → _run_analysis(text, prompt_version=2, format_fn=format_terminal_github)
```

**Web URL 处理**: 同上，用 `scraper.inspect_web()` + `prompt_version=3`

**本地文件处理**:
```
_handle_analyze_file(intent)
  → "检测到本地文件: {filename}"
  → reader.read_file(path)
  → 缓存 last_input / last_text
  → _run_analysis(text, prompt_version=1, format_fn=format_terminal)
```

**直接文本处理**: 同本地文件，`prompt_version=1`

**核心分析调用**:
```python
def _run_analysis(self, text, prompt_version, format_fn):
    result = analyze(
        text=text, api_key=self.api_key, model=self.model,
        provider=self.provider, prompt_version=prompt_version,
        # interactive=True 是默认值，TUI 模式自动开启问答
    )
    # → analyze() 内部: extract → questioner.collect_answers(input()) → 4路并行 judge
    # → prompt_toolkit 在此期间不活跃，input() 正常工作
    self.analyses.append({**result, "_source": self.last_input[:80]})
    print(format_fn(result))
```

#### Provider 切换 + 自动重分析

「用 deepseek」→ 验证 → `config.get_api_key(name)` → 切换 `self.provider` / `self.api_key` → 如果有 `last_input` → `_replay_last()` 复用缓存文本重跑分析（不重做实查）

#### 投票处理

```python
def _handle_vote(self, intent):
    text = self.last_text  # 复用缓存
    prompt_version = {"file": 1, "text": 1, "github": 2, "web": 3}[self.last_input_type]
    result = analyze_vote(text=text, providers=intent.providers, model=self.model,
                          prompt_version=prompt_version)
    # 根据 last_input_type + last_inspection 选择对应的 format_vote_terminal_xxx
```

#### 错误恢复（opencode 风格：不只报错，建议下一步）

| 错误类型 | 提示 |
|----------|------|
| API key / 认证 | "API key 可能过期或无效。输入 /config 查看配置" |
| 429 限流 | "触发限流。换个 provider 试试？（如: 用 deepseek）" |
| 缺依赖 (ImportError) | 直接显示（analyzer 的错误消息已包含 pip install 指令） |
| 其他 | "分析出错: {msg}" |

#### Unclear 输入的上下文友好提示

| 关键词 | 回复 |
|--------|------|
| 你好 / hi / hello | "你好。粘贴 URL、拖入文件、或贴文章内容，我来分析。" |
| 能做什么 / 功能 | 解释三层框架：有人在用吗 → 长板有多长 → 吹的和做的差多远 |
| 怎么用 / how to | 列出 4 种输入示例 |
| 其他 | "粘贴 URL、拖入文件、或贴文章内容开始分析。输入 /help 查看更多用法" |

---

### Step 5: `funeralai/cli.py` — 一次性 CLI 入口

**路径**: `/Users/xixiangyu/Documents/Funeral CLI/funeralai/cli.py`
**参考**: 旧项目同名文件为模板，适配新 analyzer API（删除 `--ask-max`，简化 `_run_analysis`）
**约 500 行**

#### 入口路由

```python
def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command is None:
        # 无子命令 → TUI 交互会话
        from funeralai.session import start_session
        return start_session()
    if args.command == "analyze":
        return _cmd_analyze(args)
    return 0
```

#### 参数定义

```
funeralai                                    → TUI 交互会话
funeralai --version                          → 版本号

funeralai analyze <file_or_url>...           → 一次性分析
  位置参数:
    file_or_url          文件路径、目录、GitHub URL 或 Web URL（支持多个）

  分析选项:
    --text TEXT          直接传入文本内容（替代文件）
    --ask                开启交互问答（CLI 默认关闭，TUI 默认开启）
    --vote PROVIDERS     多模型投票（逗号分隔，如 gemini,deepseek,qwen）
    --no-clone           GitHub: 跳过 clone，仅用 API 元数据
    --no-browser         Web: 跳过 playwright 浏览器体验测试

  Provider/模型:
    --provider PROVIDER  指定 LLM provider（不指定则自动检测环境变量/config）
    --api-key KEY        API key（也可通过环境变量设置）
    --model MODEL        指定模型名（每个 provider 有默认值）
    --env-file PATH      从 .env 文件加载环境变量

  输出:
    --format {json,terminal}  输出格式（默认 terminal）
    -q, --quiet              静默模式（不输出进度到 stderr）

  并发:
    --workers N              最大并发数（默认 5，用于 batch/vote）
```

#### 输入自动分类

```python
def _classify_inputs(args):
    raw_inputs = args.file or []
    github_urls = [f for f in raw_inputs if _is_github_url(f)]
    web_urls = [f for f in raw_inputs if _is_web_url(f)]
    local_paths = [其余]
    files = _resolve_files(local_paths)  # 目录 → 展开为 *.md/*.txt/*.pdf
    return github_urls, web_urls, files
```

#### 分发逻辑

```
_cmd_analyze(args)
  ├─ 加载 .env (如果 --env-file)
  ├─ 分类输入 → github_urls, web_urls, files
  ├─ 验证组合合法性
  └─ 分发:
       ├─ 单 GitHub URL        → inspect_github → analyze/vote → format_terminal_github
       ├─ 单 Web URL           → inspect_web → analyze/vote → format_terminal_web
       ├─ 多 URL (同类型)      → 串行逐个处理
       ├─ --vote + 单输入      → analyze_vote → format_vote_terminal
       ├─ 多文件 (batch)       → analyze_batch → format_batch_terminal
       ├─ 单文件 / --text      → analyze → format_terminal
       └─ 混合 URL + 文件      → 分别处理
```

#### 与旧 cli.py 的 API 适配

旧代码 `_run_analysis()` 函数需要简化：

```python
# 旧版：分 ask/非 ask 两条路径，传 max_questions
def _run_analysis(args, **extra_kwargs):
    if args.ask:
        from funeralai.analyzer import analyze_interactive
        fn = analyze_interactive
        extra_kwargs.setdefault("max_questions", args.ask_max)
    else:
        from funeralai.analyzer import analyze
        fn = analyze
        extra_kwargs.pop("red_flags", None)
    return fn(text=..., ...)

# 新版：统一调用 analyze()，interactive 由 --ask 控制
def _run_analysis(args, **extra_kwargs):
    from funeralai.analyzer import analyze
    try:
        return analyze(
            text=extra_kwargs.pop("text"),
            api_key=args.api_key,
            model=args.model,
            provider=args.provider,
            interactive=args.ask,
            **extra_kwargs,
        )
    except (RuntimeError, ImportError) as e:
        print(f"错误: {e}", file=sys.stderr)
        return None
```

其他改动：删除 `--ask-max` 参数（新 questioner 固定 3 核心 + 最多 2 补充）。

**验证**: `python -m funeralai analyze articles/001*.md --quiet --format json`

---

### Step 6: `funeralai/__main__.py` — `python -m` 支持

**路径**: `/Users/xixiangyu/Documents/Funeral CLI/funeralai/__main__.py`
**5 行**

```python
"""Allow running as python -m funeralai."""
from funeralai.cli import main
raise SystemExit(main())
```

---

## 分析引擎的复用方式

CLI 层纯粹是「调用方」，不修改分析引擎的任何代码：

| CLI 操作 | 调用的引擎 API | 文件 |
|----------|---------------|------|
| 分析本地文件 | `reader.read_file()` → `analyzer.analyze()` | reader.py, analyzer.py |
| 分析 GitHub URL | `inspector.inspect_github()` → `analyzer.analyze(prompt_version=2)` | inspector.py, analyzer.py |
| 分析 Web URL | `scraper.inspect_web()` → `analyzer.analyze(prompt_version=3)` | scraper.py, analyzer.py |
| 多模型投票 | `analyzer.analyze_vote()` | analyzer.py |
| 批量分析 | `analyzer.analyze_batch()` | analyzer.py |
| 格式化输出 | `output.format_terminal*()` / `output.format_json()` | output.py |
| 交互问答 | `questioner.collect_answers()`（通过 `analyze(interactive=True)` 内部调用） | questioner.py |
| 配置读写 | `config.get_default_provider()`（通过 `analyzer._resolve_provider()` 内部调用） | config.py |

## 实现顺序 & 验证

```
Step 1: config.py       (无依赖)        → 测试 load/save/get_default_provider
Step 2: setup.py        (→ config)       → 测试 run_setup 三级引导
Step 3: welcome.py      (→ output)       → 测试 show_welcome 视觉效果
Step 4: session.py      (→ all above)    → 测试 TUI 完整流程
Step 5: cli.py          (→ session)      → 测试一次性 CLI 所有路径
Step 6: __main__.py     (→ cli)          → 测试 python -m funeralai
```

## 端到端验证场景

```bash
# ── TUI 完整流程 ──
funeralai
# 看到 banner → 粘贴 API key → 粘贴 GitHub URL → 实查 + 问答 + 报告
# 「用 deepseek 再看看」→ 切换 + 重分析
# /vote gemini,deepseek,qwen → 投票
# /history → 查看历史
# exit → 退出

# ── 一次性 CLI ──
funeralai analyze articles/001*.md                               # 单文件
funeralai analyze articles/001*.md --format json                 # JSON 输出
funeralai analyze articles/*.md                                  # 批量
funeralai analyze https://github.com/owner/repo                  # GitHub
funeralai analyze https://github.com/owner/repo --ask            # GitHub + 问答
funeralai analyze https://example.com                            # Web
funeralai analyze https://example.com --no-browser               # Web 无浏览器
funeralai analyze articles/001*.md --vote gemini,deepseek        # 投票
funeralai analyze --text "一大段文章内容..."                       # 直接文本
echo "材料内容" | funeralai analyze --text -                      # 管道（未来支持）

# ── 边界情况 ──
# 拖拽带空格/中文路径的文件
# Ctrl+C 中断分析（不退出 TUI）
# Ctrl+D 退出
# API key 过期 → 错误恢复提示
# 非 TTY 管道输入 → 静默跳过问答
# 无 API key 无环境变量 → 主动引导配置
```

## 不做的事

- 不用 LLM 做意图识别 — 纯规则，快且免费
- 不做 streaming 输出 — 4 路并行 judge 需要完整 JSON 解析
- 不做多窗口/面板布局 — 保持单流滚动
- 不做会话磁盘持久化 — 退出清空，命令历史用 FileHistory
- 不做主题系统 — ANSI 手写够用
- 不引入 rich/textual/curses — prompt_toolkit 已是依赖
- 不新增任何依赖 — openai + prompt_toolkit 已声明

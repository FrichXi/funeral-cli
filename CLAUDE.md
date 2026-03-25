# Funeral CLI

## 项目定位

开源交互式 AI 产品分析 agent。`pip install funeralai` 后，运行 `funeralai` 进入持久化 TUI 会话——粘贴 URL、拖入文件、自然语言描述意图，agent 理解并执行分析。也支持 `funeralai analyze <file_or_url>` 一次性命令行用法。

核心理念：**吹牛逼可以，但你要有一个过得去的产品。**

## 当前状态

**分析层已完整。** CLI/TUI 交互层需要从零重构。

### 已就位（分析层）

- 三步分析引擎（extract → ask → parallel judge）：8 个 LLM provider 支持
- 三条 prompt 流水线：local（本地文件）、github（GitHub URL + 代码实查）、web（Web URL + 产品体验实查）
- **并行 judge 架构**：judge 步骤拆分为 4 个并行 LLM 调用（广告检测、产品概述、证据抽取、核心判断），各自 prompt 精简聚焦，最后纯代码拼接
- GitHub 仓库实查（API 元数据 + clone + LOC + 测试检测 + 红旗）
- 网页实查（HTTP 抓取 + trafilatura + playwright 浏览器体验测试）
- 一手体验采集（3 个核心问题对齐三层分析框架 + 最多 2 个 LLM 生成补充追问）
- 语言自适应（根据输入材料自动检测中/英文，问题和 UI 文案跟随切换）
- 多模型投票（ThreadPoolExecutor 并行，问一次用户、答案共享给所有模型）
- 批量串行分析
- 终端彩色报告 + JSON 输出

### 需要重构（CLI/TUI 层）

旧项目的 CLI 层（`cli.py`、`session.py`、`config.py`、`setup.py`、`welcome.py`）**没有复制过来**，需要在本项目从零重写。`plans/tui_interactive.md` 是之前的 TUI 设计规划，可作为参考但不必照搬。

## 架构

```
$ funeralai                              ← 主入口：TUI 交互会话（待重构）
│
├─ 首次运行：setup 引导（检测环境变量 → 或粘贴 API key → 自动识别 provider → 写入 config）
│
├─ 进入 session 主循环（prompt_toolkit PromptSession）
│     │
│     ├─ parse_intent()  规则意图识别（不过 LLM）
│     │     ├─ GitHub URL       → inspector 实查 + analyze (github)
│     │     ├─ Web URL          → scraper 实查 + analyze (web)
│     │     ├─ 本地文件路径     → reader 读取 + analyze (local)
│     │     ├─ 长文本           → 当作材料 analyze (local)
│     │     ├─ 「用 deepseek」  → 切换 provider（+ 重新分析上次输入）
│     │     ├─ 「投票 a,b,c」   → 多模型投票
│     │     ├─ 「再来一次」     → 重复上次分析
│     │     ├─ /provider /vote /history /config /clear /model → 斜杠命令
│     │     └─ help / exit / quit
│     │
│     └─ dispatch() → 复用分析引擎
│
├─ 分析引擎（已就位）
│     ├─ 本地文件：extract_local → ask user → parallel judge
│     ├─ GitHub URL：inspector 实查 → extract_github → ask user → parallel judge
│     └─ Web URL：scraper 实查 → extract_web → ask user → parallel judge
│     └─ ask 步骤：语言自动检测 → 3 核心问题 + 最多 2 个补充追问 → 答案注入 judge
│     └─ parallel judge: 4 路并行（ad_detect / summary / evidence / verdict）→ assemble
│
└─ output.py 终端彩色报告

$ funeralai analyze <file_or_url...>     ← 次入口：一次性命令行（待重构）
```

### 分析引擎

三条 prompt 流水线（按输入类型区分），每条都是 extract → ask → parallel judge：

**提取步骤**（1 次 LLM 调用）：
- local：`extract_local.md` — 从材料提取结构化事实，不判断
- github：`extract_github.md` — 同 local + code_evidence + claim_vs_reality 交叉比对
- web：`extract_web.md` — 同 local + product_evidence + claim_vs_reality 交叉比对

**问用户步骤**（questioner.py）：
- 3 个核心问题（对齐三层框架）：使用情况 → 亮点/槽点 → 宣传vs现实
- 最多 2 个补充追问（LLM 根据 gaps/red_flags 生成）
- 语言自动适配：CJK 字符占比 >10% → 中文，否则英文

**并行判断步骤**（4 次并行 LLM 调用）：

```
extract 结果 + 用户回答
    ├──→ Call A: judge_ad_detect.md   → article_type + 广告信号
    ├──→ Call B: judge_summary.md     → product_reality（带态度，不中性）
    ├──→ Call C: judge_evidence.md    → 分类证据 + 原文引用
    └──→ Call D: judge_verdict.md     → verdict + 投资建议
    ↓
assemble（纯代码拼接）→ 最终报告 JSON
```

- Call A/B 接收裁剪后的提取结果（减少 token），Call C/D 接收完整上下文
- 流水线类型（local/github/web）作为上下文注入，prompt 文件共享
- 分析框架四层：第零层（实查，仅 github/web）→ 第一层（有人在用吗）→ 第二层（长板有多长）→ 第三层（吹的和做的差多远）

铁律：**判断完全基于提交的材料内容，不基于对公司的已有认知。**

输出 JSON 核心字段：`verdict`（2-4句猛打一个点）+ `evidence`（引用原文）+ `investment_recommendation`。

三档结论：值得进一步看 / 暂不建议投资 / 信息不足，不能判断

### 执行模型

- **单输入** — `analyze(interactive=True)` 默认：extract → ask → 4 路并行 judge → assemble。`interactive=False` 跳过问答
- **投票** — `analyze_vote(interactive=True)` 用第一个模型预提取 → 问一次用户 → N 个模型各自 4 路并行 judge（共享用户回答，首模型复用预提取结果）
- **批量** — `analyze_batch()` 串行 for 循环，每个文件内部 judge 仍是 4 路并行
- **兼容** — `analyze_interactive()` 已合并为 `analyze(interactive=True)` 的 wrapper

### 分析层文件清单

- `funeralai/__init__.py` — 包入口
- `funeralai/analyzer.py` — 分析引擎（extract → ask → parallel judge）+ 批量串行 + 投票并行。公开 API：`call_llm`、`load_prompt`、`parse_json`、`analyze`、`analyze_vote`、`analyze_batch`
- `funeralai/reader.py` — 文件读取（.md/.txt/.pdf）
- `funeralai/inspector.py` — GitHub 仓库实查
- `funeralai/scraper.py` — 网页实查
- `funeralai/questioner.py` — 一手体验采集（3 核心问题 + 最多 2 补充追问 + 语言自适应）
- `funeralai/output.py` — 终端彩色报告 + JSON 输出
- `funeralai/prompts/extract_local.md` — 本地文件提取 prompt
- `funeralai/prompts/extract_github.md` — GitHub 实查提取 prompt
- `funeralai/prompts/extract_web.md` — Web 体验提取 prompt
- `funeralai/prompts/judge_ad_detect.md` — 并行 judge: 广告检测（共享）
- `funeralai/prompts/judge_summary.md` — 并行 judge: 产品概述（带态度）
- `funeralai/prompts/judge_evidence.md` — 并行 judge: 证据抽取
- `funeralai/prompts/judge_verdict.md` — 并行 judge: 核心判断
- `funeralai/prompts/ask.md` — 补充追问生成 prompt（支持中英文输出）
- `funeralai/prompts/judge_local.md` / `judge_github.md` / `judge_web.md` — 旧版单次 judge prompt（已弃用，保留兼容）

### CLI/TUI 层文件（需要从零重构）

- `funeralai/cli.py` — 命令行入口。无子命令 → TUI session；有子命令 → 一次性 CLI
- `funeralai/config.py` — API key / provider 持久化配置（`~/.config/funeralai/config.json`）
- `funeralai/setup.py` — 首次运行交互引导
- `funeralai/session.py` — TUI 交互主循环（意图识别 + 分发 + 错误恢复）
- `funeralai/welcome.py` — 品牌欢迎界面

### 数据资产（已就位）

- `articles/` — 72 篇葬AI原创文章语料
- `data/eval/human_reviews.json` — 72 篇全量人工标注
- `data/graph/canonical.json` — 知识图谱（462 节点、1155 边）
- `data/state/articles_manifest.json` — 文章元数据索引

## 约定

- 分析框架不再调优。核心价值在于结构化分析视角，不在精确预测。
- `funeralai`（无参数）= TUI 交互会话。`funeralai analyze <file_or_url>` = 一次性 CLI。两个入口共享同一套分析引擎。
- TUI 意图识别是纯规则，不过 LLM。速度快、无额外消耗、可预测。
- API key 持久化到 `~/.config/funeralai/config.json`。读取优先级：环境变量 > config.json。
- 基础依赖 `openai>=1.0`、`prompt_toolkit>=3.0`。GitHub 模式额外需要 `gh` CLI + `git`。Web 模式需要 `pip install funeralai[web]`，浏览器测试可选 `pip install funeralai[browser]`。
- prompt_version 映射：1 = local，2 = github，3 = web。分析引擎内部用数字，CLI 层不需要暴露。
- 语言检测规则：输入文本 CJK 字符占比 >10% → 中文（zh），否则英文（en）。核心问题、UI 文案、补充追问 prompt 均跟随。不依赖外部库。

## 与旧项目的关系

本项目从「葬AI CLI」(`/Users/xixiangyu/Documents/葬AI CLI`) 分叉而来。分析层原封不动复制，CLI/TUI 层从零重写。旧项目的 `project.toml` 中有大量探索阶段的历史记录（双引擎 classic/zangai、framework_pack、promptfoo 评测、DSPy 多 judge 设计等），这些方向已经放弃，当前项目采用单引擎 + 两步分析的简洁架构。

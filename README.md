<p align="center">
  <img src="docs/assets/logo.svg" alt="葬AI / funaral-cli" width="920" />
</p>

```bash
git clone https://github.com/FrichXi/funaral-cli.git
cd funaral-cli
pip install -e .
```

> 仓库名：`funaral-cli`  
> Python 包名 / 命令名：`funeralai`

`funaral-cli` 是一个开源的 AI 产品分析 CLI / TUI。

它的目标不是帮用户写一段更漂亮的夸奖词，而是把一个产品、一个 GitHub 仓库、一个网页、或者一篇文章拆开来看：到底有没有真实产品，真实能力在哪里，吹的和做的差多远。

## 项目背景

现在很多 AI 产品的公开材料都有同一个问题：叙事很多，证据很少。

- 会讲故事，但没有稳定跑通的产品链路
- 会展示 demo，但没有真实使用信号
- 会包装成 Agent、平台、工作流革命，但本质上只是模型套壳
- 会写很长的 README、PRD、融资新闻，但很难回答“它到底行不行”

`funaral-cli` 就是为这个场景做的。

它把“产品判断”拆成一条明确流水线，用结构化方法去看材料、追问体验、抽证据、给结论。重点不是预测未来，而是尽可能真实地描述现在。

## 这个项目解决什么问题

- 当你拿到一个 GitHub 仓库时，快速判断它是不是只有 README、有没有真实代码、有没有测试和工程骨架
- 当你拿到一个产品网页时，判断它是不是能正常打开、有没有真实交互、是不是空壳页或广告页
- 当你拿到一篇文章、采访、融资稿时，把事实、观点、宣传、缺口拆开
- 当你自己调研 AI 产品时，用统一口径产出更稳定的分析结果，而不是每次凭感觉重来

## 核心能力

- `TUI 交互模式`：直接进入持续会话，粘贴 URL、拖入文件、自然语言描述都能处理
- `一次性 CLI`：适合脚本化、批量化、管道输入
- `GitHub 实查`：看仓库元信息、clone 代码、统计文件结构、识别测试和工程信号
- `网页实查`：抓取页面内容、跑浏览器体验、看交互元素和异常状态
- `结构化判断`：把提取、追问、判断拆开，避免一把梭式胡说八道
- `多模型投票`：可以让多个 provider 并行判断，再综合结果
- `Markdown / JSON 输出`：方便归档、分享、二次处理

## 分析方法

整个分析流程分三步：

1. `extract`
只提取结构化事实，不急着判断。

2. `ask`
在交互模式下追问一手体验。默认 3 个核心问题，最多补 2 个追问。

3. `parallel judge`
并行做 4 路判断：
- 广告检测
- 产品概述
- 证据抽取
- 核心结论

最终结果会被组装成统一报告，而不是让单次模型输出决定全部结论。

分析框架关注四层：

- 第零层：代码或产品到底有没有真的跑起来
- 第一层：有没有人在用
- 第二层：长板到底有多长
- 第三层：吹的和做的差多远

输出结论统一为三档：

- `整挺好`
- `吹牛逼呢`
- `整不明白`

## 安装要求

- Python `3.10+`
- 如果你要分析 GitHub 仓库：建议安装 `git`，可选安装 `gh`
- 如果你要做网页体验测试：首次使用时会自动安装 Playwright 浏览器

如果你只想从源码直接使用，最稳妥的方式就是 README 顶部那组命令。

## 快速开始

### 1. 进入交互模式

```bash
funeralai
```

适合连续分析多个对象，也适合边看边追问。

### 2. 一次性分析本地文件

```bash
funeralai analyze article.md
```

### 3. 分析 GitHub 仓库

```bash
funeralai analyze https://github.com/owner/repo
```

### 4. 分析产品网页

```bash
funeralai analyze https://example.com/product
```

### 5. 直接分析一段文本

```bash
funeralai analyze --text "这个产品声称自己是 Agent OS，本质上只是把 GPT 套了一层任务面板。"
```

### 6. 从标准输入读取

```bash
cat article.md | funeralai analyze --text -
```

### 7. 多模型投票

```bash
funeralai analyze article.md --vote deepseek,openai,gemini
```

### 8. 导出结构化结果

```bash
funeralai analyze article.md --format json
funeralai analyze article.md --format markdown
```

## TUI 体验

TUI 模式不是简单的壳，而是一套适合日常调研的持续会话界面。

- 自然语言输入：URL、文件路径、短句意图、长文本都能识别
- Slash 命令：`/provider`、`/model`、`/vote`、`/export`、`/theme`、`/lang`、`/help`
- 多主题：内置 `funeral`、`catppuccin`、`tokyonight`、`gruvbox`、`nord`
- 历史输入与补全
- 当前报告一键导出到 `exports/`

## GitHub 模式会做什么

分析 GitHub 仓库时，`funeralai` 不只看 README。

- 读取仓库元数据：stars、forks、contributors、languages
- clone 仓库到临时目录做结构检查
- 统计代码、文档、模板、配置的大致占比
- 识别测试文件、CI/CD、构建系统
- 生成工程红旗，例如单人仓库、几乎没代码、没有测试、工程骨架过弱

## Web 模式会做什么

分析网页时，`funeralai` 会做更接近“实查”的事情。

- HTTP 抓取与正文提取
- Playwright 浏览器加载测试
- 页面加载时间与 JS 错误检测
- 页面交互元素检查
- 内部链接健康检查
- 识别空内容页、反爬拦截、跨域跳转等异常

## Provider 与 API Key

当前支持：

| Provider | 环境变量 | 默认模型 |
|----------|---------|---------|
| Anthropic | `ANTHROPIC_API_KEY` | claude-sonnet-4-20250514 |
| OpenAI | `OPENAI_API_KEY` | gpt-4o |
| Gemini | `GEMINI_API_KEY` | gemini-3.1-pro-preview |
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-chat |
| Qwen | `DASHSCOPE_API_KEY` | qwen-plus |
| Kimi | `MOONSHOT_API_KEY` | moonshot-v1-32k |
| MiniMax | `MINIMAX_API_KEY` | MiniMax-Text-01 |
| 智谱 | `ZHIPU_API_KEY` | glm-4-plus |

API key 优先级：

1. 环境变量
2. `~/.config/funeralai/config.json`
3. Codex CLI auth

需要注意：

- 交互式配置会把 key 保存到 `~/.config/funeralai/config.json`
- 如果你不想在本机落盘，优先使用环境变量
- 公开仓库不包含任何本地 key、私有配置或用户语料

## 开源版本包含什么

这个公开仓库只包含可运行和可维护的部分：

- 应用代码
- prompts
- TUI 资源
- 自动化测试
- 开源文档

以下内容故意不放进公开仓库：

- 私有文章语料
- 研究中间产物
- eval 数据
- 内部计划文档
- 私有协作说明

详细范围见 [OPEN_SOURCE_SCOPE.md](OPEN_SOURCE_SCOPE.md)。

## 适合谁用

- 在看 AI 产品、AI Agent、AI 工具的人
- 经常需要快速扫 GitHub 项目的人
- 想把“凭感觉判断”变成“按结构判断”的研究者、投资人、产品人、开发者
- 想把自己的调研过程沉淀成可复用命令的人

## License

[MIT](LICENSE)

<p align="center">
  <img src="docs/assets/logo.svg" alt="葬AI / funeral-cli" width="920" />
</p>

```bash
curl -fsSL https://raw.githubusercontent.com/FrichXi/funeral-cli/main/install.sh | bash
```

> Python 包名 / 命令名：`funeralai`

---

把一个 AI 产品、一个 GitHub 仓库、一个网页、或者一篇融资稿拆开来看：**到底有没有真实产品，真实能力在哪里，吹的和做的差多远。**

现在很多 AI 产品的公开材料都有同一个问题：叙事很多，证据很少。会讲故事但没有跑通的产品链路，会展示 demo 但没有真实使用信号，会包装成 Agent / 平台 / 工作流革命，但本质上只是模型套壳。

`funeralai` 把「产品判断」拆成一条明确流水线：提取事实 → 追问体验 → 并行判断 → 组装结论。重点不是预测未来，而是尽可能真实地描述现在。

**吹牛逼可以，但你要有一个过得去的产品。**

## 怎么用

### 交互模式

```bash
funeralai
```

进入持续会话。粘贴 URL、拖入文件、自然语言输入都行。

### 一次性分析

```bash
funeralai analyze article.md                          # 本地文件
funeralai analyze https://github.com/owner/repo       # GitHub 仓库
funeralai analyze https://example.com/product          # 产品网页
funeralai analyze --text "一段文本"                     # 直接分析文本
cat article.md | funeralai analyze --text -            # 标准输入
funeralai analyze article.md --vote deepseek,openai    # 多模型投票
funeralai analyze article.md --format json             # 导出 JSON
```

## 分析方法

三步走，不是一把梭让模型胡说八道：

1. **extract** — 只提取结构化事实，不急着下判断
2. **ask** — 追问一手体验（3 个核心问题，最多补 2 个）
3. **parallel judge** — 4 路并行判断：广告检测 · 产品概述 · 证据抽取 · 核心结论

最终结果由多路判断组装，而不是让单次模型输出决定全部结论。

分析框架关注四层：

| 层级 | 看什么 |
|------|--------|
| 第零层 | 代码或产品到底有没有真的跑起来 |
| 第一层 | 有没有人在用 |
| 第二层 | 长板到底有多长 |
| 第三层 | 吹的和做的差多远 |

结论三档：**整挺好** · **吹牛逼呢** · **整不明白**

判断完全基于提交的材料内容，不基于对公司的已有认知。

## GitHub 模式

不只看 README。clone 代码、统计结构、识别测试和 CI、看 stars / forks / contributors，生成工程红旗——单人仓库、几乎没代码、没有测试、工程骨架过弱，这些都会被抓出来。

## Web 模式

不只抓文本。Playwright 浏览器实际加载页面、检测 JS 错误、检查交互元素、跑内部链接健康检查，识别空壳页和反爬拦截。比你手动打开网页看一眼靠谱。

## TUI

TUI 不是简单的壳，是一套适合日常调研的持续会话界面：

- 自然语言输入：URL、文件路径、短句、长文本都能识别
- Slash 命令：`/provider` `/model` `/vote` `/export` `/theme` `/lang` `/help`
- 多主题：`funeral` `catppuccin` `tokyonight` `gruvbox` `nord`
- 历史输入与补全
- 报告一键导出到 `exports/`

## Provider

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

API key 优先级：环境变量 > `~/.config/funeralai/config.json` > Codex CLI auth

## 安装

Python 3.10+

### 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/FrichXi/funeral-cli/main/install.sh | bash
```

脚本自动检测环境，优先用 pipx，没有就帮你装。

### 手动安装

```bash
pipx install funeralai        # 推荐，全局可用
# 或
uv tool install funeralai     # 更快的替代
# 或
pip install funeralai          # 需要在虚拟环境中
```

### 从源码

```bash
git clone https://github.com/FrichXi/funeral-cli.git
cd funeral-cli
pip install -e .
```

**额外依赖：**
- 分析 GitHub 仓库：建议装 `git`，可选装 `gh`
- 网页体验测试：首次使用时自动安装 Playwright 浏览器

## 开源范围

公开仓库包含：应用代码、prompts、TUI 资源、332 个自动化测试、开源文档。

不包含：私有文章语料、研究中间产物、eval 数据、内部计划文档。详见 [OPEN_SOURCE_SCOPE.md](OPEN_SOURCE_SCOPE.md)。

## 相关项目

- [funeralai](https://github.com/FrichXi/funeralai) — 分析框架本体，Claude Code / Codex skill
- [funeralai-web4](https://github.com/FrichXi/funeralai-web4) — 知识图谱可视化站点 → [funeralai.cc](https://funeralai.cc)

## License

[MIT](LICENSE)

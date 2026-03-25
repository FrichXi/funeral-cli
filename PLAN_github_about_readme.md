# 工作计划：三个项目 GitHub About + README 维护

## 第一步：设置 GitHub About（gh repo edit）

### 1. funeralai-web4
- **Description**: `葬AI Knowledge Graph — 68 篇 AI 行业评论 → 实体关系抽取 → 交互式知识图谱`
- **Homepage**: `https://funeralai.cc`
- **Topics**: `knowledge-graph, ai-analysis, nextjs, gemini, cytoscape, data-visualization`

### 2. funeralai
- **Description**: `葬AI — AI 产品结构化分析框架，Claude Code / Codex skill + Python 参考实现`
- **Homepage**: （不设）
- **Topics**: `ai-analysis, product-analysis, claude-code, codex, llm, agent`

### 3. funaral-cli
- **Description**: `葬AI CLI — 开源交互式 AI 产品分析 agent | pipx install funeralai`
- **Homepage**: （不设）
- **Topics**: `cli, tui, ai-analysis, product-analysis, textual, python`

---

## 第二步：维护 README

### funeralai-web4（当前无 README 内容或较简单）
重写 README，内容包括：
- 项目一句话定位
- 在线地址 funeralai.cc
- 截图/预览（如果有）
- 数据流水线架构（简洁版）
- 本地运行方式
- Tech stack 简述
- License

### funeralai（主仓库）
当前 README 已较完善。微调：
- 确保开头有清晰的一句话定位
- 检查安装命令是否最新
- 确保风格统一、不啰嗦

### funaral-cli（当前工作目录）
当前 README 已很详尽。优化方向：
- 保持现有结构，但检查是否有冗余段落
- 确保和 funeralai 主仓库的关系描述清晰
- 简化过长的段落

---

## 执行顺序

1. 并行设置三个项目的 GitHub About（gh repo edit）
2. 并行更新三个项目的 README（funeralai-web4 需要 clone 或直接 gh api 更新）
3. 验证结果

# 并行 Judge 方案

## 现状

```
extract (1次LLM) → ask (用户问答) → judge (1次LLM，生成完整JSON)
```

judge 单次调用承担所有分析：广告检测、产品描述、证据抽取、核心判断、投资建议。上下文长、输出杂、延迟高。

## 目标

1. 把 judge 拆成 4 个并行 LLM 调用，每个只负责报告的一个区块
2. 每个调用的 prompt 短而精准，上下文只包含它需要的信息
3. 最终拼接是纯代码，不再过 LLM
4. `product_reality` 不再是中性描述，要把分析结论揉进去

## 架构

```
extract (1次LLM)
    ↓
ask (用户问答)
    ↓ 共享输入: extract_result + user_answers
    │
    ├──→ Call A: 广告检测 (ad_detect)
    │      输入: extract_result (facts, opinions, attitude_signals)
    │      输出: { article_type, advertorial_confidence, advertorial_signals[] }
    │      prompt 要点: 只判断是不是广告，列信号，不做产品分析
    │
    ├──→ Call B: 产品概述 (product_summary)
    │      输入: extract_result + user_answers
    │      输出: { product_reality: "2-3句话，说清楚是什么+到底行不行" }
    │      prompt 要点: 抛开话术用大白话说清楚产品本质，同时把核心判断揉进去
    │                   不是中性描述，要带态度。示例——
    │                   "一个AI生成互动H5的UGC社区，创始人定位'可以玩的抖音'
    │                    ——但实际体验更像AI版4399，完成度远未达到定义品类的水平。"
    │
    ├──→ Call C: 证据抽取 (evidence_extract)
    │      输入: extract_result + user_answers
    │      输出: { evidence: [{ claim, quote, type }] }
    │      type 枚举: 事实(fact) / 推断(inference) / 风险(risk) / 推广(promotional) / 产品实测(product_testing)
    │      prompt 要点: 每条证据必须引原文，分类准确，不编造
    │
    └──→ Call D: 核心判断 (verdict)
           输入: extract_result + user_answers
           输出: { verdict: "2-4句猛打一个点", investment_recommendation: "三档之一" }
           prompt 要点: 抓最关键的一个点猛打，不面面俱到，不正反各半
                        判断标准沿用现有框架（第零层→第一层→第二层→第三层）

    ↓ 全部完成后
assemble (纯代码)
    ↓
{
  article_type,           ← from Call A
  advertorial_confidence, ← from Call A
  advertorial_signals,    ← from Call A
  product_reality,        ← from Call B
  evidence,               ← from Call C
  verdict,                ← from Call D
  investment_recommendation ← from Call D
}
    ↓
output.py 渲染终端报告
```

## 每个 Call 的上下文策略

| Call | 接收什么 | 不接收什么 | 预估 token |
|------|---------|-----------|-----------|
| A 广告检测 | facts, opinions, attitude_signals, key_quotes | user_answers, product_evidence, claim_vs_reality | ~800 input |
| B 产品概述 | facts, gaps, claim_vs_reality, user_answers | opinions, attitude_signals | ~1000 input |
| C 证据抽取 | 全部 extract_result + user_answers | 无（需要完整信息才能找证据） | ~1500 input |
| D 核心判断 | 全部 extract_result + user_answers | 无（需要完整信息才能判断） | ~1500 input |

Call A 和 B 可以做输入裁剪，减少 token 消耗。Call C 和 D 需要完整上下文但 prompt 本身很短。

## 实现要点

### 1. prompt 文件拆分

现有:
- `prompts/judge_web.md` (一个大 prompt)

改为:
- `prompts/judge_ad_detect.md` — 广告检测
- `prompts/judge_product_summary.md` — 产品概述（带态度）
- `prompts/judge_evidence.md` — 证据抽取
- `prompts/judge_verdict.md` — 核心判断

三条流水线 (local/github/web) 共享 ad_detect，其余三个 prompt 各有 local/github/web 变体（主要差异在第零层：local 无实查、github 有代码实查、web 有产品体验实查）。

### 2. analyzer.py 改动

```python
def _judge_parallel(extract_result, user_answers, provider, api_key, model, prompt_version):
    """并行执行 4 个 judge 调用，拼接结果。"""

    # 准备各 call 的输入（按上面的裁剪策略）
    ad_input = _prepare_ad_input(extract_result)
    summary_input = _prepare_summary_input(extract_result, user_answers)
    evidence_input = _prepare_full_input(extract_result, user_answers)
    verdict_input = _prepare_full_input(extract_result, user_answers)

    # 加载各 prompt
    ad_prompt = load_prompt(f"judge_ad_detect.md")
    summary_prompt = load_prompt(f"judge_product_summary_{version}.md")
    evidence_prompt = load_prompt(f"judge_evidence_{version}.md")
    verdict_prompt = load_prompt(f"judge_verdict_{version}.md")

    # 并行调用
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            "ad": pool.submit(call_llm, provider, ad_prompt, ad_input, ...),
            "summary": pool.submit(call_llm, provider, summary_prompt, summary_input, ...),
            "evidence": pool.submit(call_llm, provider, evidence_prompt, evidence_input, ...),
            "verdict": pool.submit(call_llm, provider, verdict_prompt, verdict_input, ...),
        }

    # 拼接
    return _assemble(futures)
```

### 3. 一致性风险

并行调用的一致性风险：Call D 的 verdict 可能和 Call C 的 evidence 不完全对齐（比如 verdict 说"长板不成立"但 evidence 里没有对应条目）。

缓解方案：
- **不做额外对齐调用**（会抵消并行收益）
- **在 prompt 中明确要求自包含**——每个 call 独立做完整分析，只是输出格式不同
- **接受轻微不一致**——实际上人类分析师写报告不同部分也会有微妙差异，这不是致命问题
- **如果严重不一致**（比如 verdict 说值得看但 evidence 全是负面的），在 assemble 阶段做简单规则校验，不一致时 fallback 到串行 judge

### 4. 性能预期

- 当前串行 judge: 1 次 LLM 调用，~3000 input tokens, ~1500 output tokens
- 并行 judge: 4 次调用并行，总 input ~4800 tokens（有重叠），总 output ~1200 tokens（各 call 输出更短更聚焦）
- 延迟 ≈ 最慢的那个 call 的延迟，通常比单次大调用更快（因为每个 call 的 output 更短）
- token 总消耗略增（~30%），但用户体感延迟显著降低

### 5. 向后兼容

- `analyze()` 函数的公开 API 不变，返回的 result dict 结构不变
- 只是内部 judge 步骤从单次调用变成并行调用 + 拼接
- output.py 不需要改（它消费的 JSON 结构不变）
- 投票模式 `analyze_vote()` 天然受益：每个模型的 judge 内部又是 4 路并行

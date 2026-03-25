"""Async bridge between TUI (asyncio) and the synchronous analysis engine.

All blocking calls (LLM, network, file I/O) are wrapped in asyncio.to_thread()
so they never block the Textual event loop.
"""

from __future__ import annotations

import asyncio

from funeralai.tui.state import (
    AppState,
    STATUS_CHATTING,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_EXTRACTING,
    STATUS_INSPECTING,
    STATUS_JUDGING,
)


# ---------------------------------------------------------------------------
# GitHub URL dispatch
# ---------------------------------------------------------------------------

async def dispatch_github(url: str, state: AppState) -> dict:
    """Inspect GitHub repo + analyze. Updates state.status progressively."""
    from funeralai.inspector import inspect_github
    from funeralai.analyzer import analyze

    state.reset_analysis()

    try:
        # Step 1: inspect
        state.status = STATUS_INSPECTING
        state.status_detail = "Inspecting GitHub repo..."
        inspection, readme_text, report = await asyncio.to_thread(
            inspect_github, url,
        )

        red_flags = inspection.get("red_flags", [])
        # Combine readme + report as analysis text
        text = f"{readme_text}\n\n{report}"

        state.last_inspection = inspection
        state.last_text = text
        state.last_red_flags = red_flags
        state.last_input = url
        state.last_input_type = "github"
        state.last_prompt_version = 2

        # Step 2: analyze (extract + judge, non-interactive for TUI)
        state.status = STATUS_EXTRACTING
        state.status_detail = "Analyzing..."
        result = await asyncio.to_thread(
            analyze,
            text=text,
            api_key=state.api_key,
            model=state.model,
            provider=state.provider,
            prompt_version=2,
            interactive=False,
            red_flags=red_flags,
        )

        state.record_analysis(result)
        return result

    except Exception as e:
        state.status = STATUS_ERROR
        state.status_detail = str(e)
        raise


# ---------------------------------------------------------------------------
# Web URL dispatch
# ---------------------------------------------------------------------------

async def dispatch_web(url: str, state: AppState) -> dict:
    """Scrape web URL + analyze. Updates state.status progressively."""
    from funeralai.scraper import inspect_web
    from funeralai.analyzer import analyze

    state.reset_analysis()

    try:
        # Step 1: inspect
        state.status = STATUS_INSPECTING
        state.status_detail = "Fetching web page..."
        inspection, page_content, report = await asyncio.to_thread(
            inspect_web, url,
        )

        red_flags = inspection.get("red_flags", [])
        text = f"{page_content}\n\n{report}" if page_content else report

        state.last_inspection = inspection
        state.last_text = text
        state.last_red_flags = red_flags
        state.last_input = url
        state.last_input_type = "web"
        state.last_prompt_version = 3

        # Step 2: analyze
        state.status = STATUS_EXTRACTING
        state.status_detail = "Analyzing..."
        result = await asyncio.to_thread(
            analyze,
            text=text,
            api_key=state.api_key,
            model=state.model,
            provider=state.provider,
            prompt_version=3,
            interactive=False,
            red_flags=red_flags,
        )

        state.record_analysis(result)
        return result

    except Exception as e:
        state.status = STATUS_ERROR
        state.status_detail = str(e)
        raise


# ---------------------------------------------------------------------------
# Local file dispatch
# ---------------------------------------------------------------------------

async def dispatch_file(path: str, state: AppState) -> dict:
    """Read local file + analyze."""
    from funeralai.reader import read_file
    from funeralai.analyzer import analyze

    state.reset_analysis()

    try:
        state.status = STATUS_EXTRACTING
        state.status_detail = "Reading file..."
        text = await asyncio.to_thread(read_file, path)

        state.last_text = text
        state.last_red_flags = None
        state.last_input = path
        state.last_input_type = "file"
        state.last_prompt_version = 1
        state.last_inspection = None

        state.status_detail = "Analyzing..."
        result = await asyncio.to_thread(
            analyze,
            text=text,
            api_key=state.api_key,
            model=state.model,
            provider=state.provider,
            prompt_version=1,
            interactive=False,
        )

        state.record_analysis(result)
        return result

    except Exception as e:
        state.status = STATUS_ERROR
        state.status_detail = str(e)
        raise


# ---------------------------------------------------------------------------
# Raw text dispatch
# ---------------------------------------------------------------------------

async def dispatch_text(text: str, state: AppState) -> dict:
    """Analyze raw pasted text."""
    from funeralai.analyzer import analyze

    state.reset_analysis()

    try:
        state.status = STATUS_EXTRACTING
        state.status_detail = "Analyzing..."

        state.last_text = text
        state.last_red_flags = None
        state.last_input = text[:80]
        state.last_input_type = "text"
        state.last_prompt_version = 1
        state.last_inspection = None

        result = await asyncio.to_thread(
            analyze,
            text=text,
            api_key=state.api_key,
            model=state.model,
            provider=state.provider,
            prompt_version=1,
            interactive=False,
        )

        state.record_analysis(result)
        return result

    except Exception as e:
        state.status = STATUS_ERROR
        state.status_detail = str(e)
        raise


# ---------------------------------------------------------------------------
# Multi-model vote dispatch
# ---------------------------------------------------------------------------

async def dispatch_vote(
    providers: list[str],
    state: AppState,
    text: str | None = None,
) -> dict:
    """Run multi-model vote on given text or last analysis text."""
    from funeralai.analyzer import analyze_vote

    text = text or state.last_text
    if not text:
        raise ValueError("No text available for vote")

    prompt_version = state.last_prompt_version or 1
    red_flags = state.last_red_flags

    state.reset_analysis()

    try:
        state.status = STATUS_JUDGING
        state.status_detail = f"Voting across {len(providers)} models..."

        result = await asyncio.to_thread(
            analyze_vote,
            text=text,
            providers=providers,
            model=state.model,
            prompt_version=prompt_version,
            interactive=False,
            red_flags=red_flags,
        )

        state.record_analysis(result)
        return result

    except Exception as e:
        state.status = STATUS_ERROR
        state.status_detail = str(e)
        raise


# ---------------------------------------------------------------------------
# Batch dispatch
# ---------------------------------------------------------------------------

async def dispatch_batch(files: list[str], state: AppState) -> list[dict]:
    """Analyze multiple files serially."""
    from funeralai.analyzer import analyze_batch

    state.reset_analysis()
    state.last_input = f"{len(files)} files"
    state.last_input_type = "batch"
    state.last_inspection = None

    try:
        state.status = STATUS_EXTRACTING
        state.status_detail = f"Batch: 0/{len(files)}"

        def _on_complete(path: str, entry: dict) -> None:
            done = sum(1 for _ in filter(None, results_so_far))
            state.status_detail = f"Batch: {done}/{len(files)}"

        results_so_far: list[dict] = []

        def _tracked_callback(path: str, entry: dict) -> None:
            results_so_far.append(entry)
            _on_complete(path, entry)

        results = await asyncio.to_thread(
            analyze_batch,
            files=files,
            api_key=state.api_key,
            model=state.model,
            provider=state.provider,
            on_complete=_tracked_callback,
        )

        state.status = STATUS_DONE
        state.status_detail = f"Batch complete: {len(results)} files"
        state.current_result = results
        state.analyses.append({"batch_results": results, "_source": state.last_input})
        return results

    except Exception as e:
        state.status = STATUS_ERROR
        state.status_detail = str(e)
        raise


# ---------------------------------------------------------------------------
# Question flow helpers (for future interactive TUI Q&A)
# ---------------------------------------------------------------------------

async def get_questions(
    extraction_raw: str,
    text: str,
    red_flags: list[str] | None,
    provider_name: str,
    api_key: str,
    model: str | None = None,
) -> tuple[list[dict], str]:
    """Build question list from extraction result. Returns (questions, lang)."""
    from funeralai.analyzer import parse_json
    from funeralai.questioner import build_questions

    parsed = parse_json(extraction_raw)
    gaps = []
    if parsed and isinstance(parsed, dict):
        gaps = parsed.get("gaps", [])

    return await asyncio.to_thread(
        build_questions,
        text=text,
        gaps=gaps,
        red_flags=red_flags or [],
        provider_name=provider_name,
        api_key=api_key,
        model=model,
    )


def format_answers(answers: list[dict], lang: str = "zh") -> str:
    """Format user answers into supplementary text for judge."""
    from funeralai.questioner import format_answers_for_judge
    return format_answers_for_judge(answers, lang=lang)


# ---------------------------------------------------------------------------
# Chat dispatch
# ---------------------------------------------------------------------------

# Regex to extract a trailing [ACTION: /command arg] from the LLM reply
_ACTION_RE = __import__("re").compile(
    r"\[ACTION:\s*/(\w+)\s*(.*?)\]\s*$"
)


async def dispatch_chat(text: str, state: AppState) -> dict:
    """Send a short chat message to the LLM and return reply + optional action.

    Does NOT modify analysis state (last_text, analyses, etc.).

    Returns::

        {
            "reply": "好的，后续使用 DeepSeek。",
            "action_intent": Intent(...) | None,
        }
    """
    from funeralai.tui.intent import Intent

    state.status = STATUS_CHATTING

    try:
        user_content = _build_chat_user_content(text, state)

        from pathlib import Path
        from funeralai.analyzer import call_llm, load_prompt

        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "chat.md"
        system_prompt = load_prompt(prompt_path)

        raw_reply = await asyncio.to_thread(
            call_llm,
            provider_name=state.provider,
            system_prompt=system_prompt,
            user_content=user_content,
            api_key=state.api_key,
            model=state.model,
            max_tokens=1200 if state.current_result else 500,
        )

        reply, action_intent = _extract_chat_action(raw_reply.strip())
        state.status = STATUS_DONE
        return {"reply": reply, "action_intent": action_intent}

    except Exception as e:
        state.status = STATUS_ERROR
        state.status_detail = str(e)
        raise


def _build_chat_user_content(text: str, state: AppState) -> str:
    """Assemble the user content block sent to the chat LLM.

    Includes the user's message, current provider/model, and a rich summary
    of the last analysis result (verdict, evidence, product_reality, etc.)
    so the LLM can answer follow-up questions about the analysis.
    """
    parts: list[str] = [text]

    parts.append(f"\n---\nProvider: {state.provider} ({state.default_model})")

    if state.last_input:
        parts.append(f"Last analysis source: {state.last_input}")

    if state.current_result and isinstance(state.current_result, dict):
        r = state.current_result
        ctx: list[str] = []
        if r.get("article_type"):
            ctx.append(f"Type: {r['article_type']}")
        if r.get("verdict"):
            ctx.append(f"Verdict: {r['verdict']}")
        if r.get("investment_recommendation"):
            ctx.append(f"Recommendation: {r['investment_recommendation']}")
        if r.get("product_reality"):
            ctx.append(f"Product reality: {r['product_reality']}")
        if r.get("evidence") and isinstance(r["evidence"], dict):
            for cat, items in r["evidence"].items():
                if items and isinstance(items, list):
                    ctx.append(f"Evidence ({cat}): {'; '.join(str(i) for i in items[:3])}")
        if r.get("red_flags") and isinstance(r["red_flags"], list):
            ctx.append(f"Red flags: {', '.join(str(f) for f in r['red_flags'][:5])}")
        if ctx:
            parts.append("--- Analysis context ---\n" + "\n".join(ctx))

    return "\n".join(parts)


def _extract_chat_action(reply: str) -> tuple[str, "Intent | None"]:
    """Parse a trailing ``[ACTION: /command arg]`` from the LLM reply.

    Returns ``(display_text, intent_or_none)``.
    Only recognises switch_provider, switch_model, switch_lang actions.
    """
    from funeralai.tui.intent import Intent

    match = _ACTION_RE.search(reply)
    if not match:
        return reply, None

    cmd = match.group(1).lower()
    arg = match.group(2).strip()

    # Remove the action tag from display text
    display = reply[: match.start()].rstrip()

    if cmd == "provider" and arg:
        return display, Intent(type="switch_provider", raw=reply, provider=arg.lower())
    if cmd == "model" and arg:
        return display, Intent(type="switch_model", raw=reply, model=arg)
    if cmd == "lang" and arg:
        return display, Intent(type="switch_lang", raw=reply, lang=arg.lower())

    # Unrecognised action — ignore it, still strip the tag
    return display, None

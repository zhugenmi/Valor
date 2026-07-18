"""Bull-Bear Debate agent (3-stage sub-workflow).

Merges the former researcher_bull + researcher_bear + debate_room into a single
workflow node that internally runs 3 sequential LLM stages: bull case, bear case,
and verdict. Each stage appends its own HumanMessage to state.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import ast
import json
import re
from typing import Callable, Optional

from langchain_core.messages import HumanMessage

from valor.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from valor.tools.openrouter_config import get_chat_completion
from valor.utils.api_utils import agent_endpoint, log_llm_interaction
from valor.utils.logging_config import setup_logger
from valor.utils.prompt_loader import format_prompt

logger = setup_logger("bull_bear_debate_agent")

StageCallback = Optional[Callable[[str, dict], None]]

SYSTEM_PROMPT = (
    "你是金融分析助手。必须严格按用户指定的JSON格式返回，"
    "禁止输出任何JSON之外的文字、解释、前言或markdown代码块。"
)

DIMENSION_AGENT_NAMES = [
    "technical_analyst_agent",
    "fundamentals_agent",
    "valuation_agent",
    "capital_sentiment_agent",
    "macro_industry_agent",
]


def _load_dimension_signal(state: AgentState, agent_name: str) -> dict:
    """Fetch a dimension agent's output; return neutral placeholder if missing."""
    for message in reversed(state["messages"]):
        if getattr(message, "name", None) == agent_name:
            try:
                return json.loads(message.content)
            except (json.JSONDecodeError, TypeError):
                try:
                    return ast.literal_eval(message.content)
                except (ValueError, SyntaxError, TypeError):
                    break
    logger.warning("Missing %s output, falling back to neutral signal", agent_name)
    return {"signal": "neutral", "confidence": "0%", "reasoning": f"{agent_name} 输出缺失"}


def _parse_llm_json(raw: str) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                return None
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if 0 <= start < end:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                return None
    return None


def _build_dimension_block(state: AgentState, agent_name: str) -> str:
    """Render a dimension agent's output as a text block for the LLM."""
    signal = _load_dimension_signal(state, agent_name)
    return json.dumps(signal, ensure_ascii=False)


def _run_stage(state: AgentState, prompt_path: str, **format_kwargs) -> dict:
    """Run one LLM stage and return its parsed output dict."""
    user_content = format_prompt(prompt_path, **format_kwargs)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        raw_response = log_llm_interaction(state)(get_chat_completion)(messages)
        if raw_response is None or not raw_response.strip():
            logger.error("❌ LLM 调用返回空 (stage=%s) - 检查 API Key/网络/配额", prompt_path)
            return {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": "LLM 调用失败（返回空），请检查 API Key、网络连接或模型配额",
            }
        parsed = _parse_llm_json(raw_response)
        if parsed is None:
            preview = raw_response[:200].replace("\n", " ")
            logger.error(
                "❌ 无法解析 LLM JSON (stage=%s), raw=%s",
                prompt_path, raw_response[:500],
            )
            return {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"LLM 返回内容无法解析为 JSON: {preview}",
            }
        return parsed
    except Exception as exc:
        logger.error("❌ LLM 调用异常 (stage=%s): %s", prompt_path, exc)
        return {
            "signal": "neutral",
            "confidence": 0.0,
            "reasoning": f"LLM 调用异常: {exc}",
        }


@agent_endpoint("bull_bear_debate", "多空辩论室，3阶段子工作流：多头论点 -> 空头论点 -> 综合裁决")
def bull_bear_debate_agent(state: AgentState, stage_callback: StageCallback = None):
    """3-stage bull/bear/verdict sub-workflow as a single workflow node.

    Args:
        state: Agent state.
        stage_callback: Optional callable invoked as ``stage_callback(sub_key, payload)``
            immediately after each stage's LLM call returns. ``sub_key`` is one of
            ``"bull"``, ``"bear"``, ``"verdict"``. Used by the SSE layer to stream
            sub-events incrementally instead of waiting for the whole node to finish.
    """
    show_workflow_status("Bull Bear Debate")
    show_reasoning = state["metadata"]["show_reasoning"]

    # Gather dimension signals
    dimension_blocks = {
        name.split("_agent")[0]: _build_dimension_block(state, name)
        for name in DIMENSION_AGENT_NAMES
    }

    # Stage 1: bull case
    logger.info("🐂 Stage 1/3: 多方论点")
    bull_payload = _run_stage(
        state,
        "prompts/bull_bear_debate/bull.md",
        technical=dimension_blocks["technical_analyst"],
        fundamentals=dimension_blocks["fundamentals"],
        valuation=dimension_blocks["valuation"],
        capital_sentiment=dimension_blocks["capital_sentiment"],
        macro_industry=dimension_blocks["macro_industry"],
    )
    bull_payload.setdefault("signal", "bullish")
    bull_payload.setdefault("confidence", 0.5)
    bull_payload.setdefault("key_points", [])
    bull_payload.setdefault("reasoning", "")
    bull_message = HumanMessage(
        content=json.dumps(bull_payload, ensure_ascii=False),
        name="bull_case_agent",
    )
    if stage_callback:
        stage_callback("bull", bull_payload)

    # Stage 2: bear case
    logger.info("🐻 Stage 2/3: 空头论点")
    bear_payload = _run_stage(
        state,
        "prompts/bull_bear_debate/bear.md",
        technical=dimension_blocks["technical_analyst"],
        fundamentals=dimension_blocks["fundamentals"],
        valuation=dimension_blocks["valuation"],
        capital_sentiment=dimension_blocks["capital_sentiment"],
        macro_industry=dimension_blocks["macro_industry"],
    )
    bear_payload.setdefault("signal", "bearish")
    bear_payload.setdefault("confidence", 0.5)
    bear_payload.setdefault("key_points", [])
    bear_payload.setdefault("reasoning", "")
    bear_message = HumanMessage(
        content=json.dumps(bear_payload, ensure_ascii=False),
        name="bear_case_agent",
    )
    if stage_callback:
        stage_callback("bear", bear_payload)

    # Stage 3: verdict
    logger.info("⚖️ Stage 3/3: 综合裁决")
    verdict_payload = _run_stage(
        state,
        "prompts/bull_bear_debate/verdict.md",
        bull_case=json.dumps(bull_payload, ensure_ascii=False),
        bear_case=json.dumps(bear_payload, ensure_ascii=False),
    )
    verdict_payload.setdefault("signal", "neutral")
    verdict_payload.setdefault("confidence", 0.5)
    verdict_payload.setdefault("bull_confidence", bull_payload["confidence"])
    verdict_payload.setdefault("bear_confidence", bear_payload["confidence"])
    verdict_payload.setdefault("reasoning", "")
    verdict_message = HumanMessage(
        content=json.dumps(verdict_payload, ensure_ascii=False),
        name="bull_bear_debate_agent",
    )
    if stage_callback:
        stage_callback("verdict", verdict_payload)

    if show_reasoning:
        show_agent_reasoning(verdict_payload, "Bull Bear Debate")
        state["metadata"]["agent_reasoning"] = verdict_payload

    show_workflow_status("Bull Bear Debate", "completed")
    return {
        "messages": state["messages"] + [bull_message, bear_message, verdict_message],
        "data": {**state["data"], "debate_analysis": verdict_payload},
        "metadata": state["metadata"],
    }

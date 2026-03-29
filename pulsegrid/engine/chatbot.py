import json
import os
import urllib.request
from typing import Any, Dict, Optional

from .chain import QUESTIONS, diagnose

GENERAL_EXPLAINERS = {
    "circuit breaker": "A circuit breaker is a safety gate between services. When one dependency keeps failing, the breaker opens and temporarily stops more calls from hitting it, which prevents retries and connection pressure from cascading through the stack.",
    "retry": "Retries are extra attempts after a request fails. They help with brief transient issues, but if they are too aggressive they multiply load and can turn a small incident into a major outage.",
    "latency": "Latency is how long a request takes to complete. Rising latency is often an early warning that a dependency is slowing down before full errors appear.",
    "timeout": "A timeout happens when a service waits too long for a response and gives up. Clusters of timeouts usually mean a dependency is overloaded, unreachable, or routing is degraded.",
    "queue": "A queue buffers work that should be processed later or by background workers. When queue depth grows faster than workers can drain it, downstream delays and service lag build quickly.",
    "blast radius": "Blast radius is the set of other services likely to be affected after one dependency degrades. PulseGrid uses the dependency graph to estimate where risk spreads next.",
}


def _labels_from_responses(responses: Dict[str, Any]) -> Dict[str, str]:
    label_map: Dict[str, str] = {}
    for q in QUESTIONS:
        label_map[q["id"]] = q["text"]
    return label_map


def _question_by_step(step: Optional[int]) -> Optional[Dict[str, Any]]:
    if step is None:
        return None
    try:
        idx = int(step)
    except Exception:
        return None
    if 0 <= idx < len(QUESTIONS):
        return QUESTIONS[idx]
    return None


def _selected_labels(responses: Dict[str, Any]) -> Dict[str, list]:
    out: Dict[str, list] = {}
    for q in QUESTIONS:
        raw = responses.get(q["id"], [])
        raw_list = [raw] if isinstance(raw, str) else list(raw or [])
        labels = [opt["label"] for opt in q["options"] if opt["id"] in raw_list]
        if labels:
            out[q["id"]] = labels
    return out


def _call_openai(system_prompt: str, user_message: str) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("PULSEGRID_CHAT_MODEL", "gpt-4.1-mini")
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_message}]},
        ],
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"].strip()
        # fallback parse older/expanded structure
        for item in data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    return text.strip()
    except Exception:
        return None
    return None


def _fallback_diagnostic(message: str, responses: Dict[str, Any], step: Optional[int], current_question: Optional[str]) -> str:
    msg = (message or "").strip()
    lowered = msg.lower()
    selected = _selected_labels(responses)
    tentative = diagnose(responses or {})
    q = _question_by_step(step)
    q_text = current_question or (q["text"] if q else None)

    for term, explainer in GENERAL_EXPLAINERS.items():
        if term in lowered:
            suffix = f" Right now, I still need you to answer: {q_text}" if q_text else ""
            return explainer + suffix

    if any(k in lowered for k in ["what do you mean", "explain", "clarify", "what counts as"]) and q:
        labels = ", ".join(opt["label"] for opt in q["options"][:3])
        return (
            f"At this step I'm collecting evidence for the current layer. {q['text']} "
            f"Examples in this question include {labels}. Pick every option that actually matches your incident, then confirm."
        )

    if any(k in lowered for k in ["what do you know", "so far", "summary", "based on this", "tentative"]):
        chosen = []
        for labels in selected.values():
            chosen.extend(labels)
        chosen_text = ", ".join(chosen[:5]) if chosen else "no strong signals yet"
        scenario = tentative.get("matched_scenario", "healthy_baseline").replace("_", " ")
        risk = round((tentative.get("risk_score", 0) or 0) * 100)
        return (
            f"So far, the strongest clues are: {chosen_text}. Tentatively this resembles {scenario} at about {risk}% risk, "
            f"but I still need a few more answers before I lock the diagnosis."
        )

    if any(k in lowered for k in ["dog", "homework", "girlfriend", "boyfriend", "cat"]):
        return (
            "That sounds unrelated to the cloud incident. In this chat I can help with the infrastructure diagnosis. "
            + (f"Please answer the current question: {q_text}" if q_text else "Tell me what users or telemetry are showing.")
        )

    return (
        "I can use what you type here to clarify the diagnosis, explain terms, or summarize what the current answers imply. "
        + (f"For now, please answer: {q_text}" if q_text else "Continue by describing the incident symptoms.")
    )


def _fallback_scenario(message: str, scenario: str, scenario_context: Dict[str, Any], scenario_state: Optional[Dict[str, Any]]) -> str:
    msg = (message or "").strip()
    lowered = msg.lower()
    summary = scenario_context.get("summary") or ""
    recs = (scenario_state or {}).get("recommendations", {})
    sys_state = (scenario_state or {}).get("system_state", {})

    for term, explainer in GENERAL_EXPLAINERS.items():
        if term in lowered:
            return explainer

    if any(k in lowered for k in ["what happened", "cause", "why", "root"]):
        return summary or f"This scenario models {scenario.replace('_', ' ')}."

    if any(k in lowered for k in ["risk", "score", "severity", "state"]):
        state = sys_state.get("state", "unknown")
        score = round((sys_state.get("score", 0) or 0) * 100)
        return f"The current system state is {state} at {score}% composite risk in the {scenario.replace('_', ' ')} scenario."

    if any(k in lowered for k in ["notify", "page", "who do i tell", "who should i notify"]):
        return (
            "Notify the service owner for the primary failing dependency, the SRE or incident lead, and customer communications if users are impacted. "
            "For regulated or region-level incidents, pull in platform leadership and compliance early."
        )

    if any(k in lowered for k in ["what do i do", "action", "mitigation", "fix", "next step"]):
        immediate = recs.get("immediate_actions", [])[:3]
        optimize = recs.get("optimization_opportunities", [])[:2]
        parts = []
        if immediate:
            parts.append("Immediate actions: " + "; ".join(immediate))
        if optimize:
            parts.append("Then: " + "; ".join(optimize))
        return " ".join(parts) if parts else "No concrete actions are available yet for this scenario."

    if any(k in lowered for k in ["how long", "mttr", "resolve", "recovery"]):
        return (
            "Resolution time depends on whether this is a routing, capacity, or dependency failure. In this prototype, treat recovery as fastest when you stop the main amplifier first — reroute traffic, cap retries, restore redundancy, or fail over the degraded dependency."
        )

    layers = scenario_context.get("layers") or []
    if any(k in lowered for k in ["context", "pre-signal", "upstream", "world", "layer"]):
        snippets = []
        for layer in layers[:2]:
            sigs = layer.get("signals") or []
            if sigs:
                snippets.append(f"{layer.get('name', 'Layer')}: {sigs[0]}")
        return "Pre-signal context: " + "; ".join(snippets) if snippets else "No upstream context is available for this scenario."

    return (
        f"I can answer follow-ups about the {scenario.replace('_', ' ')} scenario — cause, risk, actions, notifications, or how the chain propagates. "
        f"Current context: {summary or 'scenario loaded.'}"
    )


def answer_chat(
    message: str,
    mode: str = "scenario",
    scenario: Optional[str] = None,
    responses: Optional[Dict[str, Any]] = None,
    step: Optional[int] = None,
    current_question: Optional[str] = None,
    scenario_context: Optional[Dict[str, Any]] = None,
    scenario_state: Optional[Dict[str, Any]] = None,
) -> str:
    responses = responses or {}
    scenario_context = scenario_context or {}

    if mode == "diagnostic":
        system_prompt = (
            "You are PulseGrid AI, a cloud incident diagnosis assistant. Be concise, practical, and grounded in the partial answers already collected. "
            "Do not pretend the diagnosis is complete. Clarify the current question, explain cloud reliability terms, and steer the user back to the active diagnostic step when needed."
        )
        selected = _selected_labels(responses)
        context_lines = []
        for qid, labels in selected.items():
            context_lines.append(f"{qid}: {', '.join(labels)}")
        q = current_question or (_question_by_step(step) or {}).get("text", "")
        user_prompt = (
            f"Current diagnostic step: {step}\n"
            f"Active question: {q}\n"
            f"Selected evidence so far: {' | '.join(context_lines) if context_lines else 'none'}\n"
            f"User message: {message}"
        )
        live = _call_openai(system_prompt, user_prompt)
        return live or _fallback_diagnostic(message, responses, step, current_question)

    system_prompt = (
        "You are PulseGrid AI, a scenario-aware cloud resilience assistant. Answer follow-up questions about the active scenario, "
        "using the scenario summary, state, and recommended actions. Keep answers practical and concise."
    )
    user_prompt = (
        f"Scenario: {scenario}\n"
        f"Scenario summary: {scenario_context.get('summary', '')}\n"
        f"System state: {json.dumps((scenario_state or {}).get('system_state', {}))}\n"
        f"Recommendations: {json.dumps((scenario_state or {}).get('recommendations', {}))}\n"
        f"User message: {message}"
    )
    live = _call_openai(system_prompt, user_prompt)
    return live or _fallback_scenario(message, scenario or "current scenario", scenario_context, scenario_state)

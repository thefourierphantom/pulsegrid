# PulseGrid AI — Chatbot and Intelligence Engine Setup

PulseGrid uses OpenAI for three distinct AI functions:

1. **Free-text bypass** — recognizes a complete incident description and skips the wizard
2. **Open-ended diagnosis** — generates a full 7-layer chain analysis for novel incidents that don't match the 13 pre-built templates
3. **Scenario follow-up chat** — answers questions about an active incident using chain context

## Environment Variables

```bash
export OPENAI_API_KEY="sk-..."             # Required for GPT features
export PULSEGRID_CHAT_MODEL="gpt-4.1-mini" # Optional, this is the default
```

## Run

```bash
cd pulsegrid
python run.py
# → http://localhost:8000
```

## What works without an API key

- Full structured diagnosis via the 5-question wizard
- All 13 pre-built scenario simulations
- Signal extraction and scenario matching
- Mitigation playbooks (deterministic, from hardcoded templates)
- Blast radius propagation
- Progressive live dashboard

## What requires an API key

- Free-text bypass (recognizing a complete incident from a paragraph)
- Open-ended analysis for novel incidents not in the 13 templates
- AI-written incident briefs with specific narrative context
- Post-diagnosis follow-up chatbot responses

## Open-Ended Analysis

When an incident description doesn't match any of the 13 known patterns at sufficient confidence (score < 6), the system calls `open_ended_diagnose()` which prompts GPT to generate a complete 7-layer chain analysis from scratch. The model is instructed to:

- Populate each layer (L0–L6) with real, specific factors from the description
- Assign a risk score and state
- Write a 2-3 sentence incident summary
- Generate a now/next/prevent mitigation playbook

The result uses the same data structure as the pre-built scenarios, so it renders identically in the dashboard.

## Fallback behavior

If OpenAI is unavailable or the API call fails, the system:
- For free-text input with enough signal: runs structured scenario matching and uses the best-fit template
- For the chatbot: uses the built-in `_fallback_diagnostic()` function, which provides scenario-aware, pattern-matched responses without GPT
- For incident briefs: generates a deterministic narrative from the matched scenario summary and playbook

No API key = no degraded experience for the core diagnostic flow. Just no GPT narrative polish.

## Model API

PulseGrid uses the OpenAI Responses API (`/v1/responses`) not the older Chat Completions format. The model string is `gpt-4.1-mini` by default. To use a different model:

```bash
export PULSEGRID_CHAT_MODEL="gpt-4.1"
```

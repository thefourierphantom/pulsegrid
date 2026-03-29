# PulseGrid Chatbot Setup

PulseGrid now supports two chatbot modes:

1. **Diagnostic Chat** in the incident questionnaire
2. **Scenario Follow-up Chat** in the simulation/results screen

## How it works

- If `OPENAI_API_KEY` is set in the environment, PulseGrid calls the OpenAI Responses API and uses a live model for grounded answers.
- If no API key is set, PulseGrid falls back to a built-in deterministic assistant that is still scenario-aware and diagnosis-aware.

## Environment variables

- `OPENAI_API_KEY` — required for model-backed chat
- `PULSEGRID_CHAT_MODEL` — optional, defaults to `gpt-4.1-mini`

## Example

```bash
export OPENAI_API_KEY="your_api_key_here"
export PULSEGRID_CHAT_MODEL="gpt-4.1-mini"
python3 pulsegrid/run.py
```

## Important note

This implementation integrates a live model. It does **not** train a new custom model locally inside this repo. For a weekend hackathon, that is the right tradeoff: you get a real chatbot experience without building a full fine-tuning or retrieval training pipeline.

import os
import sys


ROOT = os.path.dirname(os.path.dirname(__file__))
PKG_ROOT = os.path.join(ROOT, "pulsegrid")
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

from engine.chatbot import extract_signals_for_wizard_inputs


def test_attachment_evidence_prefills_structural_single_dependency():
    prompt = "Auth and API calls are intermittently failing; DNS/service discovery feels unstable."
    attachment = (
        "Auth, API gateway, and checkout rely on internal service discovery. "
        "Critical services depend on a shared DNS resolver pool. "
        "Shared resolver concentration had been flagged as a resilience concern."
    )

    result = extract_signals_for_wizard_inputs(prompt_text=prompt, attachment_text=attachment, existing_answers={})

    assert "q_structural" in result["pre_answers"]
    assert "single_dep" in result["pre_answers"]["q_structural"]
    assert "q_structural" in result["skippable"]


def test_prompt_and_attachment_evidence_combine_for_high_confidence():
    prompt = "There may be weak failover and redundancy in this path."
    attachment = "Resolver redundancy had already been recommended previously due to concentration concerns."

    result = extract_signals_for_wizard_inputs(prompt_text=prompt, attachment_text=attachment, existing_answers={})
    structural = result["pre_answers"].get("q_structural", [])

    assert "no_failover" in structural


def test_existing_user_answers_are_not_overridden_by_inference():
    prompt = "No major deploy; dependency timing out."
    attachment = "Critical services depend on a shared DNS resolver pool."
    existing = {"q_structural": ["scale_limited"]}

    result = extract_signals_for_wizard_inputs(prompt_text=prompt, attachment_text=attachment, existing_answers=existing)

    assert "q_structural" not in result["pre_answers"]
    assert "q_structural" in result["skippable"]

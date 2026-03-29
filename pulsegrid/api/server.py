# api/server.py
# PulseGrid HTTP API server
# Pure stdlib — no external web framework required.
#
# Endpoints:
#   GET  /                          → serves frontend/index.html
#   GET  /api/scenarios             → list available scenarios
#   POST /api/scenario/load?name=X  → pre-compute and cache a scenario
#   GET  /api/state?step=N          → full system state at step N
#   GET  /api/graph                 → static graph topology (nodes + edges)
#   GET  /static/<file>             → static asset serving

import sys
import os
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# Add parent directory to path so engine/simulator are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.graph     import SERVICES, get_edges_for_render
from engine.scoring   import score_service, system_state as compute_system_state
from engine.blast_radius    import propagate, get_blast_radius
from engine.recommendations import get_recommendations
from simulator.scenarios    import (get_scenario_history, get_scenario_context,
                                    list_scenarios, list_categories, TOTAL_STEPS)
from engine.chain           import diagnose, LAYERS, QUESTIONS
from engine.chatbot         import answer_chat, extract_and_diagnose, extract_signals_for_wizard

# ── Global scenario cache ─────────────────────────────────────────────────────
_cache_lock   = threading.Lock()
_scenario_cache: dict = {}          # name → list of frames
_active_scenario: str = "healthy_baseline"


def _compose_message_with_attachments(message: str, attachments) -> str:
    """
    Flatten attachment payload into prompt-safe text so existing
    extraction + fallback logic can consume it.
    """
    base = (message or "").strip()
    if not attachments:
        return base

    blocks = []
    for idx, item in enumerate(attachments[:3], start=1):
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or f"attachment_{idx}")[:120]
        ftype = (item.get("type") or "unknown")[:80]
        size = item.get("size", 0)
        excerpt = (item.get("text_excerpt") or "").strip()
        if excerpt:
            excerpt = excerpt[:8000]
            blocks.append(f"[Attachment {idx}: {name} ({ftype}, {size} bytes)]\n{excerpt}")
        else:
            blocks.append(f"[Attachment {idx}: {name} ({ftype}, {size} bytes)]")

    if not blocks:
        return base
    if base:
        return f"{base}\n\n" + "\n\n".join(blocks)
    return "\n\n".join(blocks)


def _ensure_scenario(name: str):
    """Pre-compute scenario history and store in cache."""
    with _cache_lock:
        if name not in _scenario_cache:
            _scenario_cache[name] = get_scenario_history(name)
    return _scenario_cache[name]


def _compute_state_at_step(scenario_name: str, step: int) -> dict:
    """
    Full state computation for one step of a scenario.
    Returns everything the frontend needs in one payload.
    """
    history = _ensure_scenario(scenario_name)
    step = max(0, min(step, TOTAL_STEPS - 1))
    frame = history[step]

    # Score each service
    service_results = {}
    base_scores     = {}
    signal_breakdown = {}
    for svc_id, telemetry in frame.items():
        result = score_service(telemetry)
        service_results[svc_id] = result
        base_scores[svc_id]     = result["score"]
        signal_breakdown[svc_id] = result["signals"]

    # Blast-radius propagation
    propagated_scores = propagate(base_scores)
    blast_radius = get_blast_radius(propagated_scores, base_scores)

    # Annotate service results with propagated scores
    for item in blast_radius:
        svc = item["service_id"]
        if svc in service_results:
            service_results[svc]["propagated_score"] = item["score"]
            service_results[svc]["propagated_delta"]  = item["propagated_delta"]

    # System-level state
    sys_state = compute_system_state(propagated_scores)

    # Recommendations
    recs = get_recommendations(
        scenario_name,
        sys_state["state"],
        propagated_scores,
        signal_breakdown
    )

    # EKG history: all steps up to and including current
    ekg_history = []
    for s in range(step + 1):
        f = history[s]
        step_base = {}
        for svc_id, tel in f.items():
            r = score_service(tel)
            step_base[svc_id] = r["score"]
        prop = propagate(step_base)
        sys_s = compute_system_state(prop)
        ekg_history.append({
            "step":        s,
            "system_score": sys_s["score"],
            "system_state": sys_s["state"],
            "service_scores": {svc: round(prop.get(svc, 0), 4)
                                for svc in SERVICES},
        })

    return {
        "scenario":      scenario_name,
        "step":          step,
        "total_steps":   TOTAL_STEPS,
        "timestamp":     int(time.time()),
        "system_state":  sys_state,
        "services":      {
            svc_id: {
                "score":             res["score"],
                "propagated_score":  res.get("propagated_score", res["score"]),
                "state":             res["state"],
                "color":             res["color"],
                "signals":           res["signals"],
                "top_signal":        res["top_signal"],
                "telemetry":         res["telemetry"],
            }
            for svc_id, res in service_results.items()
        },
        "blast_radius":  blast_radius,
        "recommendations": recs,
        "ekg_history":   ekg_history,
        "context":       get_scenario_context(scenario_name),
    }


# ── HTTP Handler ──────────────────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend"
)

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js":   "application/javascript",
    ".css":  "text/css",
    ".json": "application/json",
    ".png":  "image/png",
    ".ico":  "image/x-icon",
}


class PulseGridHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Quieter logs
        print(f"  [{self.log_date_time_string()}] {fmt % args}")

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        mime = MIME.get(ext, "application/octet-stream")
        try:
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed  = urlparse(self.path)
        path    = parsed.path
        params  = parse_qs(parsed.query)

        # ── Root → serve index.html
        if path in ("/", "/index.html"):
            self._send_file(os.path.join(FRONTEND_DIR, "index.html"))
            return

        # ── Static assets
        if path.startswith("/static/"):
            fname = path[len("/static/"):]
            self._send_file(os.path.join(FRONTEND_DIR, "static", fname))
            return

        # ── API: list scenarios
        if path == "/api/scenarios":
            self._send_json({"scenarios": list_scenarios(),
                              "categories": list_categories()})
            return

        # ── API: graph topology
        if path == "/api/graph":
            nodes = [
                {"id": svc_id, "label": meta["label"], "tier": meta["tier"],
                 "x": meta["x"], "y": meta["y"]}
                for svc_id, meta in SERVICES.items()
            ]
            edges = get_edges_for_render()
            self._send_json({"nodes": nodes, "edges": edges})
            return

        # ── API: state at step
        if path == "/api/state":
            scenario = params.get("scenario", [_active_scenario])[0]
            step     = int(params.get("step", ["0"])[0])
            try:
                state = _compute_state_at_step(scenario, step)
                self._send_json(state)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        # ── API: diagnostic questions schema
        if path == "/api/questions":
            self._send_json({"questions": QUESTIONS, "layers": LAYERS})
            return

        # ── API: extract signals from free-text for smart wizard skipping
        if path == "/api/extract":
            msg = params.get("message", [""])[0].strip()
            if not msg:
                self._send_json({"pre_answers": {}, "skippable": [], "is_complete": False})
                return
            try:
                result = extract_signals_for_wizard(msg)
                self._send_json(result)
            except Exception as e:
                self._send_json({"pre_answers": {}, "skippable": [], "is_complete": False, "error": str(e)})
            return

        # ── 404
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/extract":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length) if length else b"{}"
                payload = json.loads(body) if body else {}
                message = (payload.get("message") or "").strip()
                attachments = payload.get("attachments") or []
                merged_message = _compose_message_with_attachments(message, attachments)
                if not merged_message.strip():
                    self._send_json({"pre_answers": {}, "skippable": [], "is_complete": False})
                    return
                result = extract_signals_for_wizard(merged_message)
                self._send_json(result)
            except Exception as e:
                self._send_json({"pre_answers": {}, "skippable": [], "is_complete": False, "error": str(e)})
            return

        if path == "/api/scenario/load":
            name = params.get("name", ["healthy_baseline"])[0]
            _ensure_scenario(name)
            self._send_json({"status": "ok", "scenario": name,
                              "total_steps": TOTAL_STEPS})
            return

        # ── API: run diagnostic
        if path == "/api/diagnose":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length) if length else b"{}"
                responses = json.loads(body)
                result = diagnose(responses)
                self._send_json(result)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        # ── API: chat assistant for diagnostic + scenario follow-ups
        if path == "/api/chat":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length) if length else b"{}"
                payload = json.loads(body) if body else {}
                mode = payload.get("mode", "scenario")
                message = payload.get("message", "")
                attachments = payload.get("attachments") or []
                scenario = payload.get("scenario") or _active_scenario
                responses = payload.get("responses") or {}
                step = payload.get("step")
                current_question = payload.get("current_question")
                enriched_message = _compose_message_with_attachments(message, attachments)

                # ── Free-text bypass: if diagnostic mode and message describes incident,
                #    extract signals and return full diagnosis so frontend can skip wizard
                if mode == "diagnostic" and enriched_message:
                    bypass = extract_and_diagnose(enriched_message)
                    if bypass is not None:
                        self._send_json({
                            "reply":       bypass["narrative"],
                            "full_result": bypass["full_result"],
                            "scenario":    bypass["scenario"],
                            "risk_score":  bypass["risk_score"],
                            "risk_state":  bypass["risk_state"],
                        })
                        return

                # Extra context fields from enriched cbSend payload
                chain_summary = payload.get("chain_summary", "")
                blast_radius_summary = payload.get("blast_radius", "")
                top_action = payload.get("top_action", "")
                client_risk_state = payload.get("risk_state", "")
                client_risk_score = payload.get("risk_score", 0)

                scenario_context = get_scenario_context(scenario) if scenario else {}
                scenario_state = None
                if mode == "scenario" and scenario:
                    requested_step = payload.get("scenario_step")
                    if requested_step is None:
                        requested_step = TOTAL_STEPS - 1
                    try:
                        scenario_state = _compute_state_at_step(scenario, int(requested_step))
                    except Exception:
                        scenario_state = None

                    # Inject client-side chain/blast context into scenario_state so
                    # the system prompt gets enriched even when demo mode is active
                    if scenario_state and (chain_summary or blast_radius_summary):
                        scenario_state["_chain_summary"]  = chain_summary
                        scenario_state["_blast_summary"]  = blast_radius_summary
                        scenario_state["_top_action"]     = top_action

                # Augment message with extra context when provided
                augmented_message = enriched_message
                if mode == "scenario" and chain_summary:
                    augmented_message = (
                        f"{enriched_message}\n\n[Context: chain={chain_summary} | "
                        f"blast={blast_radius_summary} | "
                        f"risk={client_risk_state} {round(float(client_risk_score)*100)}% | "
                        f"top_action={top_action[:100]}]"
                    )

                reply = answer_chat(
                    message=augmented_message,
                    mode=mode,
                    scenario=scenario,
                    responses=responses,
                    step=step,
                    current_question=current_question,
                    scenario_context=scenario_context,
                    scenario_state=scenario_state,
                    attachments=attachments,
                )
                self._send_json({"reply": reply})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        self.send_response(404)
        self.end_headers()


def run(host="0.0.0.0", port=8765):
    # Pre-warm all scenarios
    print("  PulseGrid — pre-computing scenarios...")
    for name in ("healthy_baseline", "retry_storm", "dns_degradation",
                 "queue_backlog", "regional_divergence", "hurricane_datacenter",
                 "power_grid_brownout", "seismic_failure", "bgp_route_leak",
                 "regulatory_reroute", "cdn_sanctions",
                 "vendor_capacity_crunch", "cost_cut_redundancy"):
        _ensure_scenario(name)
        print(f"    ✓ {name}")

    server = HTTPServer((host, port), PulseGridHandler)
    print(f"\n  ┌─────────────────────────────────────────┐")
    print(f"  │  PulseGrid running at http://{host}:{port}  │")
    print(f"  └─────────────────────────────────────────┘\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  PulseGrid stopped.")
        server.server_close()

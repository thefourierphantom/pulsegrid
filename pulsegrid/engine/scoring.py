# engine/scoring.py
# PulseGrid risk scoring engine
#
# Converts raw telemetry signals into a normalized risk score [0.0, 1.0]
# and maps it to a named risk state.
#
# Composite score formula:
#   risk = Σ(weight_i * normalized_signal_i) with multi-signal amplification

# ── State thresholds ─────────────────────────────────────────────────────────
STATE_THRESHOLDS = [
    (0.80, "cascading"),
    (0.65, "vulnerable"),
    (0.45, "unstable"),
    (0.25, "watch"),
    (0.00, "healthy"),
]

STATE_COLORS = {
    "healthy":    "#22c55e",
    "watch":      "#eab308",
    "unstable":   "#f97316",
    "vulnerable": "#ef4444",
    "cascading":  "#7c3aed",
}

STATE_ORDER = ["healthy", "watch", "unstable", "vulnerable", "cascading"]

# ── Signal weights ────────────────────────────────────────────────────────────
# Must sum to 1.0
SIGNAL_WEIGHTS = {
    "latency_drift":     0.28,
    "error_creep":       0.25,
    "retry_amplify":     0.20,
    "timeout_cluster":   0.15,
    "resource_pressure": 0.12,
}

# ── Healthy baseline ranges for normalization ─────────────────────────────────
# (healthy_max) — values above this map to increasing stress [0→1]
SIGNAL_STRESS_BOUNDS = {
    "latency_ms":       {"lo": 20,   "hi": 800,  "invert": False},
    "error_rate":       {"lo": 0.0,  "hi": 0.20, "invert": False},
    "retry_rate":       {"lo": 0.0,  "hi": 0.30, "invert": False},
    "timeout_rate":     {"lo": 0.0,  "hi": 0.15, "invert": False},
    "cpu_util":         {"lo": 0.05, "hi": 0.95, "invert": False},
    "connection_count": {"lo": 0,    "hi": 500,  "invert": False},
    "queue_depth":      {"lo": 0,    "hi": 500,  "invert": False},
    "cache_hit_rate":   {"lo": 1.0,  "hi": 0.50, "invert": True},  # low hit = high stress
}


def _normalize(value, bounds):
    lo, hi = bounds["lo"], bounds["hi"]
    if hi == lo:
        return 0.0
    norm = (value - lo) / (hi - lo)
    if bounds.get("invert"):
        norm = (lo - value) / (lo - hi)
    return max(0.0, min(1.0, norm))


def score_service(telemetry: dict) -> dict:
    """
    Score a single service at one timestep.

    Parameters
    ----------
    telemetry : dict with keys like latency_ms, error_rate, retry_rate,
                timeout_rate, cpu_util, connection_count, queue_depth,
                cache_hit_rate (all optional).

    Returns
    -------
    dict with score, signals breakdown, state, top_signal
    """
    # Latency drift
    lat_norm = _normalize(telemetry.get("latency_ms", 40), SIGNAL_STRESS_BOUNDS["latency_ms"])
    latency_drift = min(1.0, lat_norm * 1.1)

    # Error creep (amplified — small error rates matter a lot)
    err_norm = _normalize(telemetry.get("error_rate", 0.0), SIGNAL_STRESS_BOUNDS["error_rate"])
    error_creep = min(1.0, err_norm * 2.2)

    # Retry amplification
    ret_norm = _normalize(telemetry.get("retry_rate", 0.0), SIGNAL_STRESS_BOUNDS["retry_rate"])
    retry_amplify = min(1.0, ret_norm * 2.0)

    # Timeout clustering
    to_norm = _normalize(telemetry.get("timeout_rate", 0.0), SIGNAL_STRESS_BOUNDS["timeout_rate"])
    timeout_cluster = min(1.0, to_norm * 2.5)

    # Resource pressure: max of all resource-type signals
    cpu_p = _normalize(telemetry.get("cpu_util", 0.25), SIGNAL_STRESS_BOUNDS["cpu_util"])
    conn_p = _normalize(telemetry.get("connection_count", 30), SIGNAL_STRESS_BOUNDS["connection_count"])
    resource_pressure = max(cpu_p, conn_p)

    if "queue_depth" in telemetry:
        q_p = _normalize(telemetry["queue_depth"], SIGNAL_STRESS_BOUNDS["queue_depth"])
        resource_pressure = max(resource_pressure, min(1.0, q_p * 2.0))

    if "cache_hit_rate" in telemetry:
        c_p = _normalize(telemetry["cache_hit_rate"], SIGNAL_STRESS_BOUNDS["cache_hit_rate"])
        resource_pressure = max(resource_pressure, min(1.0, c_p * 1.8))

    resource_pressure = min(1.0, resource_pressure)

    signals = {
        "latency_drift":     round(latency_drift,   4),
        "error_creep":       round(error_creep,     4),
        "retry_amplify":     round(retry_amplify,   4),
        "timeout_cluster":   round(timeout_cluster, 4),
        "resource_pressure": round(resource_pressure, 4),
    }

    # Weighted composite score
    raw = sum(SIGNAL_WEIGHTS[k] * v for k, v in signals.items())

    # Multi-signal amplification: correlated stress is worse than isolated stress
    elevated = sum(1 for v in signals.values() if v > 0.30)
    if elevated >= 3:
        raw *= 1.20
    if elevated >= 4:
        raw *= 1.15

    score = min(1.0, raw)
    state = get_state(score)
    top_signal = max(signals, key=signals.get)

    return {
        "score":      round(score, 4),
        "state":      state,
        "color":      STATE_COLORS[state],
        "signals":    signals,
        "top_signal": top_signal,
        "telemetry":  telemetry,
    }


def get_state(score: float) -> str:
    for threshold, label in STATE_THRESHOLDS:
        if score >= threshold:
            return label
    return "healthy"


def get_state_color(state: str) -> str:
    return STATE_COLORS.get(state, "#6b7280")


def system_state(service_scores: dict) -> dict:
    """
    Derive overall system state from individual service scores.
    Uses weighted average biased toward worst-performing services.
    """
    if not service_scores:
        return {"score": 0.0, "state": "healthy", "color": STATE_COLORS["healthy"]}

    scores = list(service_scores.values())
    scores.sort(reverse=True)

    # Top-2 worst services dominate the system score
    n = len(scores)
    weighted = scores[0] * 0.50
    if n > 1:
        weighted += scores[1] * 0.30
    if n > 2:
        weighted += scores[2] * 0.15
    if n > 3:
        weighted += sum(scores[3:]) / max(1, n - 3) * 0.05

    state = get_state(weighted)
    return {
        "score": round(weighted, 4),
        "state": state,
        "color": STATE_COLORS[state],
    }

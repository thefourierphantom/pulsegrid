# engine/blast_radius.py
# PulseGrid blast-radius propagation engine
#
# Propagates risk through the service dependency graph.
# If a dependency is degrading, services that depend on it inherit elevated risk.
#
# Algorithm:
#   For each hop, for each service S with dependencies:
#     For each dependency D of S:
#       If D.score > THRESHOLD:
#           S.score += (D.score - THRESHOLD) * edge_weight * FACTOR
#   Clamp all scores to [0, 1] after each hop.

from .graph import get_dependency_map, SERVICES

PROPAGATION_THRESHOLD = 0.30   # min dep score to trigger propagation
PROPAGATION_FACTOR    = 0.50   # fraction of excess risk that transfers per hop
MAX_HOPS              = 2      # propagation depth


def propagate(base_scores: dict, hops: int = MAX_HOPS) -> dict:
    """
    Propagate risk scores through the dependency graph.

    Parameters
    ----------
    base_scores : {service_id: float [0,1]}
    hops        : propagation depth (2 is sufficient for most graphs)

    Returns
    -------
    {service_id: propagated_score}
    """
    deps = get_dependency_map()
    scores = {s: base_scores.get(s, 0.0) for s in SERVICES}

    for _ in range(hops):
        updated = dict(scores)
        for service, dependencies in deps.items():
            for dep_service, edge_weight in dependencies:
                dep_score = scores[dep_service]
                if dep_score > PROPAGATION_THRESHOLD:
                    overflow = dep_score - PROPAGATION_THRESHOLD
                    delta = overflow * edge_weight * PROPAGATION_FACTOR
                    updated[service] = min(1.0, updated[service] + delta)
        scores = updated

    return {s: round(v, 4) for s, v in scores.items()}


def get_blast_radius(propagated: dict, base: dict) -> list:
    """
    Returns a ranked list of at-risk services with propagation deltas.

    Parameters
    ----------
    propagated : scores after graph propagation
    base       : original per-service scores before propagation

    Returns
    -------
    List of dicts, sorted by propagated score descending.
    """
    results = []
    for svc_id, prop_score in propagated.items():
        base_score = base.get(svc_id, 0.0)
        delta = prop_score - base_score

        # Include any service with meaningful risk
        if prop_score > 0.15 or delta > 0.03:
            from .scoring import get_state, STATE_COLORS
            state = get_state(prop_score)
            results.append({
                "service_id":         svc_id,
                "label":              SERVICES[svc_id]["label"],
                "score":              round(prop_score, 4),
                "base_score":         round(base_score, 4),
                "propagated_delta":   round(delta, 4),
                "state":              state,
                "color":              STATE_COLORS[state],
                "at_risk":            prop_score > 0.40,
                "propagation_source": delta > 0.04,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results

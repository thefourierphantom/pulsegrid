# engine/graph.py
# PulseGrid service dependency graph
# Nodes represent cloud services; directed edges represent dependencies.
# A -> B means service A depends on service B.
# Positions are (x, y) for SVG rendering (800x500 canvas).

SERVICES = {
    "frontend":    {"label": "Frontend",     "tier": "presentation", "x": 400, "y": 55},
    "api_gateway": {"label": "API Gateway",  "tier": "gateway",      "x": 400, "y": 170},
    "auth":        {"label": "Auth",         "tier": "core",         "x": 175, "y": 295},
    "cache":       {"label": "Cache",        "tier": "data",         "x": 400, "y": 295},
    "queue":       {"label": "Queue",        "tier": "messaging",    "x": 625, "y": 295},
    "worker":      {"label": "Worker",       "tier": "processing",   "x": 625, "y": 420},
    "database":    {"label": "Database",     "tier": "data",         "x": 400, "y": 420},
}

# (source, target, weight)
# source depends on target; weight controls propagation strength
DEPENDENCIES = [
    ("frontend",    "api_gateway", 0.95),
    ("api_gateway", "auth",        0.85),
    ("api_gateway", "cache",       0.70),
    ("api_gateway", "database",    0.65),
    ("api_gateway", "queue",       0.55),
    ("queue",       "worker",      0.90),
    ("worker",      "database",    0.85),
    ("worker",      "cache",       0.60),
]

def get_dependency_map():
    """Returns {service: [(dependency, weight), ...]}"""
    deps = {s: [] for s in SERVICES}
    for src, dst, weight in DEPENDENCIES:
        deps[src].append((dst, weight))
    return deps

def get_dependents_map():
    """Returns {service: [(dependent_service, weight), ...]} — who depends ON this"""
    rev = {s: [] for s in SERVICES}
    for src, dst, weight in DEPENDENCIES:
        rev[dst].append((src, weight))
    return rev

def get_edges_for_render():
    """Returns list of (src_x, src_y, dst_x, dst_y, weight) for SVG rendering."""
    edges = []
    for src, dst, weight in DEPENDENCIES:
        sx, sy = SERVICES[src]["x"], SERVICES[src]["y"]
        dx, dy = SERVICES[dst]["x"], SERVICES[dst]["y"]
        edges.append({"src": src, "dst": dst, "sx": sx, "sy": sy,
                       "dx": dx, "dy": dy, "weight": weight})
    return edges

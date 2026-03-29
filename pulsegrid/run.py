#!/usr/bin/env python3
"""
PulseGrid — Cloud Resilience & Vulnerability Intelligence Platform
HackUSF 2026

Usage:
    python3 run.py [--port 8765]
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.server import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PulseGrid server")
    parser.add_argument("--port", type=int, default=8765,
                        help="Port to listen on (default: 8765)")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="Host to bind (default: 0.0.0.0)")
    args = parser.parse_args()
    run(host=args.host, port=args.port)

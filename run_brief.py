#!/usr/bin/env python3
"""CLI: python3 run_brief.py brief.json [--md] . Key from env QLOO_API_KEY only."""
import json, os, sys
from vibespec.agent import Brief, Constraints, run
from vibespec.blueprint import to_markdown
from vibespec.qloo import QlooService


def load(path):
    d = json.load(open(path))
    c = d.pop("constraints", {})
    c["exclude_terms"] = tuple(c.get("exclude_terms", ()))
    return Brief(constraints=Constraints(**c), anchors=tuple(d.pop("anchors")), **d)


if __name__ == "__main__":
    key = os.environ.get("QLOO_API_KEY", "")
    if not key:
        sys.exit("BLOCKED: QLOO_API_KEY not set")
    bp = run(load(sys.argv[1]), QlooService(key))
    print(to_markdown(bp) if "--md" in sys.argv else json.dumps(bp, indent=1, default=str))

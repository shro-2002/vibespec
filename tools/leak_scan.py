#!/usr/bin/env python3
"""Pre-publication scan. Lists what git WOULD publish (tracked + untracked, not ignored) and checks every such file for:
 1. the Qloo API key (from env QLOO_API_KEY) and generic key-looking strings,
 2. Qloo entity names harvested from the private cache/fixtures/eval folders (response-data leakage),
 3. forbidden paths (env files, cache, private, fixtures, anything from territory/).
Anchor brand names used as INPUTS (briefs, tests) are allow-listed: they are public brand names the user types, not Qloo output.
Run from the repo root:  QLOO_API_KEY=... python3 tools/leak_scan.py   (exit 1 on any finding)"""
import json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOW = {"new york", "london", "chicago", "los angeles", "aesop", "muji", "patagonia", "ikea", "lululemon", "carhartt", "supreme", "uniqlo", "nike"}
FORBIDDEN = re.compile(r"(^|/)(\.env|\.cache|\.cache_llm|private|fixtures|territory)(/|\.|$)")
KEYISH = re.compile(r"(X-Api-Key['\"]?\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}|[A-Fa-f0-9]{40,}|[A-Za-z0-9_\-]{32,}\.[A-Za-z0-9_\-]{10,})")


def publishable():
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p]


def harvest_names():
    names = set()

    def walk(o):
        if isinstance(o, dict):
            n = o.get("name") if o.get("entity_id") else None  # entities only (tags/properties also have "name")
            if isinstance(n, str) and len(n) >= 5:
                names.add(n.strip())
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for folder in (".cache", "private", "fixtures"):
        for f in (ROOT / folder).rglob("*.json"):
            try:
                walk(json.loads(f.read_text()))
            except Exception:
                pass
    allow = set(ALLOW)
    for b in (ROOT / "briefs").glob("*.json"):  # user-typed inputs (anchors, exclusions, cities) are not Qloo output
        d = json.loads(b.read_text())
        allow |= {a.casefold() for a in d.get("anchors", [])} | {d.get("city", "").casefold()}
        allow |= {t.casefold() for t in d.get("constraints", {}).get("exclude_terms", [])}
    words = set()
    wf = Path("/usr/share/dict/words")
    if wf.exists():  # single-word entity names that are ordinary English words collide with prose: skip them
        words = {w.strip().casefold() for w in wf.read_text(errors="ignore").splitlines()}
    # Short single-word names (<= 6 chars, e.g. "Local", "Catch") collide with ordinary prose: skipped, review those by eye.
    return {n for n in names if n.casefold() not in allow and not n.isdigit() and (" " in n or (len(n) > 6 and n.casefold() not in words))}


def main():
    files = publishable()
    key = os.environ.get("QLOO_API_KEY", "")
    names = harvest_names()
    findings = []
    for rel in files:
        if FORBIDDEN.search(rel):
            findings.append((rel, "forbidden path would be published"))
            continue
        p = ROOT / rel
        if not p.is_file():
            continue
        text = p.read_text(errors="ignore")
        low = text.casefold()
        if key and key in text:
            findings.append((rel, "contains the Qloo API key"))
        if KEYISH.search(text) and not rel.endswith((".lock", ".csv")):
            findings.append((rel, "key-like string"))
        for n in names:
            if re.search(r"(?<![\w])" + re.escape(n.casefold()) + r"(?![\w])", low):
                findings.append((rel, f"Qloo entity name: {n!r}"))
    print(f"scanned {len(files)} publishable files against {len(names)} harvested entity names")
    for rel, why in findings:
        print(f"FINDING {rel}: {why}")
    print("RESULT:", "CLEAN" if not findings else f"{len(findings)} finding(s)")
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()

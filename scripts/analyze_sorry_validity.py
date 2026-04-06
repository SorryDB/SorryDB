#!/usr/bin/env python3
"""
Analyze SorryDB benchmark validity to address reviewer concerns:
  1. How many sorries are meaningful standalone proof obligations?
  2. How many might require broader refactoring or auxiliary lemmas?
  3. What does strong performance concretely demonstrate?

Outputs three console tables:
  A. Goal complexity & type distribution
  B. File path classification (main proof vs. tutorial/example)
  C. Comment analysis — unsolvable/placeholder indicators in source files

Usage:
    python scripts/analyze_sorry_validity.py \
        --sorries data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json \
        --categories data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir_categories.json

    Set GITHUB_TOKEN env var for higher GitHub API rate limits.
    Pass --no-fetch to skip module C (GitHub file fetching).
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import requests


# ---------------------------------------------------------------------------
# Module A: Goal complexity & type analysis
# ---------------------------------------------------------------------------

def parse_goal(goal: str) -> dict:
    """Parse a Lean proof-state goal string into structured components."""
    # Split on turnstile: everything before "⊢ " is hypotheses
    if "\n⊢ " in goal:
        hyp_part, conclusion = goal.split("\n⊢ ", 1)
    elif goal.startswith("⊢ "):
        hyp_part = ""
        conclusion = goal[2:]
    elif "⊢ " in goal:
        hyp_part, conclusion = goal.split("⊢ ", 1)
    else:
        hyp_part = ""
        conclusion = goal

    n_hypotheses = len([l for l in hyp_part.split("\n") if l.strip()]) if hyp_part.strip() else 0

    return {
        "n_hypotheses": n_hypotheses,
        "goal_length": len(conclusion.strip()),
        "goal_type": classify_goal_type(conclusion.strip()),
        "is_trivial": is_trivially_provable(conclusion.strip()),
    }


def classify_goal_type(conclusion: str) -> str:
    """Classify the primary logical structure of a goal conclusion."""
    c = conclusion.strip()

    if not c or "failed" in c[:30].lower():
        return "failed"
    if c in ("True", "False"):
        return "trivial_prop"

    # Check for top-level quantifiers first (they wrap everything else)
    if c.startswith("∃"):
        return "existential"
    if c.startswith("∀"):
        return "universal"
    if c.startswith("¬") or c.startswith("Not "):
        return "negation"

    # Connectives (order: ↔ before →)
    if "↔" in c:
        return "iff"
    if "→" in c:
        return "implication"
    if "∧" in c and "∨" not in c:
        return "conjunction"
    if "∨" in c:
        return "disjunction"

    # Atomic propositions
    if "≠" in c:
        return "disequality"
    if " = " in c or re.search(r'[^!<>:]=(?!=)', c):
        return "equality"
    if "≤" in c or "≥" in c or " < " in c or " > " in c:
        return "ordering"

    return "other"


def is_trivially_provable(conclusion: str) -> bool:
    """Flag goals that are obviously trivial (True, a = a, failed elaboration)."""
    c = conclusion.strip()
    if c in ("True", "False"):
        return True
    if "failed" in c[:30].lower():
        return True
    # rfl-shaped: both sides of = are identical
    m = re.match(r'^(.+?)\s*=\s*(.+)$', c)
    if m and m.group(1).strip() == m.group(2).strip():
        return True
    return False


def hyp_bucket(n: int) -> str:
    if n <= 3:
        return "0–3"
    if n <= 10:
        return "4–10"
    if n <= 20:
        return "11–20"
    return ">20"


# ---------------------------------------------------------------------------
# Module B: File path classification
# ---------------------------------------------------------------------------

# Patterns that suggest tutorial/example/scaffold files rather than real proofs
TUTORIAL_PATH_PATTERNS = re.compile(
    r'(example|tutorial|exercise|game|demo|test|workshop|sample|scratch)',
    re.IGNORECASE,
)


def classify_path(path: str) -> str:
    """Classify a file path as tutorial/example or main proof."""
    segments = re.split(r'[/\\]', path)
    for seg in segments:
        if TUTORIAL_PATH_PATTERNS.search(seg):
            return "tutorial/example"
    return "main proof"


# ---------------------------------------------------------------------------
# Module C: Comment analysis (GitHub file fetch)
# ---------------------------------------------------------------------------

# Patterns in surrounding comments that suggest the sorry is NOT a genuine
# standalone proof obligation (placeholder, known-false, needs refactoring, etc.)
UNSOLVABLE_COMMENT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r'--\s*(TODO|FIXME|HACK|WIP|XXX)\b',
        r'--[^\n]*\bplaceholder\b',
        r'--[^\n]*\badmit\b',
        r'--[^\n]*\brefactor\b',
        r'--[^\n]*\b(false|impossible|cannot|can\'t)\b',
        r'--[^\n]*\b(broken|skip|incomplete|unfinished)\b',
        r'--[^\n]*\b(awaiting|waiting for)\b',
        r'--[^\n]*\bneed[s]? (auxiliary|lemma|helper)\b',
        r'--[^\n]*\bnot (yet )?prov(ed?|en)\b',
        r'--[^\n]*\bnot (yet )?solved?\b',
    ]
]

CONTEXT_WINDOW = 10  # lines above and below the sorry


def check_surrounding_comments(lines: list[str], sorry_line_1indexed: int) -> tuple[bool, Optional[str]]:
    """
    Search ±CONTEXT_WINDOW lines around sorry_line for unsolvable indicators.
    Returns (flagged, first_matching_line).
    """
    lo = max(0, sorry_line_1indexed - 1 - CONTEXT_WINDOW)
    hi = min(len(lines), sorry_line_1indexed + CONTEXT_WINDOW)
    for line in lines[lo:hi]:
        for pat in UNSOLVABLE_COMMENT_PATTERNS:
            if pat.search(line):
                return True, line.strip()
    return False, None


def build_raw_url(remote: str, commit: str, path: str) -> Optional[str]:
    """Convert GitHub repo URL + commit + relative path to raw content URL."""
    m = re.match(r'https://github\.com/([^/]+/[^/]+?)(?:\.git)?$', remote.rstrip("/"))
    if not m:
        return None
    return f"https://raw.githubusercontent.com/{m.group(1)}/{commit}/{path}"


def fetch_file(url: str, token: Optional[str], cache: dict) -> Optional[list[str]]:
    """Fetch file lines from GitHub raw content URL, caching results."""
    if url in cache:
        return cache[url]

    headers = {"User-Agent": "SorryDB-analysis/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        r = requests.get(url, headers=headers, timeout=20)
        result = r.text.splitlines() if r.status_code == 200 else None
    except Exception:
        result = None

    cache[url] = result
    return result


# ---------------------------------------------------------------------------
# Printing helpers
# ---------------------------------------------------------------------------

def print_table(title: str, rows: list[tuple], headers: list[str]) -> None:
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
    sep = "  " + "  ".join("-" * w for w in col_widths)

    print(f"\n{'═'*62}")
    print(f"  {title}")
    print(f"{'═'*62}")
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze SorryDB benchmark validity")
    parser.add_argument("--sorries", required=True, type=Path, help="Path to sorry database JSON")
    parser.add_argument("--categories", required=True, type=Path, help="Path to repo categories JSON")
    parser.add_argument("--no-fetch", action="store_true", help="Skip GitHub file fetching (module C)")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")

    # --- Load data ---
    with open(args.sorries) as f:
        data = json.load(f)
    sorries = data["sorries"]
    print(f"Loaded {len(sorries)} sorry instances")

    with open(args.categories) as f:
        cat_data = json.load(f)
    # Map "Owner/Repo" → category string
    cat_map = {e["name"]: e["category"] for e in cat_data["categories"]}
    print(f"Loaded {len(cat_map)} repo categories")

    # --- Enrich each sorry with computed features ---
    enriched = []
    for s in sorries:
        remote = s["repo"]["remote"].rstrip("/")
        m = re.match(r'https://github\.com/([^/]+/[^/]+?)(?:\.git)?$', remote)
        repo_name = m.group(1) if m else None
        category = cat_map.get(repo_name, "unknown")
        path = s["location"]["path"]

        goal_features = parse_goal(s["debug_info"].get("goal", ""))

        enriched.append({
            "repo_name": repo_name,
            "remote": remote,
            "commit": s["repo"]["commit"],
            "path": path,
            "start_line": s["location"]["start_line"],
            "category": category,
            "path_type": classify_path(path),
            **goal_features,
        })

    total = len(enriched)

    # -----------------------------------------------------------------------
    # Table A: Goal complexity & type distribution
    # -----------------------------------------------------------------------

    hyp_dist = Counter(hyp_bucket(r["n_hypotheses"]) for r in enriched)
    ordered_buckets = ["0–3", "4–10", "11–20", ">20"]
    print_table(
        "A1. Hypothesis Count Distribution",
        [(b, hyp_dist[b], f"{100 * hyp_dist[b] / total:.1f}%") for b in ordered_buckets],
        ["Hypotheses", "Count", "Percent"],
    )

    type_dist = Counter(r["goal_type"] for r in enriched)
    print_table(
        "A2. Goal Type Distribution",
        [(t, c, f"{100 * c / total:.1f}%") for t, c in type_dist.most_common()],
        ["Goal Type", "Count", "Percent"],
    )

    n_trivial = sum(1 for r in enriched if r["is_trivial"])
    n_nontrivial = total - n_trivial
    print(f"\n  Trivial goals (⊢ True / ⊢ x=x / failed): {n_trivial} ({100*n_trivial/total:.1f}%)")
    print(f"  Non-trivial goals:                         {n_nontrivial} ({100*n_nontrivial/total:.1f}%)")

    # -----------------------------------------------------------------------
    # Table B: File path classification × category
    # -----------------------------------------------------------------------

    cats = sorted(set(r["category"] for r in enriched))
    cross: Counter = Counter((r["category"], r["path_type"]) for r in enriched)

    rows_b = []
    for cat in cats:
        main_n = cross.get((cat, "main proof"), 0)
        tut_n = cross.get((cat, "tutorial/example"), 0)
        sub_total = main_n + tut_n
        pct = f"{100 * main_n / sub_total:.0f}%" if sub_total else "—"
        rows_b.append((cat, main_n, tut_n, sub_total, pct))

    total_main = sum(r[1] for r in rows_b)
    total_tut = sum(r[2] for r in rows_b)
    rows_b.append(("TOTAL", total_main, total_tut, total, f"{100 * total_main / total:.0f}%"))

    print_table(
        "B. File Path Classification by Category",
        rows_b,
        ["Category", "Main Proof", "Tutorial/Example", "Total", "% Main Proof"],
    )

    # -----------------------------------------------------------------------
    # Module C: Comment analysis via GitHub file fetch
    # -----------------------------------------------------------------------

    if args.no_fetch:
        print("\n[Module C skipped — run without --no-fetch to enable GitHub comment analysis]")
        return

    print(f"\n{'═'*62}")
    print("  C. Comment Analysis (fetching source files from GitHub)")
    print(f"{'═'*62}")

    unique_files = {
        (r["remote"], r["commit"], r["path"])
        for r in enriched
        if build_raw_url(r["remote"], r["commit"], r["path"]) is not None
    }
    print(f"  {len(unique_files)} unique source files to fetch...")

    file_cache: dict[str, Optional[list[str]]] = {}
    fetch_count = 0

    for remote, commit, path in unique_files:
        url = build_raw_url(remote, commit, path)
        if url in file_cache:
            continue
        fetch_file(url, token, file_cache)
        fetch_count += 1
        if fetch_count % 50 == 0:
            print(f"  ... {fetch_count}/{len(unique_files)} files fetched")
        time.sleep(0.05)  # be polite to GitHub

    n_fetched_ok = sum(1 for v in file_cache.values() if v is not None)
    print(f"  Successfully fetched: {n_fetched_ok}/{len(unique_files)} files\n")

    # Classify each sorry
    c_results = []  # (enriched_row, status, match_line)
    for r in enriched:
        url = build_raw_url(r["remote"], r["commit"], r["path"])
        if url is None:
            c_results.append((r, "url_error", None))
            continue
        lines = file_cache.get(url)
        if lines is None:
            c_results.append((r, "fetch_failed", None))
            continue
        flagged, match_line = check_surrounding_comments(lines, r["start_line"])
        c_results.append((r, "flagged" if flagged else "clean", match_line))

    checked = [(r, s, m) for r, s, m in c_results if s in ("clean", "flagged")]
    n_checked = len(checked)
    n_flagged = sum(1 for _, s, _ in checked if s == "flagged")
    n_clean = n_checked - n_flagged
    n_errors = total - n_checked

    print_table(
        "C1. Unsolvable Comment Indicators (all sorries)",
        [
            ("Clean — no concerning comments", n_clean, f"{100*n_clean/n_checked:.1f}%" if n_checked else "—"),
            ("Flagged — has TODO/placeholder/etc.", n_flagged, f"{100*n_flagged/n_checked:.1f}%" if n_checked else "—"),
            ("Could not fetch source file", n_errors, ""),
        ],
        ["Category", "Count", "% of checked"],
    )

    # Per-category breakdown
    cat_clean: Counter = Counter()
    cat_flagged: Counter = Counter()
    for r, status, _ in checked:
        cat = r["category"]
        if status == "flagged":
            cat_flagged[cat] += 1
        else:
            cat_clean[cat] += 1

    rows_c = []
    for cat in sorted(set(cat_clean) | set(cat_flagged)):
        cl = cat_clean.get(cat, 0)
        fl = cat_flagged.get(cat, 0)
        tot = cl + fl
        rows_c.append((cat, cl, fl, tot, f"{100*cl/tot:.0f}%" if tot else "—"))
    rows_c.append(("TOTAL", n_clean, n_flagged, n_checked, f"{100*n_clean/n_checked:.0f}%" if n_checked else "—"))

    print_table(
        "C2. Comment Analysis by Category",
        rows_c,
        ["Category", "Clean", "Flagged", "Total", "% Clean"],
    )

    # Show the most common flagged patterns
    match_lines = [m for _, s, m in checked if s == "flagged" and m]
    if match_lines:
        pattern_counts: Counter = Counter()
        for line in match_lines:
            for pat in UNSOLVABLE_COMMENT_PATTERNS:
                m = pat.search(line)
                if m:
                    pattern_counts[m.group(0).strip()] += 1
                    break

        print("\n  Most common patterns in flagged comments:")
        for pattern, count in pattern_counts.most_common(10):
            print(f"    {count:4d}x  {pattern!r}")

        print("\n  Sample flagged comment lines:")
        seen = set()
        shown = 0
        for line in match_lines:
            if line not in seen and shown < 8:
                print(f"    {line[:100]}")
                seen.add(line)
                shown += 1


if __name__ == "__main__":
    main()

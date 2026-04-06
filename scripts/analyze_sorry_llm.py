#!/usr/bin/env python3
"""
LLM-based analysis of SorryDB sorry instances to address reviewer concerns.

For each sorry the model receives:
  - the full proof-state goal (hypotheses + conclusion)
  - ±20 lines of surrounding Lean source code (including comments)

And returns structured judgements on:
  - validity: is this a genuine standalone proof obligation?
  - difficulty: estimated difficulty for an automated prover
  - unsolvable_indicator: does context suggest this can't/won't be proved?
  - reasoning: brief explanation

Runs up to --concurrency parallel async API calls.
Results are cached to --cache so the script is safe to re-run.

Usage:
    python scripts/analyze_sorry_llm.py \\
        --sorries  data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json \\
        --categories data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir_categories.json \\
        --output   analysis_sorry_llm.md \\
        --cache    analysis_sorry_llm_cache.json \\
        --model    claude-haiku-4-5-20251001 \\
        --concurrency 20

Set ANTHROPIC_API_KEY (and optionally GITHUB_TOKEN) in the environment or .env file.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import anthropic
import dotenv
import requests

dotenv.load_dotenv()

# ---------------------------------------------------------------------------
# Rubric — injected verbatim into the prompt so the model knows what we expect
# ---------------------------------------------------------------------------

RUBRIC = """
You are analysing a Lean 4 proof obligation (a `sorry`) from a real GitHub repository.
You are given the *proof state* at the sorry (hypotheses + goal) and the surrounding
source lines for context.

Classify the sorry using EXACTLY the following fields:

validity (choose one):
  - "standalone"          : A clear, self-contained proof obligation. Given the local
                            context, an automated prover could plausibly attempt it
                            without rewriting surrounding code.
  - "needs_auxiliary"     : Likely solvable in principle, but probably requires
                            introducing one or more helper lemmas not yet present.
  - "needs_refactoring"   : The surrounding proof structure would need to change
                            before this sorry can be filled (e.g. wrong induction
                            hypothesis, wrong generalisation, wrong split).
  - "placeholder_false"   : Evidence suggests the goal is known-false, intentionally
                            left open, or is a structural placeholder (e.g. comment
                            says TODO/WIP/impossible, or the goal is `False`).
  - "trivial"             : Very likely solvable by a single basic tactic
                            (rfl, simp, decide, norm_num, tauto, omega, …).
  - "unclear"             : Not enough context to judge.

difficulty (choose one):
  - "trivial"   : One basic tactic suffices.
  - "easy"      : A few standard tactics or a short tactic sequence.
  - "medium"    : Requires non-trivial reasoning or library search.
  - "hard"      : Requires creative proof strategy, novel lemmas, or deep library knowledge.

unsolvable_indicator (bool):
  True if ANY of the following: comment says TODO/placeholder/WIP/impossible/false nearby,
  goal is `False` or `True`, validity is placeholder_false or needs_refactoring.

key_observation (string, ≤ 20 words):
  The single most important thing about this sorry for a reviewer wondering whether
  the benchmark is meaningful.
""".strip()

ANALYSIS_TOOL = {
    "name": "classify_sorry",
    "description": "Return a structured classification of the Lean sorry instance.",
    "input_schema": {
        "type": "object",
        "properties": {
            "validity": {
                "type": "string",
                "enum": ["standalone", "needs_auxiliary", "needs_refactoring",
                         "placeholder_false", "trivial", "unclear"],
            },
            "difficulty": {
                "type": "string",
                "enum": ["trivial", "easy", "medium", "hard"],
            },
            "unsolvable_indicator": {"type": "boolean"},
            "reasoning": {"type": "string", "description": "2-3 sentence explanation."},
            "key_observation": {"type": "string", "description": "≤ 20 words."},
        },
        "required": ["validity", "difficulty", "unsolvable_indicator", "reasoning", "key_observation"],
    },
}

CONTEXT_WINDOW = 20  # lines above and below the sorry


# ---------------------------------------------------------------------------
# GitHub fetching (same approach as analyze_sorry_validity.py)
# ---------------------------------------------------------------------------

def build_raw_url(remote: str, commit: str, path: str) -> Optional[str]:
    m = re.match(r'https://github\.com/([^/]+/[^/]+?)(?:\.git)?$', remote.rstrip("/"))
    return f"https://raw.githubusercontent.com/{m.group(1)}/{commit}/{path}" if m else None


def fetch_source_files(sorries: list[dict], token: Optional[str]) -> dict[str, Optional[list[str]]]:
    """Fetch all unique source files synchronously (with caching)."""
    cache: dict[str, Optional[list[str]]] = {}
    unique = {
        build_raw_url(s["repo"]["remote"], s["repo"]["commit"], s["location"]["path"])
        for s in sorries
        if build_raw_url(s["repo"]["remote"], s["repo"]["commit"], s["location"]["path"])
    }
    print(f"  Fetching {len(unique)} unique source files from GitHub...")

    headers = {"User-Agent": "SorryDB-analysis/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"

    for i, url in enumerate(sorted(unique)):
        if url in cache:
            continue
        try:
            r = requests.get(url, headers=headers, timeout=20)
            cache[url] = r.text.splitlines() if r.status_code == 200 else None
        except Exception:
            cache[url] = None
        time.sleep(0.03)
        if (i + 1) % 100 == 0:
            print(f"    ... {i+1}/{len(unique)}")

    ok = sum(1 for v in cache.values() if v is not None)
    print(f"  Fetched {ok}/{len(unique)} files successfully.\n")
    return cache


def get_context_lines(lines: list[str], sorry_line: int) -> str:
    """Extract ±CONTEXT_WINDOW lines around sorry_line (1-indexed)."""
    lo = max(0, sorry_line - 1 - CONTEXT_WINDOW)
    hi = min(len(lines), sorry_line + CONTEXT_WINDOW)
    numbered = [f"{lo+1+i:4d} | {line}" for i, line in enumerate(lines[lo:hi])]
    return "\n".join(numbered)


# ---------------------------------------------------------------------------
# Async LLM analysis
# ---------------------------------------------------------------------------

async def analyse_sorry(
    client: anthropic.AsyncAnthropic,
    sorry_id: str,
    goal: str,
    context_lines: str,
    model: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Call the LLM for one sorry. Returns parsed tool-use result."""
    user_content = f"""{RUBRIC}

---

**Proof state (goal):**
```
{goal}
```

**Surrounding source (±{CONTEXT_WINDOW} lines, line numbers shown):**
```lean
{context_lines if context_lines else "(source not available)"}
```

Call `classify_sorry` with your analysis.
"""
    async with semaphore:
        for attempt in range(3):
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=512,
                    tools=[ANALYSIS_TOOL],
                    tool_choice={"type": "tool", "name": "classify_sorry"},
                    messages=[{"role": "user", "content": user_content}],
                )
                # Extract tool-use block
                for block in response.content:
                    if block.type == "tool_use" and block.name == "classify_sorry":
                        return {"id": sorry_id, "status": "ok", **block.input}
                return {"id": sorry_id, "status": "error", "error": "no tool_use block"}
            except anthropic.RateLimitError:
                await asyncio.sleep(5 * (attempt + 1))
            except Exception as e:
                if attempt == 2:
                    return {"id": sorry_id, "status": "error", "error": str(e)}
                await asyncio.sleep(2)
    return {"id": sorry_id, "status": "error", "error": "max retries exceeded"}


# ---------------------------------------------------------------------------
# Printing + markdown helpers
# ---------------------------------------------------------------------------

def fmt_table_md(headers: list[str], rows: list[tuple]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def print_console_table(title: str, headers: list[str], rows: list[tuple]) -> None:
    col_w = [len(h) for h in headers]
    for row in rows:
        for i, c in enumerate(row):
            col_w[i] = max(col_w[i], len(str(c)))
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_w)
    sep = "  " + "  ".join("-" * w for w in col_w)
    print(f"\n{'═'*62}\n  {title}\n{'═'*62}")
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> None:
    token = os.environ.get("GITHUB_TOKEN")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set. Add it to .env or the environment.")

    # --- Load data ---
    with open(args.sorries) as f:
        data = json.load(f)
    sorries = data["sorries"]
    print(f"Loaded {len(sorries)} sorry instances")

    with open(args.categories) as f:
        cat_data = json.load(f)
    cat_map = {e["name"]: e["category"] for e in cat_data["categories"]}

    def repo_name(remote: str) -> Optional[str]:
        m = re.match(r'https://github\.com/([^/]+/[^/]+?)(?:\.git)?$', remote.rstrip("/"))
        return m.group(1) if m else None

    # --- Load existing cache ---
    cache_path = Path(args.cache)
    result_cache: dict[str, dict] = {}
    if cache_path.exists():
        with open(cache_path) as f:
            result_cache = json.load(f)
        print(f"Loaded {len(result_cache)} cached results from {cache_path}")

    # --- Fetch source files ---
    print("\nFetching source files...")
    file_cache = fetch_source_files(sorries, token)

    # --- Build work list ---
    if args.limit:
        sorries = sorries[:args.limit]

    work_items = []
    for s in sorries:
        sid = s["id"]
        if sid in result_cache:
            continue  # already done

        remote = s["repo"]["remote"].rstrip("/")
        url = build_raw_url(remote, s["repo"]["commit"], s["location"]["path"])
        lines = file_cache.get(url) if url else None
        ctx = get_context_lines(lines, s["location"]["start_line"]) if lines else ""

        work_items.append({
            "id": sid,
            "sorry": s,
            "goal": s["debug_info"].get("goal", ""),
            "context": ctx,
            "repo_name": repo_name(remote),
            "category": cat_map.get(repo_name(remote), "unknown"),
        })

    print(f"\n{len(work_items)} sorries to analyse ({len(result_cache)} already cached).")

    if work_items:
        print(f"Using model: {args.model}  |  concurrency: {args.concurrency}")
        client = anthropic.AsyncAnthropic(api_key=api_key)
        semaphore = asyncio.Semaphore(args.concurrency)

        tasks = [
            analyse_sorry(client, item["id"], item["goal"], item["context"],
                          args.model, semaphore)
            for item in work_items
        ]

        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            result_cache[result["id"]] = result
            completed += 1
            if completed % 50 == 0 or completed == len(tasks):
                print(f"  ... {completed}/{len(tasks)} done", end="\r")
                # Save cache incrementally
                with open(cache_path, "w") as f:
                    json.dump(result_cache, f)

        print(f"\nAll {len(tasks)} LLM calls complete. Cache saved to {cache_path}")

    # --- Merge results with sorry metadata ---
    id_to_meta = {}
    for s in sorries:
        remote = s["repo"]["remote"].rstrip("/")
        rn = repo_name(remote)
        id_to_meta[s["id"]] = {
            "category": cat_map.get(rn, "unknown"),
            "path": s["location"]["path"],
            "goal": s["debug_info"].get("goal", ""),
            "url": s["debug_info"].get("url", ""),
        }

    analyses = []
    for sid, res in result_cache.items():
        if res.get("status") != "ok":
            continue
        meta = id_to_meta.get(sid, {})
        analyses.append({**res, **meta})

    total = len(analyses)
    print(f"\n{total} successfully analysed sorries.\n")

    # ---------------------------------------------------------------------------
    # Compute summary statistics
    # ---------------------------------------------------------------------------

    validity_counts = Counter(a["validity"] for a in analyses)
    difficulty_counts = Counter(a["difficulty"] for a in analyses)
    n_unsolvable = sum(1 for a in analyses if a.get("unsolvable_indicator"))
    n_soluble = total - n_unsolvable

    # Per-category breakdowns
    cats = sorted(set(a["category"] for a in analyses))

    val_by_cat: dict[str, Counter] = {c: Counter() for c in cats}
    diff_by_cat: dict[str, Counter] = {c: Counter() for c in cats}
    for a in analyses:
        val_by_cat[a["category"]][a["validity"]] += 1
        diff_by_cat[a["category"]][a["difficulty"]] += 1

    # ---------------------------------------------------------------------------
    # Console output
    # ---------------------------------------------------------------------------

    VALIDITY_ORDER = ["standalone", "needs_auxiliary", "needs_refactoring",
                      "placeholder_false", "trivial", "unclear"]
    DIFFICULTY_ORDER = ["trivial", "easy", "medium", "hard"]

    print_console_table(
        "Validity Distribution (all sorries)",
        ["Validity", "Count", "Percent"],
        [(v, validity_counts[v], f"{100*validity_counts[v]/total:.1f}%") for v in VALIDITY_ORDER],
    )

    print_console_table(
        "Difficulty Distribution (all sorries)",
        ["Difficulty", "Count", "Percent"],
        [(d, difficulty_counts[d], f"{100*difficulty_counts[d]/total:.1f}%") for d in DIFFICULTY_ORDER],
    )

    soluble_pct = f"{100*n_soluble/total:.1f}%"
    print(f"\n  Sorries with NO unsolvable indicator: {n_soluble} / {total} ({soluble_pct})")
    print(f"  Sorries WITH unsolvable indicator:    {n_unsolvable} / {total} ({100*n_unsolvable/total:.1f}%)")

    # Per-category validity table (standalone + trivial = "likely solvable")
    rows_cat = []
    for cat in cats:
        vc = val_by_cat[cat]
        ct = sum(vc.values())
        standalone = vc["standalone"] + vc["trivial"]
        rows_cat.append((cat, ct, standalone, f"{100*standalone/ct:.0f}%" if ct else "—",
                         vc["needs_auxiliary"], vc["needs_refactoring"], vc["placeholder_false"]))
    rows_cat.append((
        "TOTAL", total,
        validity_counts["standalone"] + validity_counts["trivial"],
        f"{100*(validity_counts['standalone']+validity_counts['trivial'])/total:.0f}%",
        validity_counts["needs_auxiliary"],
        validity_counts["needs_refactoring"],
        validity_counts["placeholder_false"],
    ))

    print_console_table(
        "Validity by Category",
        ["Category", "Total", "Standalone/Trivial", "% Solo", "NeedsAux", "NeedsRefactor", "Placeholder"],
        rows_cat,
    )

    # ---------------------------------------------------------------------------
    # Markdown report
    # ---------------------------------------------------------------------------

    # Sample sorries per validity class (up to 3 each)
    samples: dict[str, list] = {v: [] for v in VALIDITY_ORDER}
    for a in analyses:
        v = a["validity"]
        if len(samples[v]) < 3:
            samples[v].append(a)

    md_lines = [
        "# SorryDB Benchmark — LLM Validity Analysis",
        "",
        f"**Model:** `{args.model}`  |  **Sorries analysed:** {total}",
        "",
        "This report addresses the reviewer's concern about whether sorry instances",
        "represent meaningful standalone proof obligations.",
        "",
        "---",
        "",
        "## 1. Validity Distribution",
        "",
        fmt_table_md(
            ["Validity", "Count", "Percent", "Description"],
            [
                ("standalone", validity_counts["standalone"],
                 f"{100*validity_counts['standalone']/total:.1f}%",
                 "Clear self-contained proof obligation"),
                ("trivial", validity_counts["trivial"],
                 f"{100*validity_counts['trivial']/total:.1f}%",
                 "Likely one basic tactic (rfl, simp, decide, …)"),
                ("needs_auxiliary", validity_counts["needs_auxiliary"],
                 f"{100*validity_counts['needs_auxiliary']/total:.1f}%",
                 "Solvable but likely needs a helper lemma"),
                ("needs_refactoring", validity_counts["needs_refactoring"],
                 f"{100*validity_counts['needs_refactoring']/total:.1f}%",
                 "Proof structure needs to change first"),
                ("placeholder_false", validity_counts["placeholder_false"],
                 f"{100*validity_counts['placeholder_false']/total:.1f}%",
                 "Known-false or intentional placeholder"),
                ("unclear", validity_counts["unclear"],
                 f"{100*validity_counts['unclear']/total:.1f}%",
                 "Insufficient context to judge"),
            ],
        ),
        "",
        f"**{n_soluble} / {total} ({soluble_pct}) sorries have no unsolvable indicator** — "
        "i.e. the LLM found no evidence in the goal or surrounding source that would prevent "
        "a prover from attempting them.",
        "",
        "---",
        "",
        "## 2. Difficulty Distribution",
        "",
        fmt_table_md(
            ["Difficulty", "Count", "Percent"],
            [(d, difficulty_counts[d], f"{100*difficulty_counts[d]/total:.1f}%")
             for d in DIFFICULTY_ORDER],
        ),
        "",
        "---",
        "",
        "## 3. Validity by Repository Category",
        "",
        fmt_table_md(
            ["Category", "Total", "Standalone/Trivial", "% Solo", "Needs Auxiliary", "Needs Refactor", "Placeholder"],
            rows_cat,
        ),
        "",
        "---",
        "",
        "## 4. Sample Sorries by Validity Class",
        "",
    ]

    for v in VALIDITY_ORDER:
        if not samples[v]:
            continue
        md_lines += [f"### `{v}`", ""]
        for a in samples[v]:
            goal_short = a["goal"][:300].replace("\n", "  \n  ") + ("…" if len(a["goal"]) > 300 else "")
            md_lines += [
                f"**Goal:**",
                f"```",
                goal_short,
                f"```",
                f"**Key observation:** {a.get('key_observation', '')}",
                f"**Reasoning:** {a.get('reasoning', '')}",
                f"**URL:** {a.get('url', '')}",
                "",
            ]

    md_lines += [
        "---",
        "",
        "## 5. Key Takeaways for Reviewer Response",
        "",
        f"- **{validity_counts['standalone']} ({100*validity_counts['standalone']/total:.0f}%) sorries** "
        "are classified as *standalone* proof obligations — clear mathematical statements "
        "with sufficient local context for an automated prover to attempt.",
        "",
        f"- **{validity_counts['trivial']} ({100*validity_counts['trivial']/total:.0f}%) sorries** "
        "are flagged as *trivial* (e.g. `rfl`, `simp`, `decide`). These serve as easy benchmarks "
        "that calibrate what a basic tactic solver can handle.",
        "",
        f"- **Only {validity_counts['placeholder_false']} ({100*validity_counts['placeholder_false']/total:.1f}%) "
        "sorries** appear to be known-false or intentional placeholders, confirming the benchmark "
        "is not dominated by unsolvable tasks.",
        "",
        f"- **{validity_counts['needs_auxiliary']} ({100*validity_counts['needs_auxiliary']/total:.1f}%) sorries** "
        "likely require auxiliary lemmas — this represents a meaningful sub-task for systems "
        "that can decompose proof obligations.",
        "",
        f"- **{n_unsolvable} ({100*n_unsolvable/total:.1f}%) sorries** have some unsolvable indicator. "
        f"Even if excluded, the remaining **{n_soluble}** sorries form a challenging and "
        "diverse benchmark.",
        "",
    ]

    output_path = Path(args.output)
    output_path.write_text("\n".join(md_lines))
    print(f"\nMarkdown report written to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-based sorry validity analysis")
    parser.add_argument("--sorries", required=True, type=Path)
    parser.add_argument("--categories", required=True, type=Path)
    parser.add_argument("--output", default="analysis_sorry_llm.md", type=Path,
                        help="Output markdown report path")
    parser.add_argument("--cache", default="analysis_sorry_llm_cache.json", type=Path,
                        help="JSON cache for LLM results (safe to re-run)")
    parser.add_argument("--model", default="claude-haiku-4-5-20251001",
                        help="Anthropic model ID to use")
    parser.add_argument("--concurrency", type=int, default=20,
                        help="Max parallel API calls")
    parser.add_argument("--limit", type=int, default=None,
                        help="Analyse only first N sorries (for testing)")
    args = parser.parse_args()

    if args.limit:
        print(f"[--limit {args.limit}] Will analyse only the first {args.limit} sorries.")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()

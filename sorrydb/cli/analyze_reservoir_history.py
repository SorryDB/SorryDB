#!/usr/bin/env python3
"""Analyze all Lean reservoir repositories to find historical sorries using git pickaxe."""

import argparse
import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sorrydb.database.reservoir import clone_reservoir, process_repositories

logger = logging.getLogger(__name__)


def get_repo_name_from_url(repo_url: str) -> str:
    """Extract repo name from git URL."""
    # Handle URLs like https://github.com/owner/repo.git or git@github.com:owner/repo.git
    name = repo_url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def clone_or_fetch_repo(repo_url: str, clone_dir: Path) -> Path | None:
    """Clone a repo or fetch updates if it already exists. Returns repo path or None on failure."""
    repo_name = get_repo_name_from_url(repo_url)
    repo_path = clone_dir / repo_name

    # Disable git credential prompts - fail immediately if auth required
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    try:
        if repo_path.exists():
            logger.info(f"Fetching updates for {repo_name}")
            subprocess.run(
                ["git", "fetch", "--all"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                env=env,
            )
        else:
            logger.info(f"Cloning {repo_url}")
            subprocess.run(
                ["git", "clone", repo_url, str(repo_path)],
                check=True,
                capture_output=True,
                env=env,
            )
        return repo_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to clone/fetch {repo_url}: {e.stderr.decode() if e.stderr else e}")
        return None


def count_sorries_in_line(line: str) -> int:
    """
    Count sorry tactic occurrences in a line, ignoring comments and strings.

    Handles:
    - Multi-sorry lines: `rw [sorry, sorry, sorry]` → 3
    - Comments: `-- TODO: sorry` → 0
    - Strings: `"sorry"` → 0
    - Identifiers: `sorry_lemma` → 0 (word boundary)
    """
    # Remove comment portion (everything after --)
    comment_idx = line.find("--")
    if comment_idx != -1:
        line = line[:comment_idx]

    # Remove string literals (simple handling - doesn't handle escaped quotes)
    line = re.sub(r'"[^"]*"', "", line)

    # Count word-boundary "sorry" occurrences
    return len(re.findall(r"\bsorry\b", line))


def parse_sorry_diff(output: str, repo_url: str) -> list[dict]:
    """Parse git log -p output to count sorry adds/removes per commit."""
    commits = []
    current = None

    for line in output.split("\n"):
        if line.startswith("COMMIT|"):
            # Save previous commit if it had sorry changes
            if current and (current["added"] > 0 or current["removed"] > 0):
                current["net"] = current["added"] - current["removed"]
                commits.append(current)
            parts = line.split("|")
            if len(parts) >= 3:
                current = {
                    "repo": repo_url,
                    "commit": parts[1],
                    "date": parts[2],
                    "added": 0,
                    "removed": 0,
                }
        elif current:
            # Count sorry occurrences in added lines (exclude +++ header)
            if line.startswith("+") and not line.startswith("+++"):
                current["added"] += count_sorries_in_line(line[1:])  # Skip the leading +
            # Count sorry occurrences in removed lines (exclude --- header)
            elif line.startswith("-") and not line.startswith("---"):
                current["removed"] += count_sorries_in_line(line[1:])  # Skip the leading -

    # Don't forget the last commit
    if current and (current["added"] > 0 or current["removed"] > 0):
        current["net"] = current["added"] - current["removed"]
        commits.append(current)

    return commits


def analyze_repo_sorry_history(repo_url: str, repo_path: Path) -> list[dict]:
    """
    Analyze a repo for historical sorries using git pickaxe with diff parsing.

    Returns a list of dicts with: repo, commit, date, added, removed, net
    """
    try:
        # Run git log -S with -p to get diffs for counting adds/removes
        # Note: We don't use --all to avoid counting unmerged branches
        result = subprocess.run(
            [
                "git", "log",
                "-S", "sorry",
                "-p",
                "--format=COMMIT|%H|%aI",
                "--", "*.lean"
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        output = result.stdout
        if not output.strip():
            return []

        return parse_sorry_diff(output, repo_url)

    except subprocess.CalledProcessError as e:
        logger.error(f"Git log failed for {repo_path}: {e.stderr if e.stderr else e}")
    except Exception as e:
        logger.error(f"Error analyzing {repo_path}: {e}")

    return []


def count_sorries_at_commit(repo_path: Path, commit_sha: str) -> int:
    """
    Checkout a commit and count sorries in all .lean files.

    This is slower but 100% accurate - no diff parsing errors.
    """
    # Save current HEAD
    original = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    try:
        # Checkout target commit (quietly, no submodules)
        subprocess.run(
            ["git", "checkout", "--quiet", commit_sha],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Count sorries in all .lean files
        total = 0
        for lean_file in repo_path.rglob("*.lean"):
            # Skip .lake directory (build artifacts)
            if ".lake" in lean_file.parts:
                continue
            try:
                with open(lean_file, encoding="utf-8") as f:
                    for line in f:
                        total += count_sorries_in_line(line)
            except (UnicodeDecodeError, IOError):
                pass  # Skip binary/unreadable files

        return total

    finally:
        # Restore original HEAD
        subprocess.run(
            ["git", "checkout", "--quiet", original],
            cwd=repo_path,
            capture_output=True,
        )


def analyze_repo_accurate(repo_url: str, repo_path: Path) -> list[dict]:
    """
    Analyze repo with accurate sorry counts at each change commit.

    Uses git checkout to read actual file contents - slower but 100% accurate.
    Returns list of dicts with: repo, commit, date, sorry_count (absolute count).
    """
    try:
        # Get commits where sorry count changed
        result = subprocess.run(
            ["git", "log", "-S", "sorry", "--format=%H|%aI", "--", "*.lean"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        if not result.stdout.strip():
            return []

        commits = []
        lines = [l for l in result.stdout.strip().split("\n") if "|" in l]

        for i, line in enumerate(lines):
            sha, date = line.split("|", 1)
            logger.debug(f"  [{i+1}/{len(lines)}] Counting sorries at {sha[:8]}")

            # Count sorries at this commit
            sorry_count = count_sorries_at_commit(repo_path, sha)

            commits.append({
                "repo": repo_url,
                "commit": sha,
                "date": date,
                "sorry_count": sorry_count,
            })

        # Sort chronologically (git log returns newest first)
        commits.sort(key=lambda c: c["date"])

        return commits

    except subprocess.CalledProcessError as e:
        logger.error(f"Git log failed for {repo_path}: {e.stderr if e.stderr else e}")
    except Exception as e:
        logger.error(f"Error analyzing {repo_path}: {e}")

    return []


def analyze_all_reservoir_sorries(
    updated_since: datetime,
    minimum_stars: int,
    output_path: str,
    clone_dir: Path,
    accurate: bool = False,
) -> None:
    """
    Analyze all reservoir repos for historical sorries.

    Args:
        updated_since: Only include repos updated since this date
        minimum_stars: Minimum number of GitHub stars
        output_path: Path to write output JSON
        clone_dir: Directory to clone repos into (persistent)
        accurate: If True, use accurate mode (checkout + count) instead of diff parsing
    """
    # Ensure clone directory exists
    clone_dir.mkdir(parents=True, exist_ok=True)

    # Get list of repos from reservoir
    logger.info("Fetching reservoir repo list...")
    with tempfile.TemporaryDirectory() as reservoir_dir:
        clone_reservoir(reservoir_dir)
        repos = process_repositories(updated_since, minimum_stars, reservoir_dir)

    logger.info(f"Found {len(repos)} repos to analyze")

    all_commits = []
    repos_analyzed = 0
    repos_failed = 0

    for i, repo_info in enumerate(repos, 1):
        repo_url = repo_info["remote"]
        logger.info(f"[{i}/{len(repos)}] Processing {repo_url}")

        # Clone or fetch the repo
        repo_path = clone_or_fetch_repo(repo_url, clone_dir)
        if repo_path is None:
            repos_failed += 1
            continue

        # Analyze for sorries (use accurate mode if requested)
        if accurate:
            commits = analyze_repo_accurate(repo_url, repo_path)
            all_commits.extend(commits)
            repos_analyzed += 1
            if commits:
                final_count = commits[-1]["sorry_count"]
                logger.info(f"  Found {len(commits)} commits, final sorry count: {final_count}")
            else:
                logger.info("  No sorry-related commits found")
        else:
            commits = analyze_repo_sorry_history(repo_url, repo_path)
            all_commits.extend(commits)
            repos_analyzed += 1
            total_added = sum(c["added"] for c in commits)
            total_removed = sum(c["removed"] for c in commits)
            logger.info(f"  Found {len(commits)} commits with sorry changes (+{total_added}/-{total_removed})")

    # Write output (different format for accurate vs fast mode)
    if accurate:
        output_data = {
            "documentation": (
                f"Historical sorry counts in Lean reservoir repositories using git pickaxe + checkout. "
                f"Generated on {datetime.now(timezone.utc).isoformat()}. "
                f"Analyzed repos updated since {updated_since.isoformat()} with at least {minimum_stars} stars. "
                f"Each commit entry includes 'sorry_count' - the absolute count at that commit (100% accurate)."
            ),
            "mode": "accurate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_repos_analyzed": repos_analyzed,
            "total_repos_failed": repos_failed,
            "total_commits": len(all_commits),
            "commits": all_commits,
        }
        logger.info(f"Analysis complete (accurate mode). Analyzed {repos_analyzed} repos, found {len(all_commits)} commits.")
    else:
        # Compute summary statistics for fast mode
        total_added = sum(c["added"] for c in all_commits)
        total_removed = sum(c["removed"] for c in all_commits)

        output_data = {
            "documentation": (
                f"Historical sorry changes in Lean reservoir repositories using git pickaxe (git log -S -p). "
                f"Generated on {datetime.now(timezone.utc).isoformat()}. "
                f"Analyzed repos updated since {updated_since.isoformat()} with at least {minimum_stars} stars. "
                f"Each commit entry includes 'added' and 'removed' counts parsed from diffs."
            ),
            "mode": "fast",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_repos_analyzed": repos_analyzed,
            "total_repos_failed": repos_failed,
            "total_commits": len(all_commits),
            "total_added": total_added,
            "total_removed": total_removed,
            "commits": all_commits,
        }
        logger.info(f"Analysis complete. Analyzed {repos_analyzed} repos, found {len(all_commits)} commits with sorry changes.")
        logger.info(f"Total: +{total_added} added, -{total_removed} removed")

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.info(f"Results written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Lean reservoir repositories for historical sorries using git pickaxe"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON file path",
    )
    parser.add_argument(
        "--clone-dir",
        required=True,
        help="Directory to clone repositories into (persistent)",
    )
    parser.add_argument(
        "--updated-since",
        default="2000-01-01",
        help="Only include repos updated since this date (isoformat, default: 2000-01-01)",
    )
    parser.add_argument(
        "--minimum-stars",
        type=int,
        default=0,
        help="Minimum number of GitHub stars (default: 0)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--accurate",
        action="store_true",
        help="Use accurate mode: checkout each commit and count sorries directly (slower but 100%% accurate)",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Parse the date and make it timezone-aware (UTC)
    updated_since = datetime.fromisoformat(args.updated_since).replace(
        tzinfo=timezone.utc
    )

    clone_dir = Path(args.clone_dir)

    try:
        analyze_all_reservoir_sorries(
            updated_since=updated_since,
            minimum_stars=args.minimum_stars,
            output_path=args.output,
            clone_dir=clone_dir,
            accurate=args.accurate,
        )
    except Exception as e:
        logger.exception(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())

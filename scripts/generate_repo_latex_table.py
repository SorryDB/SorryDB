#!/usr/bin/env python3
"""Generate a LaTeX list of repos from the sorry dataset."""

import json
from collections import Counter
from pathlib import Path


def extract_repo_name(url: str) -> str:
    """Extract repo name from GitHub URL."""
    # Remove trailing .git if present
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    # Get the last part of the URL (owner/repo)
    parts = url.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return url


def escape_latex(text: str) -> str:
    """Escape special LaTeX characters."""
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def count_sorries_per_repo(json_path: str) -> tuple[Counter, dict]:
    """Count sorries per repo from a JSON file.

    Returns:
        Tuple of (repo_counts Counter, repo_urls dict)
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    repo_counts = Counter()
    repo_urls = {}

    for sorry in data["sorries"]:
        url = sorry["repo"]["remote"]
        repo_name = extract_repo_name(url)
        repo_counts[repo_name] += 1
        repo_urls[repo_name] = url

    return repo_counts, repo_urls


def generate_latex_list(
    json_path: str,
    json_path_2: str | None = None,
    output_path: str | None = None
) -> str:
    """Generate LaTeX list from the sorry dataset(s).

    Args:
        json_path: Path to the first JSON file containing sorries
        json_path_2: Optional path to second JSON file for comparison
        output_path: Optional path to write the LaTeX output

    Returns:
        LaTeX list as a string
    """
    repo_counts_1, repo_urls = count_sorries_per_repo(json_path)

    if json_path_2:
        repo_counts_2, repo_urls_2 = count_sorries_per_repo(json_path_2)
        # Merge URLs (prefer first file's URLs)
        for repo, url in repo_urls_2.items():
            if repo not in repo_urls:
                repo_urls[repo] = url
        # Get all repos from both files
        all_repos = set(repo_counts_1.keys()) | set(repo_counts_2.keys())
    else:
        repo_counts_2 = None
        all_repos = set(repo_counts_1.keys())

    sorted_repos = sorted(all_repos)

    # Generate longtable format
    if repo_counts_2 is not None:
        # Two column version (test set and full set)
        lines = [
            r"\begin{longtable}{lrr}",
            r"\caption{Repositories in the \texttt{SorryDB-2601} Dataset}",
            r"\label{tab:repos} \\",
            r"\toprule",
            r"Repository & Test Set & Full Set \\",
            r"\midrule",
            r"\endfirsthead",
            r"\toprule",
            r"Repository & Test Set & Full Set \\",
            r"\midrule",
            r"\endhead",
            r"\midrule",
            r"\multicolumn{3}{r}{\textit{Continued on next page}} \\",
            r"\endfoot",
            r"\bottomrule",
            r"\endlastfoot",
            "",
        ]

        total_1 = 0
        total_2 = 0
        for repo_name in sorted_repos:
            count_1 = repo_counts_1.get(repo_name, 0)
            count_2 = repo_counts_2.get(repo_name, 0)
            total_1 += count_1
            total_2 += count_2
            url = repo_urls[repo_name]
            escaped_name = escape_latex(repo_name)

            lines.append(f"\\href{{{url}}}{{{escaped_name}}} & {count_1} & {count_2} \\\\")

        lines.extend([
            r"\midrule",
            f"\\textbf{{Total}} & \\textbf{{{total_1}}} & \\textbf{{{total_2}}} \\\\",
            r"\end{longtable}",
        ])
    else:
        # Single column version
        lines = [
            r"\begin{longtable}{lr}",
            r"\caption{Repositories in the \texttt{SorryDB-2601} Dataset}",
            r"\label{tab:repos} \\",
            r"\toprule",
            r"Repository & Sorries \\",
            r"\midrule",
            r"\endfirsthead",
            r"\toprule",
            r"Repository & Sorries \\",
            r"\midrule",
            r"\endhead",
            r"\midrule",
            r"\multicolumn{2}{r}{\textit{Continued on next page}} \\",
            r"\endfoot",
            r"\bottomrule",
            r"\endlastfoot",
            "",
        ]

        total_sorries = 0
        for repo_name in sorted_repos:
            count = repo_counts_1.get(repo_name, 0)
            total_sorries += count
            url = repo_urls[repo_name]
            escaped_name = escape_latex(repo_name)

            lines.append(f"\\href{{{url}}}{{{escaped_name}}} & {count} \\\\")

        lines.extend([
            r"\midrule",
            f"\\textbf{{Total}} & \\textbf{{{total_sorries}}} \\\\",
            r"\end{longtable}",
        ])

    latex_output = "\n".join(lines)

    if output_path:
        with open(output_path, "w") as f:
            f.write(latex_output)
        print(f"LaTeX list written to {output_path}")

    return latex_output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate LaTeX list of repos from sorry dataset")
    parser.add_argument(
        "input",
        nargs="?",
        default="data/2025_12_experiment_all_reservoir/1000_all_reservoir.json",
        help="Path to the first JSON file containing sorries"
    )
    parser.add_argument(
        "--input2",
        help="Path to second JSON file for comparison column"
    )
    parser.add_argument(
        "-o", "--output",
        help="Path to write the LaTeX output (optional, prints to stdout if not specified)"
    )

    args = parser.parse_args()

    latex = generate_latex_list(args.input, args.input2, args.output)

    if not args.output:
        print(latex)

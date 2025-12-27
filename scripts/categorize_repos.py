#!/usr/bin/env python3
"""
Categorize Lean repositories using LLM.

This script takes a repository list JSON file and categorizes each repository
into one of the predefined categories using an LLM to analyze GitHub metadata.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import dotenv
import requests
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

# Setup logging
logger = logging.getLogger(__name__)


def setup_logging(level="INFO"):
    """Setup logging with standard format."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d - %(funcName)s()] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper()))


def load_repos_from_list(list_path: Path) -> list[str]:
    """
    Load repository URLs from a repo list JSON file.

    Args:
        list_path: Path to the repo list JSON file

    Returns:
        List of repository URLs
    """
    logger.info(f"Loading repositories from {list_path}")

    with open(list_path, "r", encoding="utf-8") as f:
        repo_list = json.load(f)

    repos = [repo["remote"] for repo in repo_list["repos"]]
    logger.info(f"Loaded {len(repos)} repositories")

    return repos


def load_repos_from_database(database_path: Path) -> list[str]:
    """
    Load unique repository URLs from a sorry database JSON file.

    Args:
        database_path: Path to the sorry database JSON file

    Returns:
        List of unique repository URLs
    """
    logger.info(f"Loading repositories from database {database_path}")

    with open(database_path, "r", encoding="utf-8") as f:
        database = json.load(f)

    # Extract unique repo URLs from sorries
    repos = set()
    for sorry in database["sorries"]:
        repos.add(sorry["repo"]["remote"])

    repos_list = sorted(repos)
    logger.info(f"Loaded {len(repos_list)} unique repositories from {len(database['sorries'])} sorries")

    return repos_list


def parse_github_url(url: str) -> tuple[str, str]:
    """
    Parse GitHub URL to extract owner and repo name.

    Args:
        url: GitHub repository URL

    Returns:
        Tuple of (owner, repo)
    """
    # Remove trailing slash and .git suffix
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    # Parse URL
    parts = url.split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL: {url}")

    repo = parts[-1]
    owner = parts[-2]

    return owner, repo


def fetch_github_metadata(owner: str, repo: str) -> Optional[dict]:
    """
    Fetch GitHub metadata for a repository.

    Args:
        owner: Repository owner
        repo: Repository name

    Returns:
        Dictionary with repository metadata, or None if fetch failed
    """
    logger.info(f"Fetching metadata for {owner}/{repo}")

    # Setup headers with optional authentication
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    metadata = {
        "url": f"https://github.com/{owner}/{repo}",
        "name": f"{owner}/{repo}",
        "description": None,
        "topics": [],
        "readme_excerpt": None,
    }

    # Fetch repository info
    try:
        repo_url = f"https://api.github.com/repos/{owner}/{repo}"
        r = requests.get(repo_url, timeout=15, headers=headers)

        if r.status_code == 404:
            logger.warning(f"Repository not found: {owner}/{repo}")
            return None
        elif r.status_code == 429:
            logger.error(f"Rate limited while fetching {owner}/{repo}")
            return None
        elif r.status_code != 200:
            logger.error(f"GitHub API error {r.status_code} for {owner}/{repo}")
            return None

        repo_data = r.json()
        metadata["description"] = repo_data.get("description", "")
        metadata["topics"] = repo_data.get("topics", [])

    except Exception as e:
        logger.error(f"Error fetching repo info for {owner}/{repo}: {e}")
        return None

    # Fetch README
    try:
        readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        r = requests.get(readme_url, timeout=15, headers=headers)

        if r.status_code == 200:
            readme_data = r.json()
            # README content is base64 encoded
            import base64
            readme_content = base64.b64decode(readme_data["content"]).decode("utf-8")
            # Take first 2000 characters as excerpt
            metadata["readme_excerpt"] = readme_content[:2000]
        else:
            logger.warning(f"No README found for {owner}/{repo}")

    except Exception as e:
        logger.warning(f"Error fetching README for {owner}/{repo}: {e}")

    return metadata


def categorize_with_llm(repo_data: dict, model: ChatAnthropic) -> dict:
    """
    Categorize repository using LLM.

    Args:
        repo_data: Repository metadata
        model: LangChain ChatAnthropic model

    Returns:
        Dictionary with category and reasoning
    """
    logger.info(f"Categorizing {repo_data['name']}")

    # Build prompt
    prompt = f"""You are categorizing Lean 4 repositories for a database of proof obligations (sorries).
The goal is to understand what type of project each repository represents.

Categories (choose exactly one):
- pedagogical: Teaching materials, tutorials, course repositories, learning resources
- library: Reusable infrastructure, tooling, general-purpose libraries (like mathlib4, batteries)
- formalization: Projects formalizing specific theorems or mathematical theories (like FLT, Carleson theorem)
- benchmark: Math competition problems, AI evaluation datasets, benchmark suites (IMO, miniF2F, etc.)
- other: Experimental projects, domain-specific research, or anything that doesn't fit other categories

Repository to categorize:
- Name: {repo_data['name']}
- Description: {repo_data['description'] or 'None'}
- Topics: {', '.join(repo_data['topics']) or 'None'}
- README excerpt: {repo_data['readme_excerpt'][:500] if repo_data['readme_excerpt'] else 'None'}

Respond with valid JSON in this exact format:
{{
  "category": "one of the categories above",
  "reasoning": "brief explanation (1-2 sentences) of why this category fits"
}}"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.invoke([HumanMessage(content=prompt)])
            response_text = response.content

            # Parse JSON response
            # LLM might wrap JSON in markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            result = json.loads(response_text)

            # Validate category
            valid_categories = ["pedagogical", "library", "formalization", "benchmark", "other"]
            if result["category"] not in valid_categories:
                logger.warning(f"Invalid category '{result['category']}', retrying...")
                continue

            return {
                "category": result["category"],
                "reasoning": result["reasoning"]
            }

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
        except Exception as e:
            logger.error(f"Error during categorization: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue

    # Failed all retries
    logger.error(f"Failed to categorize {repo_data['name']} after {max_retries} attempts")
    return {
        "category": "other",
        "reasoning": "Failed to categorize (LLM error)"
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Categorize Lean repositories using LLM"
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to input JSON file (repo list or sorry database)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path for categorization results (default: auto-generated based on input)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-categorization of all repos, even if they already exist in output"
    )

    args = parser.parse_args()

    # Setup
    setup_logging(args.log_level)
    dotenv.load_dotenv()

    try:
        # Auto-detect input format and load repositories
        logger.info(f"Reading input file: {args.input}")
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "repos" in data:
            # Repo list format
            logger.info("Detected repo list format")
            repos = [repo["remote"] for repo in data["repos"]]
        elif "sorries" in data:
            # Sorry database format
            logger.info("Detected sorry database format")
            repos_set = set()
            for sorry in data["sorries"]:
                repos_set.add(sorry["repo"]["remote"])
            repos = sorted(repos_set)
            logger.info(f"Extracted {len(repos)} unique repositories from {len(data['sorries'])} sorries")
        else:
            logger.error("Unrecognized input format. Expected 'repos' or 'sorries' key in JSON.")
            return 1

        logger.info(f"Loaded {len(repos)} repositories")

        # Set default output path based on input if not specified
        if args.output is None:
            output_name = args.input.stem + "_categories.json"
            args.output = args.input.parent / output_name
            logger.info(f"Using auto-generated output path: {args.output}")

        # Load existing categories if output file exists
        existing_categories = {}
        if args.output.exists() and not args.force:
            logger.info(f"Loading existing categories from {args.output}")
            try:
                with open(args.output, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    if "categories" in existing_data and isinstance(existing_data["categories"], list):
                        for cat in existing_data["categories"]:
                            existing_categories[cat["name"]] = cat
                        logger.info(f"Loaded {len(existing_categories)} existing categories")
            except Exception as e:
                logger.warning(f"Failed to load existing categories: {e}")
                logger.warning("Will proceed with fresh categorization")
        elif args.force:
            logger.info("--force flag set, will re-categorize all repos")

        # Filter repos that need categorization
        repos_to_process = []
        for repo_url in repos:
            try:
                owner, repo = parse_github_url(repo_url)
                repo_name = f"{owner}/{repo}"
                if repo_name not in existing_categories:
                    repos_to_process.append(repo_url)
                else:
                    logger.debug(f"Skipping {repo_name} (already categorized)")
            except Exception as e:
                logger.warning(f"Failed to parse {repo_url}: {e}")
                repos_to_process.append(repo_url)

        logger.info(f"{len(existing_categories)} repos already categorized, {len(repos_to_process)} repos need categorization")

        # Initialize LLM only if needed
        if len(repos_to_process) > 0:
            logger.info("Initializing LLM model")
            model = ChatAnthropic(model="claude-sonnet-4-5-20250929")
        else:
            logger.info("No new repos to categorize")
            model = None

        # Process repositories that need categorization
        new_results = []
        failures = []

        for i, repo_url in enumerate(repos_to_process):
            logger.info(f"Processing {i+1}/{len(repos_to_process)}: {repo_url}")

            try:
                # Parse URL
                owner, repo = parse_github_url(repo_url)

                # Fetch metadata
                metadata = fetch_github_metadata(owner, repo)

                if metadata is None:
                    logger.warning(f"Skipping {repo_url} due to metadata fetch failure")
                    failures.append({
                        "repo_url": repo_url,
                        "error": "Failed to fetch GitHub metadata"
                    })
                    continue

                # Categorize with LLM
                categorization = categorize_with_llm(metadata, model)

                # Store result as array element
                new_results.append({
                    "name": f"{owner}/{repo}",
                    "category": categorization["category"],
                    "reasoning": categorization["reasoning"],
                    "github_metadata": {
                        "description": metadata["description"],
                        "topics": metadata["topics"]
                    }
                })

                # Rate limiting delay (be nice to APIs)
                if i < len(repos_to_process) - 1:  # Don't wait after last repo
                    time.sleep(2)

            except Exception as e:
                logger.error(f"Error processing {repo_url}: {e}")
                failures.append({
                    "repo_url": repo_url,
                    "error": str(e)
                })
                continue

        # Merge existing and new results
        all_results = list(existing_categories.values()) + new_results

        # Sort by repo name for consistency
        all_results.sort(key=lambda x: x["name"])

        logger.info(f"Total results: {len(existing_categories)} existing + {len(new_results)} new = {len(all_results)} total")

        # Write output
        output_data = {
            "metadata": {
                "total_repos": len(all_results),
                "existing_categories": len(existing_categories),
                "newly_categorized": len(new_results),
                "failed": len(failures),
                "timestamp": datetime.now().isoformat(),
                "model": "claude-sonnet-4-5-20250929",
                "source": str(args.input)
            },
            "categories": all_results
        }

        if failures:
            output_data["failures"] = failures

        logger.info(f"Writing results to {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Categorization complete: {len(all_results)} total ({len(existing_categories)} existing, {len(new_results)} new), {len(failures)} failed")
        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Local script that runs on MorphCloud to submit a sorry to Aristotle.

This script:
1. Receives sorry JSON and repo path as arguments
2. Builds a prompt using the same logic as AristotleStrategyV2
3. Calls aristotlelib.Project.create_from_directory()
4. Immediately writes the project ID to result JSON and exits (no waiting)
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import aristotlelib

from ..database.sorry import Sorry


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Add file handler to also write logs to a file
try:
    file_handler = logging.FileHandler('/root/repo/aristotle_submit.log')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logging.getLogger().addHandler(file_handler)
except Exception as e:
    # Allow running this script also locally for debugging
    print(f"Could not create log file: {e}")

logger = logging.getLogger(__name__)


def build_prompt(sorry: Sorry, include_goal: bool = True) -> str:
    """Build a targeted prompt for proving a specific sorry.

    Reuses the same logic as AristotleStrategyV2._build_prompt().

    Args:
        sorry: The sorry to prove
        include_goal: Whether to include the goal state in the prompt

    Returns:
        A prompt string instructing Aristotle to prove this specific sorry
    """
    loc = sorry.location
    file_path = loc.path  # Relative path within the repo

    prompt_parts = [
        f"Fill in the sorry at line {loc.start_line} in {file_path}."
    ]

    # Optionally include the goal to help Aristotle understand what needs to be proved
    if include_goal and sorry.debug_info and sorry.debug_info.goal:
        prompt_parts.append(f"\nThe goal at this sorry is:\n```\n{sorry.debug_info.goal}\n```")

    return "\n".join(prompt_parts)


async def submit_to_aristotle(repo_path: Path, sorry: Sorry) -> dict:
    """Submit a sorry to Aristotle and return the project info immediately.

    Args:
        repo_path: Path to the Lean repository
        sorry: The sorry to prove

    Returns:
        Dictionary with project info including project_id
    """
    prompt = build_prompt(sorry)
    logger.info(f"Submitting to Aristotle with prompt: {prompt}")

    # Create a project from the repository directory
    project = await aristotlelib.Project.create_from_directory(
        prompt=prompt,
        project_dir=str(repo_path),
    )
    logger.info(f"Created Aristotle project: {project.project_id}")

    return {
        "sorry_id": sorry.id,
        "aristotle_project_id": project.project_id,
        "submitted_at": datetime.now().isoformat(),
        "prompt": prompt,
        "repo_path": str(repo_path),
        "file_path": sorry.location.path,
        "line": sorry.location.start_line,
    }


async def main_async(args):
    """Async main function."""
    logger.info("=" * 80)
    logger.info("Starting submit_aristotle_local.py")
    logger.info("=" * 80)

    load_dotenv()
    logger.info("Environment loaded")

    # Load sorry data
    logger.info("Loading sorry data...")
    if args.sorry_path:
        logger.info(f"Loading sorry from file: {args.sorry_path}")
        with open(args.sorry_path, "r") as f:
            sorry_data = json.load(f)
            # Handle both single object and array with one element
            if isinstance(sorry_data, list):
                if len(sorry_data) != 1:
                    raise ValueError(f"File contains {len(sorry_data)} sorries, expected 1")
                sorry_data = sorry_data[0]
    else:
        logger.info("Parsing sorry from JSON string...")
        sorry_data = json.loads(args.sorry_json)

    logger.info("Creating Sorry object...")
    sorry = Sorry.from_dict(sorry_data)
    logger.info(f"Sorry object created: id={sorry.id}")
    logger.info(f"Sorry location: {sorry.location.path}:{sorry.location.start_line}")

    repo_path = Path(args.repo_path)
    logger.info(f"Repository path: {repo_path}")

    try:
        # Submit to Aristotle
        result = await submit_to_aristotle(repo_path, sorry)
        result["success"] = True
        result["error"] = None
        logger.info(f"Successfully submitted: project_id={result['aristotle_project_id']}")

    except aristotlelib.AristotleAPIError as e:
        logger.error(f"Aristotle API error: {e}")
        result = {
            "sorry_id": sorry.id,
            "aristotle_project_id": None,
            "submitted_at": datetime.now().isoformat(),
            "success": False,
            "error": f"AristotleAPIError: {str(e)}",
        }

    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}: {e}")
        result = {
            "sorry_id": sorry.id,
            "aristotle_project_id": None,
            "submitted_at": datetime.now().isoformat(),
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}",
        }

    # Write result to output file
    logger.info(f"Writing result to: {args.output_path}")
    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info("Result file written successfully")

    logger.info("submit_aristotle_local.py completed")
    return 0 if result.get("success") else 1


def main():
    parser = argparse.ArgumentParser(
        description="Submit a sorry to Aristotle and return the project ID immediately"
    )
    parser.add_argument(
        "--sorry-json",
        type=str,
        required=False,
        help="JSON string with a single sorry object (not a path)",
    )
    parser.add_argument(
        "--sorry-path",
        type=str,
        required=False,
        help="Path to a JSON file containing a single sorry object",
    )
    parser.add_argument(
        "--repo-path",
        type=str,
        required=True,
        help="Path to the local repository",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="/root/repo/aristotle_submit.json",
        help="Path to write the result JSON file (default: /root/repo/aristotle_submit.json)",
    )

    args = parser.parse_args()
    logger.info(f"Full command: {' '.join(sys.argv)}")

    # Validate that exactly one of --sorry-json or --sorry-path is provided
    if args.sorry_json and args.sorry_path:
        parser.error("Cannot specify both --sorry-json and --sorry-path")
    if not args.sorry_json and not args.sorry_path:
        parser.error("Must specify either --sorry-json or --sorry-path")

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())

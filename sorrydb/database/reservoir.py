import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def clone_reservoir(temp_dir):
    """Clone the reservoir index to a temporary directory."""
    subprocess.run(
        ["git", "clone", "https://github.com/leanprover/reservoir-index.git", temp_dir],
        check=True,
    )


def find_metadata_files(reservoir_dir):
    """Find all metadata.json files in the reservoir index."""
    return list(Path(reservoir_dir).rglob("metadata.json"))


def process_repositories(updated_since, minimum_stars, reservoir_dir):
    """Process all repositories and filter based on criteria."""
    repos = []

    for metadata_file in find_metadata_files(reservoir_dir):
        with open(metadata_file, "r") as f:
            metadata = json.load(f)

            # Check if repository meets criteria
            updated_at = datetime.fromisoformat(
                metadata["updatedAt"].replace("Z", "+00:00")
            )
            stars = metadata.get("stars", 0)

            if updated_at >= updated_since and stars >= minimum_stars:
                # Find the git URL from sources
                git_url = None
                for source in metadata.get("sources", []):
                    if source.get("type") == "git" and source.get("host") == "github":
                        git_url = source.get("gitUrl")
                        break

                if git_url:
                    repos.append({"remote": git_url})

    return repos


def scrape_reservoir(updated_since, minimum_stars, output):
    # Process repositories using temporary directory
    with tempfile.TemporaryDirectory() as reservoir_dir:
        clone_reservoir(reservoir_dir)
        repos = process_repositories(updated_since, minimum_stars, reservoir_dir)

        # Create output JSON
        output_data = {
            "documentation": f"List of active repositories pulled from reservoir. Generated on {datetime.now().isoformat()}. Includes repositories which have been updated since {updated_since} and have at least {minimum_stars} GitHub stars.",
            "repos": repos,
        }

        # Write to output file
        with open(output, "w") as f:
            json.dump(output_data, f, indent=2)

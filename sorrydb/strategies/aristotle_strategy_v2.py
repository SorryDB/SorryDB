import asyncio
import logging
import tarfile
import tempfile
from pathlib import Path

import aristotlelib

from sorrydb.database.sorry import Sorry
from sorrydb.runners.json_runner import SorryStrategy
from sorrydb.utils.sorry_extraction import extract_proof_from_diff

logger = logging.getLogger(__name__)


class AristotleStrategyV2(SorryStrategy):
    """Strategy that uses Aristotle's theorem proving service via aristotlelib.

    This version uses the Project.create_from_directory API with a targeted prompt
    to specify which sorry to prove, rather than proving all sorries in a file.
    """

    def __init__(
        self,
        polling_interval_seconds: int = 30,
        include_goal_in_prompt: bool = True,
    ):
        """Initialize the Aristotle strategy.

        Args:
            polling_interval_seconds: How often to poll for completion (default: 30)
            include_goal_in_prompt: Whether to include the goal state in the prompt (default: True)
        """
        self.polling_interval_seconds = polling_interval_seconds
        self.include_goal_in_prompt = include_goal_in_prompt

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Prove a sorry using Aristotle's API.

        Args:
            repo_path: Path to the Lean repository
            sorry: The sorry to prove

        Returns:
            Proof string or None if no proof found
        """
        return asyncio.run(self._prove_sorry_async(repo_path, sorry))

    async def prove_sorry_async(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Async version for parallel execution support."""
        return await self._prove_sorry_async(repo_path, sorry)

    async def _prove_sorry_async(self, repo_path: Path, sorry: Sorry) -> str | None:
        loc = sorry.location
        file_path = loc.path  # Relative path within the repo

        # Build a targeted prompt for this specific sorry
        prompt = self._build_prompt(sorry, file_path)
        logger.info(f"Submitting to Aristotle with prompt: {prompt}")

        try:
            # Create a project from the repository directory
            project = await aristotlelib.Project.create_from_directory(
                prompt=prompt,
                project_dir=str(repo_path),
            )
            logger.info(f"Created Aristotle project: {project.project_id}")

            # Wait for completion and download result
            with tempfile.TemporaryDirectory() as temp_dir:
                result_path = Path(temp_dir) / "result.tar.gz"

                downloaded_path = await project.wait_for_completion(
                    destination=str(result_path),
                    polling_interval_seconds=self.polling_interval_seconds,
                )

                if not downloaded_path:
                    logger.warning(
                        f"Aristotle project {project.project_id} did not complete successfully. "
                        f"Status: {project.status}"
                    )
                    return None

                # Extract the proof from the result
                proof = self._extract_proof_from_result(
                    result_tar_path=Path(downloaded_path),
                    file_path=file_path,
                    sorry=sorry,
                    temp_dir=Path(temp_dir),
                    repo_path=repo_path,
                )
                return proof

        except aristotlelib.AristotleAPIError as e:
            logger.error(f"Aristotle API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {type(e).__name__}: {e}")
            return None

    def _build_prompt(self, sorry: Sorry, file_path: str) -> str:
        """Build a targeted prompt for proving a specific sorry.

        Args:
            sorry: The sorry to prove
            file_path: Relative path to the file containing the sorry

        Returns:
            A prompt string instructing Aristotle to prove this specific sorry
        """
        loc = sorry.location

        prompt_parts = [
            f"Replace the `sorry` at line {loc.start_line} in {file_path}.",
            "",
            "IMPORTANT: You must ONLY replace the `sorry` keyword itself with a valid tactic or proof term.",
            "Do NOT modify any surrounding code. Do NOT remove `by` if present. Do NOT restructure the proof.",
            "The replacement should be a drop-in substitution for the word `sorry` only.",
            "",
            "For example:",
            "  - If the code is `by sorry`, replace it with `by <tactic>`, NOT with just `<term>`",
            "  - If the code is `:= sorry`, replace it with `:= <term>`, NOT with `:= by <tactic>`",
        ]

        # Optionally include the goal to help Aristotle understand what needs to be proved
        if self.include_goal_in_prompt and sorry.debug_info.goal:
            prompt_parts.append(f"\nThe goal at this sorry is:\n```\n{sorry.debug_info.goal}\n```")

        return "\n".join(prompt_parts)

    def _extract_proof_from_result(
        self,
        result_tar_path: Path,
        file_path: str,
        sorry: Sorry,
        temp_dir: Path,
        repo_path: Path,
    ) -> str | None:
        """Extract the proof from Aristotle's result tar.gz.

        Args:
            result_tar_path: Path to the downloaded result tar.gz
            file_path: Relative path to the file that was modified
            sorry: The original sorry (for location info)
            temp_dir: Temporary directory for extraction
            repo_path: Path to the original repository

        Returns:
            The proof string or None if extraction failed
        """
        try:
            # Extract the tar.gz
            extract_dir = temp_dir / "extracted"
            extract_dir.mkdir(exist_ok=True)

            with tarfile.open(result_tar_path, "r:gz") as tar:
                tar.extractall(extract_dir)

            # Find the modified file
            # The tar might have a top-level directory, so we need to search
            modified_file = self._find_file_in_extracted(extract_dir, file_path)

            if not modified_file:
                logger.error(f"Could not find {file_path} in Aristotle result")
                return None

            # Read original file from repo
            original_file = repo_path / file_path
            original_content = original_file.read_text()

            # Truncate original to end at sorry line (matching LLMStrategy)
            original_lines = original_content.splitlines()[: sorry.location.end_line]
            original_truncated = "\n".join(original_lines)

            # Read the modified file
            modified_content = modified_file.read_text()

            # Use diff-based extraction
            proof = extract_proof_from_diff(
                original_truncated, modified_content, sorry.location
            )

            return proof

        except Exception as e:
            logger.error(f"Error extracting proof from result: {type(e).__name__}: {e}")
            return None

    def _find_file_in_extracted(self, extract_dir: Path, relative_path: str) -> Path | None:
        """Find a file in the extracted tar directory.

        The tar might have different structures, so we search for the file.
        """
        # Try direct path first
        direct_path = extract_dir / relative_path
        if direct_path.exists():
            return direct_path

        # Search for the file by name in case there's a wrapper directory
        target_name = Path(relative_path).name
        for path in extract_dir.rglob(target_name):
            # Check if the path ends with our relative path
            if str(path).endswith(relative_path):
                return path

        # Last resort: find any file with the same name
        for path in extract_dir.rglob(target_name):
            return path

        return None

    def name(self) -> str:
        return "AristotleStrategyV2"

"""Strategy that extracts a synthetic theorem from a sorry and uses an inner strategy to solve it."""

import asyncio
import json
import logging
import subprocess
import tempfile
from pathlib import Path

from sorrydb.database.sorry import Sorry, Location, RepoInfo, DebugInfo, Metadata
from sorrydb.runners.json_runner import SorryStrategy
from sorrydb.utils.lean_utils_runner import (
    run_extract_sorry,
    match_sorry_to_parsed_sorry,
    run_extract_goal,
)
from sorrydb.utils.proof_body_extractor import (
    extract_proof_body_from_theorem,
    wrap_as_exact_by,
)

logger = logging.getLogger(__name__)

# Default LeanUtils repository settings
DEFAULT_LEAN_UTILS_REPO = "https://github.com/SorryDB/LeanUtils.git"
DEFAULT_LEAN_UTILS_COMMIT = "main"  # or a specific commit hash for stability


class SyntheticTheoremStrategy:
    """Strategy that extracts a synthetic theorem and uses an inner strategy to solve it.

    This strategy:
    1. Uses LeanUtils ExtractSorry to find all sorries in the file
    2. Matches the target sorry to a ParsedSorry by position
    3. Uses LeanUtils ExtractGoal to create a synthetic theorem file
    4. Delegates to an inner strategy to solve the synthetic theorem
    5. Extracts the proof body and wraps it as `exact (by ...)`

    Args:
        inner_strategy: The strategy to use for solving the synthetic theorem
        lean_utils_path: Path to the LeanUtils repository (optional - will clone if not provided)
        lean_utils_repo: Git URL to clone LeanUtils from (default: SorryDB/LeanUtils)
        lean_utils_commit: Git commit/branch to checkout (default: main)
        use_exact_by_wrapper: Whether to wrap the proof in `exact (by ...)` (default: True)
    """

    def __init__(
        self,
        inner_strategy: SorryStrategy,
        lean_utils_path: Path | str | None = None,
        lean_utils_repo: str = DEFAULT_LEAN_UTILS_REPO,
        lean_utils_commit: str = DEFAULT_LEAN_UTILS_COMMIT,
        use_exact_by_wrapper: bool = True,
    ):
        self.inner_strategy = inner_strategy
        self._lean_utils_path = Path(lean_utils_path) if lean_utils_path else None
        self.lean_utils_repo = lean_utils_repo
        self.lean_utils_commit = lean_utils_commit
        self.use_exact_by_wrapper = use_exact_by_wrapper
        self._last_usage = None
        self._lean_utils_ready = False

    @property
    def lean_utils_path(self) -> Path:
        """Get the LeanUtils path, cloning if necessary."""
        if self._lean_utils_path is None:
            # Use a consistent location in /tmp for the cloned repo
            self._lean_utils_path = Path("/tmp/LeanUtils")
        return self._lean_utils_path

    def _ensure_lean_utils(self) -> None:
        """Ensure LeanUtils is cloned and built."""
        if self._lean_utils_ready:
            return

        lean_utils_path = self.lean_utils_path

        # Check if already exists and is valid
        if (lean_utils_path / "lakefile.toml").exists():
            logger.info(f"LeanUtils already exists at {lean_utils_path}")
            self._lean_utils_ready = True
            return

        logger.info(f"Cloning LeanUtils from {self.lean_utils_repo} to {lean_utils_path}")

        # Clone the repository
        lean_utils_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing directory if it exists but is incomplete
        if lean_utils_path.exists():
            import shutil
            shutil.rmtree(lean_utils_path)

        clone_result = subprocess.run(
            ["git", "clone", self.lean_utils_repo, str(lean_utils_path)],
            capture_output=True,
            text=True,
        )

        if clone_result.returncode != 0:
            raise RuntimeError(f"Failed to clone LeanUtils: {clone_result.stderr}")

        # Checkout specific commit/branch
        checkout_result = subprocess.run(
            ["git", "checkout", self.lean_utils_commit],
            cwd=lean_utils_path,
            capture_output=True,
            text=True,
        )

        if checkout_result.returncode != 0:
            raise RuntimeError(f"Failed to checkout {self.lean_utils_commit}: {checkout_result.stderr}")

        # Build LeanUtils (lake build)
        logger.info("Building LeanUtils with lake build...")
        build_result = subprocess.run(
            ["lake", "build"],
            cwd=lean_utils_path,
            capture_output=True,
            text=True,
        )

        if build_result.returncode != 0:
            logger.warning(f"lake build returned non-zero: {build_result.stderr}")
            # Don't fail - the scripts might still work with lake env lean --run

        logger.info("LeanUtils setup complete")
        self._lean_utils_ready = True

    def name(self) -> str:
        inner_name = (
            self.inner_strategy.name()
            if hasattr(self.inner_strategy, "name")
            else type(self.inner_strategy).__name__
        )
        return f"SyntheticTheorem({inner_name})"

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Attempt to prove a sorry using synthetic theorem extraction.

        Args:
            repo_path: Path to the repository
            sorry: The sorry to prove

        Returns:
            Proof string or None if no proof was found
        """
        try:
            return self._prove_sorry_impl(repo_path, sorry)
        except Exception as e:
            logger.error(f"SyntheticTheoremStrategy failed: {type(e).__name__}: {e}")
            return None

    def _prove_sorry_impl(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Implementation of prove_sorry with full error propagation."""
        # Ensure LeanUtils is available (clone if necessary)
        self._ensure_lean_utils()

        file_path = repo_path / sorry.location.path

        # Step 1: Run ExtractSorry to get all ParsedSorry objects
        logger.info(f"Running ExtractSorry on {file_path}")
        parsed_sorries = run_extract_sorry(self.lean_utils_path, repo_path, file_path)

        if not parsed_sorries:
            logger.warning("ExtractSorry found no sorries in file")
            return None

        # Step 2: Match the SorryDB sorry to a ParsedSorry by position
        matched_sorry = match_sorry_to_parsed_sorry(sorry, parsed_sorries)

        if matched_sorry is None:
            logger.warning("Could not match sorry to ParsedSorry")
            return None

        # Step 3: Run ExtractGoal to get the synthetic theorem content
        parsed_sorry_json = json.dumps(matched_sorry)
        logger.info("Running ExtractGoal to generate synthetic theorem")
        synthetic_content = run_extract_goal(
            self.lean_utils_path, repo_path, file_path, parsed_sorry_json
        )

        if not synthetic_content:
            logger.warning("ExtractGoal returned empty content")
            return None

        # Step 4: Write synthetic theorem to temp file and create synthetic Sorry
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lean", delete=False
        ) as tmp_file:
            tmp_file.write(synthetic_content)
            tmp_path = Path(tmp_file.name)

        try:
            # Find the sorry position in the synthetic file
            # The synthetic theorem ends with `:= sorry`
            lines = synthetic_content.splitlines()
            sorry_line = len(lines)  # Last line (1-indexed)
            sorry_col = 1

            # Find the actual sorry position
            for i, line in enumerate(lines, 1):
                col = line.find("sorry")
                if col != -1:
                    sorry_line = i
                    sorry_col = col + 1  # 1-indexed
                    break

            # Create a synthetic Sorry object for the temp file
            synthetic_sorry = Sorry(
                repo=sorry.repo,
                location=Location(
                    path=tmp_path.name,  # Just the filename
                    start_line=sorry_line,
                    start_column=sorry_col,
                    end_line=sorry_line,
                    end_column=sorry_col + 5,  # "sorry" is 5 chars
                ),
                debug_info=DebugInfo(
                    goal=matched_sorry["goal"],
                    url=sorry.debug_info.url,
                ),
                metadata=sorry.metadata,
            )

            # Step 5: Run inner strategy on the synthetic sorry
            # Use tmp_path.parent as repo_path since the file is standalone
            logger.info("Running inner strategy on synthetic theorem")
            inner_result = self.inner_strategy.prove_sorry(tmp_path.parent, synthetic_sorry)

            # Capture usage info from inner strategy
            if hasattr(self.inner_strategy, "get_usage_info"):
                self._last_usage = self.inner_strategy.get_usage_info()

            if inner_result is None:
                logger.warning("Inner strategy returned no proof")
                return None

            # Step 6: Extract the proof body from the inner result
            # The inner strategy returns the full replacement text
            # We need to extract the proof body if it's a full theorem

            # First, check if the result is already a proof body (not a full theorem)
            if not inner_result.strip().startswith("theorem"):
                # It's likely already extracted - use directly
                proof_body = inner_result.strip()
            else:
                # Extract the proof body from the theorem
                proof_body = extract_proof_body_from_theorem(inner_result)

            if proof_body is None:
                logger.warning("Could not extract proof body from inner result")
                return None

            # Step 7: Wrap in exact (by ...) if configured
            if self.use_exact_by_wrapper:
                result = wrap_as_exact_by(proof_body)
            else:
                result = proof_body

            logger.info(f"SyntheticTheoremStrategy produced: {result[:100]}...")
            return result

        finally:
            # Clean up temp file
            try:
                tmp_path.unlink()
            except Exception:
                pass

    async def prove_sorry_async(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Async version of prove_sorry.

        Currently delegates to the sync version via thread pool, but if the inner
        strategy has async support, we could use it.
        """
        # Check if inner strategy has async support
        if hasattr(self.inner_strategy, "prove_sorry_async"):
            return await self._prove_sorry_async_impl(repo_path, sorry)
        else:
            # Fall back to running sync version in thread
            return await asyncio.to_thread(self.prove_sorry, repo_path, sorry)

    async def _prove_sorry_async_impl(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Async implementation when inner strategy supports async."""
        try:
            # Ensure LeanUtils is available (clone if necessary)
            await asyncio.to_thread(self._ensure_lean_utils)

            file_path = repo_path / sorry.location.path

            # Steps 1-3 are CPU-bound, run in thread
            def extract_steps():
                parsed_sorries = run_extract_sorry(self.lean_utils_path, repo_path, file_path)
                if not parsed_sorries:
                    return None, None

                matched_sorry = match_sorry_to_parsed_sorry(sorry, parsed_sorries)
                if matched_sorry is None:
                    return None, None

                parsed_sorry_json = json.dumps(matched_sorry)
                synthetic_content = run_extract_goal(
                    self.lean_utils_path, repo_path, file_path, parsed_sorry_json
                )
                return matched_sorry, synthetic_content

            matched_sorry, synthetic_content = await asyncio.to_thread(extract_steps)

            if matched_sorry is None or not synthetic_content:
                return None

            # Step 4: Write synthetic theorem to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".lean", delete=False
            ) as tmp_file:
                tmp_file.write(synthetic_content)
                tmp_path = Path(tmp_file.name)

            try:
                # Find sorry position
                lines = synthetic_content.splitlines()
                sorry_line = len(lines)
                sorry_col = 1

                for i, line in enumerate(lines, 1):
                    col = line.find("sorry")
                    if col != -1:
                        sorry_line = i
                        sorry_col = col + 1
                        break

                # Create synthetic Sorry
                synthetic_sorry = Sorry(
                    repo=sorry.repo,
                    location=Location(
                        path=tmp_path.name,
                        start_line=sorry_line,
                        start_column=sorry_col,
                        end_line=sorry_line,
                        end_column=sorry_col + 5,
                    ),
                    debug_info=DebugInfo(
                        goal=matched_sorry["goal"],
                        url=sorry.debug_info.url,
                    ),
                    metadata=sorry.metadata,
                )

                # Step 5: Run inner strategy async
                logger.info("Running inner strategy async on synthetic theorem")
                inner_result = await self.inner_strategy.prove_sorry_async(
                    tmp_path.parent, synthetic_sorry
                )

                if hasattr(self.inner_strategy, "get_usage_info"):
                    self._last_usage = self.inner_strategy.get_usage_info()

                if inner_result is None:
                    return None

                # Step 6: Extract proof body
                if not inner_result.strip().startswith("theorem"):
                    proof_body = inner_result.strip()
                else:
                    proof_body = extract_proof_body_from_theorem(inner_result)

                if proof_body is None:
                    return None

                # Step 7: Wrap result
                if self.use_exact_by_wrapper:
                    result = wrap_as_exact_by(proof_body)
                else:
                    result = proof_body

                return result

            finally:
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"SyntheticTheoremStrategy async failed: {type(e).__name__}: {e}")
            return None

    def get_usage_info(self):
        """Return token usage from the inner strategy's last API call."""
        return self._last_usage

    def get_debug_info(self):
        """Return debug info from the inner strategy if available."""
        if hasattr(self.inner_strategy, "get_debug_info"):
            return self.inner_strategy.get_debug_info()
        return None

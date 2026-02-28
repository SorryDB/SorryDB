import asyncio
import json
import logging
import tarfile
import tempfile
from pathlib import Path

import aristotlelib
from aristotlelib import ProjectStatus

from sorrydb.database.sorry import Sorry
from sorrydb.runners.json_runner import SorryStrategy
from sorrydb.utils.sorry_extraction import extract_proof_from_diff

logger = logging.getLogger(__name__)


class AristotleCollectStrategy(SorryStrategy):
    """Strategy that retrieves proofs from already-completed Aristotle jobs.

    This strategy loads a mapping of sorry_id -> aristotle_project_id from a JSON file
    and fetches completed proofs from the Aristotle API.
    """

    def __init__(self, projects_file: str = "/root/aristotle_projects.json"):
        """Initialize the Aristotle collect strategy.

        Args:
            projects_file: Path to aristotle_projects.json on the instance
        """
        self.projects_file = Path(projects_file)
        self._mapping: dict[str, str] | None = None

    def _load_mapping(self) -> dict[str, str]:
        """Load sorry_id -> project_id mapping from file."""
        if self._mapping is None:
            with open(self.projects_file) as f:
                data = json.load(f)
            self._mapping = {
                p["sorry_id"]: p["aristotle_project_id"]
                for p in data["projects"]
                if p.get("success") and p.get("aristotle_project_id")
            }
            logger.info(f"Loaded {len(self._mapping)} project mappings from {self.projects_file}")
        return self._mapping

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Prove a sorry by fetching from Aristotle API.

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
        mapping = self._load_mapping()
        project_id = mapping.get(sorry.id)

        if not project_id:
            logger.warning(f"No project ID for sorry {sorry.id}")
            return None

        logger.info(f"Fetching project {project_id} for sorry {sorry.id}")

        try:
            project = await aristotlelib.Project.from_id(project_id)

            if project.status not in (ProjectStatus.COMPLETE, ProjectStatus.COMPLETE_WITH_ERRORS):
                logger.warning(f"Project {project_id} not complete: {project.status}")
                return None

            with tempfile.TemporaryDirectory() as temp_dir:
                result_path = Path(temp_dir) / "result.tar.gz"
                await project.get_solution(destination=str(result_path))

                file_path = sorry.location.path
                proof = self._extract_proof_from_result(
                    result_tar_path=result_path,
                    file_path=file_path,
                    sorry=sorry,
                    temp_dir=Path(temp_dir),
                    repo_path=repo_path,
                )
                return proof

        except aristotlelib.AristotleAPIError as e:
            logger.error(f"Aristotle API error for project {project_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching project {project_id}: {type(e).__name__}: {e}")
            return None

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

            # Read the modified file
            modified_content = modified_file.read_text()

            logger.info(f"Full modified file from Aristotle:\n{modified_content}")

            # Use diff-based extraction (pass full original so diff has anchors on both sides)
            proof = extract_proof_from_diff(
                original_content, modified_content, sorry.location
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
        return "AristotleCollectStrategy"

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
    ) -> str | None:
        """Extract the proof from Aristotle's result tar.gz.

        Args:
            result_tar_path: Path to the downloaded result tar.gz
            file_path: Relative path to the file that was modified
            sorry: The original sorry (for location info)
            temp_dir: Temporary directory for extraction

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

            # Read the modified file
            modified_content = modified_file.read_text()

            # Extract the proof by comparing with the original location
            proof = self._extract_proof_at_location(
                modified_content, sorry.location
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

    def _extract_proof_at_location(self, modified_content: str, location) -> str | None:
        """Extract the proof that replaced the sorry at the given location.

        This is a heuristic approach: we look at the line where the sorry was
        and try to extract what replaced it.

        Args:
            modified_content: The content of the modified file
            location: The original sorry location

        Returns:
            The proof string or None
        """
        lines = modified_content.splitlines()

        # The sorry was at start_line (1-indexed)
        # Get the content starting from that line
        if location.start_line > len(lines):
            logger.error(f"Start line {location.start_line} exceeds file length {len(lines)}")
            return None

        # Get the line where sorry was (0-indexed)
        sorry_line_idx = location.start_line - 1
        sorry_line = lines[sorry_line_idx]

        # Check if this line still contains "sorry" - if so, Aristotle didn't solve it
        if "sorry" in sorry_line.lower():
            logger.warning("The sorry was not replaced in the result")
            return None

        # Extract the content from the sorry position
        # This is approximate - we take from start_column to the end of what looks like a proof
        start_col = location.start_column - 1  # Convert to 0-indexed

        # Get content from the sorry's start position
        if start_col < len(sorry_line):
            proof_start = sorry_line[start_col:].strip()
        else:
            proof_start = sorry_line.strip()

        # If the proof spans multiple lines, we need to figure out where it ends
        # This is tricky without parsing Lean, so we use a simple heuristic:
        # Take lines until we hit an empty line or a new declaration
        proof_lines = [proof_start]

        for i in range(sorry_line_idx + 1, len(lines)):
            line = lines[i]
            stripped = line.strip()

            # Stop at empty lines or new top-level declarations
            if not stripped:
                break
            if stripped.startswith(("theorem ", "lemma ", "def ", "example ", "instance ", "#")):
                break
            # Stop if indentation decreases significantly (back to top level)
            if line and not line[0].isspace() and not line.startswith("  "):
                break

            proof_lines.append(line)

        proof = "\n".join(proof_lines).strip()

        # Clean up the proof if needed
        if proof:
            return proof

        return None

    def name(self) -> str:
        return "AristotleCollectStrategy"

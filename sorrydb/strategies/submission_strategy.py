"""Replay proofs from a prover submission file instead of generating them."""

import json
import logging
from pathlib import Path

from ..database.sorry import Sorry
from ..runners.json_runner import SorryStrategy
from ..utils.verify import verify_extended_proof

logger = logging.getLogger(__name__)

# The REPL is cloned and built here rather than inside the repo under test:
# setup_repl treats any non-empty directory as already built, so per-repo REPLs
# mean a redundant build per checkout and concurrent clones of the same tag
# corrupt each other permanently.
DEFAULT_REPL_ROOT = Path.home() / ".sorrydb_repl_cache"


class SubmissionStrategy(SorryStrategy):
    """Serve proofs from a submission file, keyed by sorry id.

    A submission entry carries more than a proof string: helper declarations to
    splice in ahead of the target, an insertion line, and sometimes extra
    imports. The usual verifier only substitutes the sorry span and cannot see
    the helpers, so verification goes through `verify_submission` below rather
    than through VerificationContext.
    """

    def __init__(self, submission_file: str, repl_root: str | None = None):
        self.submission_file = Path(submission_file)
        self.repl_root = Path(repl_root) if repl_root else DEFAULT_REPL_ROOT
        entries = json.loads(self.submission_file.read_text())
        self.entries = {e["sorry"]["id"]: e for e in entries}
        logger.info(
            f"Loaded {len(self.entries)} submission entries from {self.submission_file}"
        )

    def name(self):
        return "submission"

    def entry_for(self, sorry: Sorry) -> dict | None:
        return self.entries.get(sorry.id)

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        entry = self.entry_for(sorry)
        if entry is None:
            logger.warning(f"No submission entry for sorry {sorry.id}")
            return None
        logger.info(f"Replaying submitted proof for {sorry.id}: {entry['proof']}")
        return entry["proof"]

    def verify_submission(self, repo_path: Path, sorry: Sorry) -> tuple[bool, str]:
        """Verify the submitted proof together with its helpers and imports."""
        entry = self.entry_for(sorry)
        if entry is None:
            return False, f"No submission entry for sorry {sorry.id}"

        helpers = entry.get("helpers") or []
        imports = entry.get("imports") or []
        helpers_at_line = (entry.get("insert_at") or {}).get("line")
        logger.info(
            f"Verifying {sorry.id}: {len(helpers)} helper(s), {len(imports)} import(s), "
            f"inserted before line {helpers_at_line}"
        )

        self.repl_root.mkdir(parents=True, exist_ok=True)
        return verify_extended_proof(
            repo_dir=repo_path,
            lean_version=sorry.repo.lean_version,
            location=sorry.location,
            proof=entry["proof"],
            imports=imports,
            helpers=helpers,
            helpers_at_line=helpers_at_line,
            repl_root=self.repl_root,
        )

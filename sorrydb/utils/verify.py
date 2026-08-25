#!/usr/bin/env python3

import logging
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from lean_interact import FileCommand, LeanREPLConfig, LeanServer, LocalProject
from lean_interact.interface import LeanError
from sorrydb.database.sorry import Location

from .repl_ops import LeanRepl, setup_repl, check_lean_file

logger = logging.getLogger(__name__)

REPL_TIMEOUT=60

def verify_proof(
    repo_dir: Path,
    lean_version: str,
    location: Location,
    proof: str,
    use_lean_interact: bool = False,
) -> bool:
    """
    Verify if a proof successfully replaces a sorry at a specific location.

    Args:
        repo_dir: Path to the repository
        lean_version: Lean version tag
        location: Location object containing sorry location info (path and coordinates)
        proof: The Proof string to replace the sorry, or None
        use_lean_interact: If True, use LeanInteract library instead of custom LeanRepl

    Returns:
        Boolean indicating whether the proof successfully replaces the sorry
    """
    # Load the original file
    file_path = location.path
    full_path = repo_dir / Path(file_path)
    original_file = full_path.read_text()

    # Obtain absolute linear character indices of sorry
    start_index = position_to_index(
        original_file, location.start_line, location.start_column
    )
    end_index = position_to_index(original_file, location.end_line, location.end_column)

    # Replace sorry with proof
    modified_file = (
        original_file[:start_index] + proof + original_file[end_index:]
    )

    offset = start_index - end_index + len(proof)


    # Create a temporary file in the same directory as the original file
    parent_dir = full_path.parent
    with tempfile.NamedTemporaryFile(
        suffix=".lean", dir=parent_dir, delete=True
    ) as tmp:
        logger.debug(f"Writing modified file for REPL to check: {modified_file}")
        tmp.write(modified_file.encode("utf-8"))
        tmp.flush()  # Ensure all data is written to disk

        # Get the relative path from repo_dir to the temp file
        temp_path = Path(tmp.name).resolve()
        # repo_dir must be resolve if it is a relative path
        modified_file_path = temp_path.relative_to(repo_dir.resolve())

        # Quickly verify the file with lake env lean before doing full analysis
        logger.info(" Checking file") 
        can_build, errors = check_lean_file(
            repo_dir, modified_file_path, show_warnings=False
        )
        if not can_build:
            error_msg = f"Cannot build modified file: {errors}\n"
            logger.info(f" Cannot build modified file {errors}") 
            return False, error_msg
        
        # Read sorries using either LeanInteract or custom LeanRepl
        logger.info(f"Verifying with lean interact: {use_lean_interact}") 
        if use_lean_interact:
            # Use LeanInteract
            # Note: LocalProject automatically infers the Lean version from the project
            logger.info(" Building REPL config ") 
            project = LocalProject(directory=str(repo_dir.resolve()))
            config = LeanREPLConfig(
                project=project,
                verbose=False,
            )


            try:
                logger.info("Trying to create lean server") 
                server = LeanServer(config)

                # Read sorries from original file
                try:
                    logger.info(f"Trying to read orignal file with timeout {REPL_TIMEOUT}")
                    original_response = server.run(
                        FileCommand(path=str(file_path)), timeout=REPL_TIMEOUT
                    )
                    logger.info(f"response from original file {REPL_TIMEOUT}")

                    # Check if response is an error (including timeout)
                    if isinstance(original_response, LeanError):
                        error_msg = f"Failed to analyze original file: {original_response.message}"
                        logger.warning(error_msg)
                        return False, error_msg

                    sorries_raw = (
                        original_response.sorries if original_response.sorries else []
                    )
                    # Convert LeanInteract Sorry objects to our format
                    sorries = [
                        {
                            "location": {
                                "start_line": s.start_pos.line,
                                "start_column": s.start_pos.column,
                                "end_line": s.end_pos.line,
                                "end_column": s.end_pos.column,
                            },
                            "goal": s.goal,
                        }
                        for s in sorries_raw
                    ]
                except Exception as e:
                    error_msg = f"Failed to analyze original file: {e}"
                    logger.warning(error_msg)
                    return False, error_msg

                # Read sorries from modified file
                try:
                    logger.info("Trying to read modified file")
                    modified_response = server.run(
                        FileCommand(path=str(modified_file_path)), timeout=REPL_TIMEOUT
                    )

                    # Check if response is an error (including timeout)
                    if isinstance(modified_response, LeanError):
                        error_msg = f"Failed to analyze modified file: {modified_response.message}"
                        logger.warning(error_msg)
                        return False, error_msg

                    modified_sorries_raw = (
                        modified_response.sorries if modified_response.sorries else []
                    )
                    # Convert LeanInteract Sorry objects to our format
                    modified_sorries = [
                        {
                            "location": {
                                "start_line": s.start_pos.line,
                                "start_column": s.start_pos.column,
                                "end_line": s.end_pos.line,
                                "end_column": s.end_pos.column,
                            },
                            "goal": s.goal,
                        }
                        for s in modified_sorries_raw
                    ]
                except Exception as e:
                    error_msg = f"Failed to analyze modified file: {e}"
                    logger.warning(error_msg)
                    return False, error_msg

            except Exception as e:
                error_msg = f"Failed to initialize LeanInteract: {e}"
                logger.error(error_msg)
                return False, error_msg

        else:
            # Use custom LeanRepl
            repl_binary = setup_repl(repo_dir, lean_version)
            with LeanRepl(repo_dir, repl_binary) as repl:
                try:
                    sorries = repl.read_file(file_path)
                except RuntimeError as e:
                    error_msg = f"Failed to analyze original file: {e}"
                    logger.warning(error_msg)
                    return False, error_msg

            # quickly verify the file with lake env lean before doing full build
            can_build, errors = check_lean_file(
                repo_dir, modified_file_path, show_warnings=False
            )
            if not can_build:
                error_msg = f"Cannot build modified file: {errors}\n"
                return False, error_msg

            with LeanRepl(repo_dir, repl_binary) as repl:
                try:
                    modified_sorries = repl.read_file(modified_file_path)
                except RuntimeError as e:
                    error_msg = f"Failed to analyze modified file: {e}"
                    logger.warning(error_msg)
                    return False, error_msg

        # first check if we have removed one sorry
        if len(sorries) != len(modified_sorries) + 1:
            error_msg = "Expected one less sorry in modified file"
            logger.info(error_msg)
            return False, error_msg

        # Add character index to each sorry
        for sorry in sorries:
            sorry["index"] = position_to_index(
                original_file,
                sorry["location"]["start_line"],
                sorry["location"]["start_column"],
            )

        for sorry in modified_sorries:
            sorry["index"] = position_to_index(
                modified_file,
                sorry["location"]["start_line"],
                sorry["location"]["start_column"],
            )

        # next check if the sorries match up
        for original_sorry in sorries:
            # Skip the sorry that was replaced
            if original_sorry["index"] == start_index:
                continue

            # Find corresponding sorry in modified file
            expected_index = original_sorry["index"]
            if original_sorry["index"] > start_index:
                expected_index += offset

            # Look for matching sorry in modified file
            match_found = False
            for modified_sorry in modified_sorries:
                if modified_sorry["index"] == expected_index:
                    # check if goals match
                    if original_sorry["goal"] != modified_sorry["goal"]:
                        error_msg = "Matching sorry index, but goals do not agree"
                        logger.info(error_msg)
                        return False, error_msg
                    else:
                        match_found = True
                        break
            if not match_found:
                error_msg = "Sorries do not match up"
                logger.info(error_msg)
                return False, error_msg

        implementation = "LeanInteract" if use_lean_interact else "custom LeanRepl"
        logger.info(f"Proof verified (using {implementation})")
        return True, ""


def position_to_index(content: str, line: int, column: int) -> int:
    """
    Convert a (line, column) position to a linear character index.

    Args:
        content: File content as a string
        line: Line number (starts at 1)
        column: Column number

    Returns:
        Linear character index corresponding to the position

    Raises:
        ValueError: If the line or column is out of range
    """
    lines = content.split("\n")

    # Check if coordinates are valid
    if line < 1 or line > len(lines):
        raise ValueError(f"Line {line} out of range (1-{len(lines)})")
    if column < 0 or column > len(lines[line - 1]):
        raise ValueError(f"Column {column} is out of range for line {line}")

    # Add up the lengths of all previous lines plus newline characters
    index = sum(len(lines[i]) + 1 for i in range(line - 1))

    return index + column


# ---------------------------------------------------------------------------
# Extended proofs: imports + helper declarations + the sorry replacement
# ---------------------------------------------------------------------------


_METAVAR_RE = re.compile(r"\?([a-zA-Z_]+)\.(\d+)")


def normalize_goal(goal: str) -> str:
    """Renumber metavariable labels so goals can be compared across elaborations.

    Lean names anonymous metavariables from a global counter (`?u.16996`,
    `?m.3072`). Inserting a declaration ahead of a sorry shifts that counter, so
    two textually identical goals differ only in those numbers — which makes an
    exact string comparison report a mismatch on an unchanged goal. Distinct
    metavariables are still distinguished, since each is renumbered in order of
    first appearance; only the absolute values are discarded.
    """
    seen: dict[str, str] = {}

    def repl(m: "re.Match[str]") -> str:
        key = m.group(0)
        if key not in seen:
            seen[key] = f"?{m.group(1)}.{len(seen)}"
        return seen[key]

    return _METAVAR_RE.sub(repl, goal)


def apply_extended_patch(
    original_file: str,
    location: Location,
    proof: str,
    imports: list[str] | None = None,
    helpers: list[str] | None = None,
    helpers_at_line: int | None = None,
) -> tuple[str, "Callable[[int], int]"]:
    """Build the modified file and a map from original to modified char indices.

    Three edits, applied so that later ones don't disturb earlier positions:
      * the `sorry` span is replaced by `proof`
      * `helpers` are inserted before line `helpers_at_line` (1-indexed)
      * `imports` are inserted after the file's last `import` line

    Returns (modified_file, remap) where `remap(i)` gives the new index of an
    original index `i`. Callers need this because verification compares the
    positions of every *other* sorry in the file, and inserting declarations
    shifts them by a variable amount rather than the single delta that a bare
    span replacement produces.
    """
    imports = imports or []
    helpers = helpers or []

    start_index = position_to_index(
        original_file, location.start_line, location.start_column
    )
    end_index = position_to_index(original_file, location.end_line, location.end_column)

    lines = original_file.split("\n")

    def line_start_index(line_no_1based: int) -> int:
        line_no_1based = max(1, min(line_no_1based, len(lines) + 1))
        return sum(len(lines[i]) + 1 for i in range(line_no_1based - 1))

    helpers_text = ""
    helpers_index = None
    if helpers:
        helpers_index = line_start_index(helpers_at_line or 1)
        helpers_text = "\n".join(helpers) + "\n\n"

    imports_text = ""
    imports_index = None
    if imports:
        last_import = max(
            (n for n, line in enumerate(lines) if line.startswith("import ")), default=-1
        )
        imports_index = line_start_index(last_import + 2)
        imports_text = "".join(f"import {m}\n" for m in imports)

    # Build back-to-front so each splice uses original indices.
    edits = [(start_index, end_index, proof)]
    if helpers_index is not None:
        edits.append((helpers_index, helpers_index, helpers_text))
    if imports_index is not None:
        edits.append((imports_index, imports_index, imports_text))
    edits.sort(key=lambda e: e[0], reverse=True)

    modified = original_file
    for begin, finish, text in edits:
        modified = modified[:begin] + text + modified[finish:]

    proof_delta = len(proof) - (end_index - start_index)

    def remap(index: int) -> int:
        shifted = index
        if imports_index is not None and index >= imports_index:
            shifted += len(imports_text)
        if helpers_index is not None and index >= helpers_index:
            shifted += len(helpers_text)
        if index > start_index:
            shifted += proof_delta
        return shifted

    return modified, remap


def verify_extended_proof(
    repo_dir: Path,
    lean_version: str,
    location: Location,
    proof: str,
    imports: list[str] | None = None,
    helpers: list[str] | None = None,
    helpers_at_line: int | None = None,
    repl_root: Path | None = None,
) -> tuple[bool, str]:
    """Verify a proof that also needs new imports and helper declarations.

    Same contract as `verify_proof` — the file must compile, exactly one sorry
    must disappear, and every other sorry must survive with an unchanged goal —
    but the submission may additionally add imports and top-level declarations.
    That is outside the official `proof`-string format, so this is for evaluating
    submissions that carry the richer payload.
    """
    full_path = repo_dir / Path(location.path)
    original_file = full_path.read_text()

    start_index = position_to_index(
        original_file, location.start_line, location.start_column
    )

    modified_file, remap = apply_extended_patch(
        original_file, location, proof, imports, helpers, helpers_at_line
    )

    # `repl_root` keeps the REPL out of the tree under test: setup_repl clones and
    # builds it into whatever directory it is given, and treats any non-empty
    # directory as already built -- so per-worktree REPLs mean one redundant build
    # per checkout, and concurrent clones of the same tag poison each other for good.
    repl_binary = setup_repl(repl_root or repo_dir, lean_version)
    with LeanRepl(repo_dir, repl_binary) as repl:
        try:
            sorries = repl.read_file(Path(location.path))
        except RuntimeError as e:
            return False, f"Failed to analyze original file: {e}"

    parent_dir = full_path.parent
    with tempfile.NamedTemporaryFile(suffix=".lean", dir=parent_dir, delete=True) as tmp:
        tmp.write(modified_file.encode("utf-8"))
        tmp.flush()
        modified_file_path = Path(tmp.name).resolve().relative_to(repo_dir.resolve())

        can_build, errors = check_lean_file(
            repo_dir, modified_file_path, show_warnings=False
        )
        if not can_build:
            return False, f"Cannot build modified file: {errors}\n"

        with LeanRepl(repo_dir, repl_binary) as repl:
            try:
                modified_sorries = repl.read_file(modified_file_path)
            except RuntimeError as e:
                return False, f"Failed to analyze modified file: {e}"

        if len(sorries) != len(modified_sorries) + 1:
            return False, (
                f"Expected one less sorry in modified file "
                f"(original {len(sorries)}, modified {len(modified_sorries)}); "
                "helper declarations must not introduce sorries"
            )

        for sorry in sorries:
            sorry["index"] = position_to_index(
                original_file,
                sorry["location"]["start_line"],
                sorry["location"]["start_column"],
            )
        for sorry in modified_sorries:
            sorry["index"] = position_to_index(
                modified_file,
                sorry["location"]["start_line"],
                sorry["location"]["start_column"],
            )

        # The REPL reports one entry per unsolved goal, not per `sorry` token, so a
        # single token that closes several goals (`constructor <;> sorry`) yields
        # several entries sharing one char index. Matching on index alone would then
        # pair each of them against whichever entry happens to be listed first at
        # that index -- `case right` compared against `case left` -- and report a goal
        # disagreement for a sorry nobody touched. Pair on (index, goal) instead, and
        # consume each match so multiplicity at an index has to agree too.
        pool = list(modified_sorries)
        for original_sorry in sorries:
            if original_sorry["index"] == start_index:
                continue  # the one we replaced
            expected_index = remap(original_sorry["index"])
            at_index = [m for m in pool if m["index"] == expected_index]
            if not at_index:
                return False, "Sorries do not match up"
            want = normalize_goal(original_sorry["goal"])
            match = next((m for m in at_index if normalize_goal(m["goal"]) == want), None)
            if match is None:
                return False, (
                    "Matching sorry index, but goals do not agree\n"
                    f"  original: {original_sorry['goal'][:4000]}\n"
                    f"  modified: {at_index[0]['goal'][:4000]}"
                )
            pool.remove(match)

    logger.info("Extended proof verified")
    return True, ""

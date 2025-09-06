import pytest
from unittest.mock import patch, MagicMock

from pathlib import Path
from sorrydb.database.process_sorries import get_repo_lean_version
from sorrydb.utils.lean_repo import build_lean_project
from sorrydb.utils.repl_ops import setup_repl
from sorrydb.utils.repl_ops import LeanRepl, ReplCommandTimeout

REPO_DIR = "mock_lean_repository"


def test_repl_timeout():
    # Get the mock repository directory and proofs file
    repo_dir = Path(__file__).parent / REPO_DIR
    # Determine Lean version of the repo
    lean_version = get_repo_lean_version(repo_dir)

    repl_binary = setup_repl(repo_dir, lean_version)
    build_lean_project(repo_dir)

    file_path = Path("MockLeanRepository/multiline_triple.lean")

    # Use pytest.raises to assert that the timeout exception is thrown.
    # The 'with' statement ensures the real REPL process is started
    # and properly cleaned up, even when an exception occurs.
    with pytest.raises(ReplCommandTimeout):
        with LeanRepl(repo_dir, repl_binary) as repl:
            # Call read_file with an extremely short timeout to ensure it triggers.
            # A real call to the REPL will take longer than this.
            repl.read_file(file_path, timeout=0.0001)

    # TODO: move this to its own test
    with LeanRepl(repo_dir, repl_binary) as repl:
        # Call read_file with a generous timeout (or None) to allow completion.
        sorries = repl.read_file(file_path)

        # --- Assertions about the output ---
        # NOTE: Adjust these assertions based on the actual content of your .lean file.

        # 1. Check that we received a list of sorries.
        assert isinstance(sorries, list)
        # 2. Check that at least one sorry was found.
        assert len(sorries) > 0

        # 3. Inspect the first sorry found.
        first_sorry = sorries[0]
        assert isinstance(first_sorry, dict)

        # 4. Check for the expected keys and value types.
        assert "proof_state_id" in first_sorry
        assert isinstance(first_sorry["proof_state_id"], int)

        assert "goal" in first_sorry
        assert isinstance(first_sorry["goal"], str)
        assert first_sorry["goal"] != ""  # Goal string should not be empty

        assert "location" in first_sorry
        location = first_sorry["location"]
        assert isinstance(location, dict)
        assert "start_line" in location
        assert "end_line" in location


@patch("sorrydb.utils.repl_ops.select.select")
@patch("sorrydb.utils.repl_ops.subprocess.Popen")
def test_send_command_timeout_and_cleanup(mock_popen, mock_select):
    """
    Verify that send_command raises ReplCommandTimeout and that the
    LeanRepl context manager still cleans up the process.
    """
    # 1. Setup mocks
    mock_process = MagicMock()
    mock_process.poll.return_value = None  # Simulate running process
    mock_popen.return_value = mock_process

    # Simulate select() timing out by returning empty lists
    mock_select.return_value = ([], [], [])

    # 2. Use a `with` block to ensure __enter__ and __exit__ are called
    #    Use pytest.raises to catch the expected exception
    with pytest.raises(ReplCommandTimeout):
        with LeanRepl(
            repo_path=Path("/fake/repo"), repl_binary=Path("/fake/bin")
        ) as repl:
            # This call should trigger the timeout because mock_select returns empty
            repl.send_command({"cmd": "do_something"}, timeout=0.1)

    # 3. Verify that the context manager cleaned up the process after the exception
    mock_process.terminate.assert_called_once()
    assert mock_process.wait.call_count > 0

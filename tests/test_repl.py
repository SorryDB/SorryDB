from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sorrydb.database.process_sorries import get_repo_lean_version
from sorrydb.utils.lean_repo import build_lean_project
from sorrydb.utils.repl_ops import LeanRepl, ReplCommandTimeout, setup_repl

REPO_DIR = "mock_lean_repository"


def test_repl_read_file():
    repo_dir = Path(__file__).parent / REPO_DIR
    lean_version = get_repo_lean_version(repo_dir)

    repl_binary = setup_repl(repo_dir, lean_version)
    build_lean_project(repo_dir)

    file_path1 = Path("MockLeanRepository/multiline_triple.lean")
    file_path2 = Path("MockLeanRepository/triple.lean")
    with LeanRepl(repo_dir, repl_binary) as repl:
        sorries = repl.read_file(file_path1)
        sorries2 = repl.read_file(file_path2)

        assert sorries == [
            {
                "proof_state_id": 0,
                "location": {
                    "start_line": 9,
                    "start_column": 48,
                    "end_line": 9,
                    "end_column": 53,
                },
                "goal": "n : Nat\n⊢ n + 1 = 1 + n + 0",
            },
            {
                "proof_state_id": 1,
                "location": {
                    "start_line": 11,
                    "start_column": 51,
                    "end_line": 11,
                    "end_column": 56,
                },
                "goal": "n : Nat\n⊢ n + 1 = 1 + n + 0",
            },
            {
                "proof_state_id": 2,
                "location": {
                    "start_line": 13,
                    "start_column": 51,
                    "end_line": 13,
                    "end_column": 56,
                },
                "goal": "n : Nat\n⊢ n + 1 = 1 + n + 0",
            },
        ]
        assert sorries2 == [
            {
                "proof_state_id": 6,
                "location": {
                    "start_line": 3,
                    "start_column": 26,
                    "end_line": 3,
                    "end_column": 31,
                },
                "goal": "⊢ 1 = 1",
            },
            {
                "proof_state_id": 7,
                "location": {
                    "start_line": 5,
                    "start_column": 29,
                    "end_line": 5,
                    "end_column": 34,
                },
                "goal": "⊢ 1 = 1",
            },
            {
                "proof_state_id": 8,
                "location": {
                    "start_line": 7,
                    "start_column": 29,
                    "end_line": 7,
                    "end_column": 34,
                },
                "goal": "⊢ 1 = 1",
            },
        ]


def test_repl_timeout():
    repo_dir = Path(__file__).parent / REPO_DIR
    lean_version = get_repo_lean_version(repo_dir)

    repl_binary = setup_repl(repo_dir, lean_version)
    build_lean_project(repo_dir)

    file_path = Path("MockLeanRepository/multiline_triple.lean")

    with pytest.raises(ReplCommandTimeout):
        with LeanRepl(repo_dir, repl_binary) as repl:
            # Call read_file with an extremely short timeout to ensure it triggers.
            # A real call to the REPL will take longer than this.
            repl.read_file(file_path, timeout=0.0001)


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

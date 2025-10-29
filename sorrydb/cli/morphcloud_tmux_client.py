#!/usr/bin/env python3
"""
Client for sending commands to tmux REPL session.

Usage:
    python -m sorrydb.cli.morphcloud_tmux_client \
        --sorry-json '{"id": "...", ...}' \
        --strategy '{"name": "rfl", "args": {}}' \
        --output-path /tmp/result.json
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SESSION_NAME = "lean_repl"
RESULT_MARKER = "RESULT_SAVED:"
ERROR_MARKER = "ERROR_SAVED:"


class TmuxREPLError(Exception):
    """Raised when tmux REPL communication fails"""
    pass


def check_tmux_session_exists(session_name: str) -> bool:
    """Check if tmux session exists"""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True
    )
    return result.returncode == 0


def send_command_to_repl(command: str, session_name: str = SESSION_NAME) -> str:
    """
    Send command to tmux REPL session.

    Args:
        command: Python command to execute
        session_name: Name of tmux session

    Returns:
        Session name (for chaining)
    """
    if not check_tmux_session_exists(session_name):
        raise TmuxREPLError(f"tmux session '{session_name}' does not exist")

    # Send command to REPL
    subprocess.run(
        ["tmux", "send-keys", "-t", session_name, command, "Enter"],
        check=True,
        capture_output=True
    )

    # Small delay for command to start
    time.sleep(0.2)

    return session_name


def wait_for_completion(
    output_path: str,
    session_name: str = SESSION_NAME,
    timeout: int = 600,
    poll_interval: float = 1.0
) -> bool:
    """
    Wait for result file to appear.

    Args:
        output_path: Path to result file
        session_name: Name of tmux session
        timeout: Maximum wait time in seconds
        poll_interval: Check interval in seconds

    Returns:
        True if completed successfully, False if timeout
    """
    start_time = time.time()
    output_file = Path(output_path)

    print(f"[CLIENT] Waiting for result at {output_path} (timeout: {timeout}s)")

    while time.time() - start_time < timeout:
        # Check if result file exists
        if output_file.exists():
            print(f"[CLIENT] Result file found after {time.time() - start_time:.1f}s")
            return True

        # Check tmux output for markers
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-100"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )

            output = result.stdout

            # Check for completion markers
            if RESULT_MARKER in output or ERROR_MARKER in output:
                # Wait a bit more for file write to complete
                time.sleep(0.5)
                if output_file.exists():
                    return True

            # Check for errors
            if "WARMUP_FAILED" in output:
                raise TmuxREPLError("LeanServer warmup failed")

        except subprocess.TimeoutExpired:
            print(f"[CLIENT] Warning: tmux capture timed out")
        except subprocess.CalledProcessError as e:
            print(f"[CLIENT] Warning: tmux capture failed: {e}")

        time.sleep(poll_interval)

    print(f"[CLIENT] Timeout after {timeout}s")
    return False


def capture_repl_output(session_name: str = SESSION_NAME, lines: int = 50) -> str:
    """Capture recent output from REPL"""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p", "-S", f"-{lines}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        return result.stdout
    except Exception as e:
        return f"Failed to capture output: {e}"


def execute_sorry_via_tmux(
    sorry_json: str,
    strategy_spec: str,
    output_path: str = "/tmp/result.json",
    timeout: int = 600
) -> dict:
    """
    Execute sorry via tmux REPL.

    Args:
        sorry_json: JSON string of Sorry object
        strategy_spec: JSON string of strategy spec
        output_path: Path to save result
        timeout: Execution timeout in seconds

    Returns:
        Result dictionary
    """
    print(f"[CLIENT] Starting execution via tmux session '{SESSION_NAME}'")

    # Validate inputs are valid JSON
    try:
        json.loads(sorry_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid sorry JSON: {e}")

    try:
        json.loads(strategy_spec) if strategy_spec else None
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid strategy spec JSON: {e}")

    # Escape for Python string
    sorry_escaped = json.dumps(sorry_json)
    strategy_escaped = json.dumps(strategy_spec)
    output_escaped = json.dumps(output_path)

    # Build Python command for REPL
    command = f"exec_and_save({sorry_escaped}, {strategy_escaped}, {output_escaped})"

    print(f"[CLIENT] Sending command to REPL")
    print(f"[CLIENT] Command length: {len(command)} chars")

    # Send command
    try:
        send_command_to_repl(command)
    except TmuxREPLError as e:
        raise TmuxREPLError(f"Failed to send command: {e}")

    # Wait for completion
    completed = wait_for_completion(output_path, timeout=timeout)

    if not completed:
        # Capture output for debugging
        output = capture_repl_output()
        raise TimeoutError(
            f"Execution timed out after {timeout}s\n"
            f"Recent REPL output:\n{output}"
        )

    # Read and return result
    result_text = Path(output_path).read_text()
    result_dict = json.loads(result_text)

    print(f"[CLIENT] Execution complete")
    print(f"[CLIENT] Proof verified: {result_dict.get('proof_verified', False)}")

    return result_dict


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Execute sorry via tmux REPL session"
    )
    parser.add_argument(
        "--sorry-json",
        type=str,
        required=True,
        help="JSON string of Sorry object"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        required=False,
        help="JSON string of strategy spec"
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="/root/repo/result.json",
        help="Path to save result JSON"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Execution timeout in seconds"
    )

    args = parser.parse_args()

    try:
        result = execute_sorry_via_tmux(
            args.sorry_json,
            args.strategy,
            args.output_path,
            args.timeout
        )

        # Print result to stdout for caller
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)

        # Try to capture REPL output for debugging
        try:
            output = capture_repl_output()
            print(f"\nREPL output:\n{output}", file=sys.stderr)
        except:
            pass

        sys.exit(1)

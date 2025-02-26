#!/usr/bin/env python3

import subprocess
import json
from pathlib import Path
from git import Repo
import time
import select

def setup_repl(lean_data: Path, version_tag: str | None = None) -> Path:
    """Clone and build the REPL repository.
    
    Args:
        lean_data: Path where the REPL should be cloned
        version_tag: Optional git tag to checkout. If None, uses latest version
    """
    repl_dir = lean_data / "repl"
    if not repl_dir.exists():
        print("Cloning REPL repository...")
        repo = Repo.clone_from(
            "https://github.com/leanprover-community/repl",
            repl_dir
        )
        
        if version_tag is not None:
            print(f"Checking out REPL at tag: {version_tag}")
            repo.git.checkout(version_tag)
        
        print("Building REPL...")
        result = subprocess.run(["lake", "build"], cwd=repl_dir)
        if result.returncode != 0:
            raise Exception("Failed to build REPL")
    
    repl_binary = repl_dir / ".lake" / "build" / "bin" / "repl"
    if not repl_binary.exists():
        raise Exception("REPL binary not found")
    
    # Make binary executable
    repl_binary.chmod(0o755)
    
    return repl_binary

class LeanRepl:
    """Interface to the Lean REPL."""
    
    def __init__(self, repo_path: Path, repl_binary: Path):
        """Start a new REPL process.
        
        Args:
            repo_path: Path to the repository root (used as working directory)
            repl_binary: Path to the REPL executable
        """
        print("  Starting REPL process...")
        print(f"  Working directory: {repo_path}")
        print(f"  REPL binary: {repl_binary.absolute()}")
        
        # Start the REPL in the project's environment
        cmd = ["lake", "env", str(repl_binary.absolute())]
        print(f"  Running command: {' '.join(cmd)}")
        
        self.process = subprocess.Popen(
            cmd,
            cwd=repo_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Check if process started successfully
        if self.process.poll() is not None:
            error = self.process.stderr.read()
            raise Exception(f"Failed to start REPL: {error}")
            
        print("  REPL process started successfully")
    
    def send_command(self, command: dict) -> dict | None:
        """Send a command to the REPL and get the response.
        
        Args:
            command: Dictionary containing the command to send
            
        Returns:
            Parsed JSON response or None if no response
            
        Raises:
            Exception if REPL process dies
        """
        try:
            print("  Sending command to REPL:", json.dumps(command))
            self.process.stdin.write(json.dumps(command) + "\n\n")
            self.process.stdin.flush()
            
            response = ""
            while True:
                if self.process.poll() is not None:
                    error = self.process.stderr.read()
                    raise Exception(f"REPL died: {error}")
                
                line = self.process.stdout.readline()
                if not line.strip():
                    break
                response += line
                print("  Got line from REPL:", line.strip())
            
            if response.strip():
                print("  Raw REPL response:", response.strip())
                return json.loads(response)
            else:
                print("  REPL returned empty response")
                return None
            
        except Exception as e:
            print(f"  Error sending command to REPL: {e}")
            # Try to get any stderr output
            error = self.process.stderr.read()
            if error:
                print(f"  REPL stderr: {error}")
            return None
    
    def close(self):
        """Terminate the REPL process."""
        try:
            self.process.terminate()
            self.process.wait(timeout=5)  # Wait up to 5 seconds for clean termination
        except subprocess.TimeoutExpired:
            self.process.kill()  # Force kill if it doesn't terminate cleanly
        finally:
            self.process.wait()  # Make sure process is fully cleaned up
    
    def __enter__(self):
        """Support for 'with' statement."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure REPL is closed when exiting 'with' block."""
        self.close()

def get_goal_parent_type(repl: LeanRepl, proof_state_id: int) -> str | None:
    """Get the parent type of the goal at a given proof state.
    
    Args:
        repl: An active REPL instance
        proof_state_id: The proofState identifier
        
    Returns:
        The parent type as a string, or None if failed
    """
    # Original tactic:
    # run_tac (do let parentType ← Lean.Meta.inferType (← Lean.Elab.Tactic.getMainTarget); Lean.logInfo m!"Goal parent type: {parentType}")
    
    command = {
        "tactic": "run_tac (do let parentType ← Lean.Meta.inferType (← Lean.Elab.Tactic.getMainTarget); Lean.logInfo m!\"Goal parent type: {parentType}\")", 
        "proofState": proof_state_id
    }
    response = repl.send_command(command)
    
    if response and "messages" in response:
        for msg in response["messages"]:
            if msg.get("severity") == "info" and "data" in msg:
                if "Goal parent type:" in msg["data"]:
                    return msg["data"].split("Goal parent type:", 1)[1].strip()
    
    return None


import json
from pathlib import Path
from pprint import pprint
import shutil

import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from sorrydb.repro.repl_api import LeanRepl, setup_repl
from sorrydb.crawler.git_ops import prepare_repository
from sorrydb.database.build_database import build_lean_project


class LLMClient:
    """LLMClient sets up Lean project and REPL, then attempts to solve it using an LLM.

    Args:
        sorry_file_path (str): Path to the sorry JSON file
        lean_data (str | None): Directory to store Lean data. Defaults to None (use temporary directory).
    """

    def __init__(self):
        # Load environment variables
        dotenv.load_dotenv()

        # Setup LLM
        self.model = ChatAnthropic(model="claude-3-7-sonnet-latest")

    def _invoke_model(self, prompt: str) -> str:
        """Invoke the LLM model with a given prompt.

        Args:
            prompt (str): Prompt to provide to the LLM model

        Returns:
            str: Response from the LLM model
        """
        response = self.model.invoke([HumanMessage(content=prompt)])
        return response.content

    def _setup_sorry(self, sorry_file_path: str):
        """Setup the sorry by reading the sorry JSON file, creating a Lean project, and starting the REPL.

        Args:
            sorry_file_path (str): Path to the sorry JSON file
        """
        # Load JSON data from sorry file
        with open(sorry_file_path) as f:
            sorry_data = json.load(f)
        self.sorry_data = sorry_data

        # Create temporary directory for Lean data. Clear if it already exists.
        lean_data = Path("temp_lean_dir")
        if lean_data.exists():
            shutil.rmtree(lean_data)
        else:
            lean_data.mkdir(exist_ok=True)

        # Setup Lean project and REPL
        self.repo_path = prepare_repository(
            sorry_data["remote_url"], sorry_data["branch"], sorry_data["sha"], lean_data
        )
        build_lean_project(self.repo_path)
        repl_binary = setup_repl(lean_data, sorry_data["lean_version"])
        self.repl = LeanRepl(self.repo_path, repl_binary)

    def solve(self, sorry_file_path: str) -> str | None:
        """Solve the sorry using the LLM.

        Returns:
            str | None: Solution to the sorry or None if not solved.
        """
        self._setup_sorry(sorry_file_path)

        location = self.sorry_data["location"]
        file_path = Path(self.repo_path, location["file"])
        file_text = file_path.read_text()

        # Create the prompt
        prompt = f"""You are an advanced AI that has studied all known mathematics. Solve the following proof:

Proof Goal:
```lean
{self.sorry_data["goal"]["type"]}
```

Lean Code:
```lean
{file_text}
```

Write Lean 4 code to replace the sorry at line {location["startLine"]}, column {location["startColumn"]}.

No comments, no explanations, just write code.
Do not re-state the theorem. 
Only write exactly the code that you would replace the sorry with.
"""

        # Invoke the LLM to solve the proof
        solution = self._invoke_model(prompt)

        # Check the solution using the REPL
        reply = self.repl.send_command({"cmd": file_text})
        sorry = [
            s
            for s in reply["sorries"]
            if s["pos"]["line"] == location["startLine"]
            and s["pos"]["column"] == location["startColumn"]
        ][0]

        proof_state = sorry["proofState"]
        for tactic in solution.split("/n"):
            reply = self.repl.send_command(
                {"tactic": tactic, "proofState": proof_state}
            )
            if "proofState" in reply:
                proof_state = reply["proofState"]
            else:
                print(
                    f"Failed to apply tactic.\nLLM solution: {solution}\nCurrent tactic: {tactic}\nREPL reply: {reply}"
                )
                return None

        if reply["goals"] == []:
            return solution

        print(f"Failed to solve sorry. Remaining goals:\n{reply['goals']}")
        return None

    def close(self):
        """Close the REPL."""
        self.repl.close()

import json
from pathlib import Path
from pprint import pprint
import shutil

import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
import requests

from sorrydb.repro.repl_api import LeanRepl, setup_repl
from sorrydb.crawler.git_ops import prepare_repository
from sorrydb.database.build_database import build_lean_project


PROMPT = """You are an advanced AI that has studied all known mathematics. Solve the following proof:

Proof Goal:
```lean
{goal}
```

Lean Code:
```lean
{file_text}
```

Write Lean 4 code to replace the sorry at line {line}, column {column}.

No comments, no explanations, just write code.
Do not re-state the theorem, do not start with "by".
Only write exactly the code that you would replace the sorry with.
"""


class LLMClient:
    """LLMClient sets up Lean project and REPL, then attempts to solve it using an LLM.

    Example model JSON:
    ```json
        {
            "provider": "anthropic",
            "cost": [3, 15],  # $/1M tokens: Input, output
            "params": {"model": "claude-3-7-sonnet-latest"},
        }
    ```

    Args:
        model_json (str | None): Path to the model config JSON. Defaults to None.
        lean_dir (str): Directory to store Lean data. Defaults to "lean_data".
    """

    def __init__(self, model_json: str = None, lean_dir: str = "lean_data"):
        # Load environment variables
        dotenv.load_dotenv()

        # Load model config
        if model_json is None:
            model_config = {
                "provider": "anthropic",
                "cost": [3, 15],
                "params": {"model": "claude-3-7-sonnet-latest"},
            }
        else:
            with open(model_json) as f:
                model_config = json.load(f)
        self.model_config = model_config

        # Setup LLM
        if model_config["provider"] == "anthropic":
            self.model = ChatAnthropic(**model_config["params"])
        elif model_config["provider"] == "openai":
            self.model = ChatOpenAI(**model_config["params"])
        elif model_config["provider"] == "google":
            self.model = ChatGoogleGenerativeAI(**model_config["params"])
        else:
            raise ValueError(f"Invalid model provider: {model_config['provider']}")

        # Create lean directory if it doesn't exist
        self.lean_dir = Path(lean_dir)
        self.lean_dir.mkdir(exist_ok=True)

        # Keep track of token usage
        self.token_usage = [0, 0]

    def _invoke_model(self, prompt: str) -> str:
        """Invoke the LLM model with a given prompt.

        Args:
            prompt (str): Prompt to provide to the LLM model

        Returns:
            str: Response from the LLM model
        """
        response = self.model.invoke([HumanMessage(content=prompt)])
        usage = response.response_metadata["usage"]
        self.token_usage[0] += usage["input_tokens"]
        self.token_usage[1] += usage["output_tokens"]
        return response.content

    def _setup_repo(self, remote_url: str, branch: str, sha: str, lean_version: str):
        """Prepare repo, create a Lean project, and setup the REPL.

        Args:
            remote_url (str): URL of the remote repository
            branch (str): Branch name
            sha (str): Commit SHA
            lean_version (str): Lean version
        """
        self.repo_path = prepare_repository(remote_url, branch, sha, self.lean_dir)
        build_lean_project(self.repo_path)
        repl_binary = setup_repl(self.lean_dir, lean_version)
        self.repl = LeanRepl(self.repo_path, repl_binary)

    def _check_proof(
        self, file_text: str, line: int, column: int, proof: list[str]
    ) -> bool:
        """Check the proof using the REPL.

        Args:
            file_text (str): Lean code
            line (int): Line number of the sorry
            column (int): Column number of the sorry
            proof (list[str]): Proof to check, as list of tactics

        Returns:
            bool: Does the proof solve the sorry?
        """
        reply = self.repl.send_command({"cmd": file_text})
        for s in reply["sorries"]:
            if s["pos"]["line"] == line and s["pos"]["column"] == column:
                sorry = s
                break
        else:
            raise ValueError("Sorry not found in REPL reply")

        proof_state = sorry["proofState"]
        for tactic in proof:
            cmd = {"tactic": tactic, "proofState": proof_state}
            reply = self.repl.send_command(cmd)
            if "proofState" in reply:
                proof_state = reply["proofState"]
            else:
                msg = (
                    f"Failed to apply tactic.\nLLM proof:\n{proof}\nREPL reply: {reply}"
                )
                print(msg)
                return False

        if reply["goals"] == []:
            return True

        print(f"Failed to solve sorry. Remaining goals:\n{reply['goals']}")
        return False

    def _solve_sorry(self, sorry_config: dict) -> list[str] | None:
        """Solve the sorry using the LLM model.

        Returns:
            list[str] | None: Proof (list of tactics) or None if not solved.
        """
        loc = sorry_config["location"]
        file_path = Path(self.repo_path, loc["file"])
        file_text = file_path.read_text()

        # Render the prompt
        prompt = PROMPT.format(
            goal=sorry_config["goal"]["type"],
            file_text=file_text,
            line=loc["startLine"],
            column=loc["startColumn"],
        )

        # Run the prompt, check the proof
        proof = self._invoke_model(prompt)
        if self._check_proof(file_text, loc["startLine"], loc["startColumn"], proof):
            return proof
        return None

    def solve_sorry_db(self, sorry_db_url: str, out_json: str):
        """Run all sorries in the sorry DB

        Args:
            sorry_db_url (str): URL of the sorry DB
            out_json (str): Path to the output JSON file
        """
        sorry_db = json.loads(requests.get(sorry_db_url).text)

        # Confirm with user
        # num_repos = len(sorry_db["repos"])
        # num_sorries = sum(
        #     len(
        #         [s for s in c["sorries"] if s["goal"].get("parentType", None) == "Prop"]
        #     )
        #     for r in sorry_db["repos"]
        #     for c in r["commits"]
        # )
        # print(f"Attempting to solve {num_sorries} sorries in {num_repos} repos.")
        # print("Continue? (y/N)")
        # if input().lower() != "y":
        #     return

        llm_proofs = {}
        for i_repo, repo in enumerate(sorry_db["repos"]):
            for commit in repo["commits"]:

                sorries = [
                    s for s in commit["sorries"] if s["goal"]["parentType"] == "Prop"
                ]
                if not sorries:
                    continue

                self._setup_repo(
                    repo["remote_url"],
                    commit["branch"],
                    commit["sha"],
                    commit["lean_version"],
                )

                for sorry in sorries:
                    llm_proofs[sorry["uuid"]] = self._solve_sorry(sorry)
                    print("Total cost: $%.2f $" % self.get_cost())

                    # DEBUG: End after the first model call
                    break
                break
            if llm_proofs:
                break
        print("DEBUG: Ending after first sorry attempt.")

        with open(out_json, "w") as f:
            json.dump(llm_proofs, f)

    def get_cost(self):
        """Get the total cost of using the model.

        Returns:
            float: Total model usage in $
        """
        return sum(
            t * c / 1e6 for t, c in zip(self.token_usage, self.model_config["cost"])
        )

    def close(self):
        """Always close the client when you're done!"""
        self.repl.close()

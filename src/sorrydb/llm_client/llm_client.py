import json
import logging
from pathlib import Path
from pprint import pprint
import time

import dotenv
import requests
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from sorrydb.repro.repl_api import LeanRepl, setup_repl
from sorrydb.crawler.git_ops import prepare_repository
from sorrydb.database.build_database import build_lean_project


# EXAMPLE PROMPTS IN LITERATURE
# https://github.com/cmu-l3/llmlean/blob/77448d68e51166f60bd43c6284b43d65209321b0/LLMlean/API.lean#L258
# https://plmlab.math.cnrs.fr/nuccio/octonions/-/blob/c3569703fd17191c279908509b8845735d5c507e/Mathlib/Tactic/GPT/Sagredo/Dialog.lean
# https://github.com/GasStationManager/LeanTool/blob/main/leantool.py
# https://github.com/quinn-dougherty/fvapps/blob/master/src/baselines/baselines_config.py
# https://github.com/Goedel-LM/Goedel-Prover/blob/5988bb0e3650f0417b61da4b10885e7ad6ca75fc/prover/utils.py#L23
# https://github.com/lean-dojo/LeanCopilot/blob/e2aebdab8e9b1c74a5334b36ba2c288c5a5f175d/python/external_models/hf_runner.py#L41
# https://github.com/oOo0oOo/lean-scribe/blob/main/default_scribe_folder/default_prompts/progress_in_proof.md


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

You cannot import any additional libraries to the ones already imported in the file.
Write a short, simple and elegant proof.
Do not re-state the theorem or "by".
If you conclude that the sorry is not provable, explain why in a short comment.
Do NOT WRITE ANY COMMENTS OR EXPLANATIONS! Just write code!
Only write the code that you would replace the sorry with!
"""


logger = logging.getLogger(__name__)


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
        logger.info("LLM response:\n" + response.content)
        return response.content

    def _setup_repo(
        self, remote_url: str, branch: str, sha: str, lean_version: str
    ) -> bool:
        """Prepare repo, create a Lean project, and setup the REPL.

        Args:
            remote_url (str): URL of the remote repository
            branch (str): Branch name
            sha (str): Commit SHA
            lean_version (str): Lean version

        Returns:
            bool: True if setup was successful
        """
        try:
            self.repo_path = prepare_repository(remote_url, branch, sha, self.lean_dir)
            if self.repo_path is None:
                return False
            build_lean_project(self.repo_path)
            self.repl_binary = setup_repl(self.lean_dir, lean_version)
        except:
            return False
        return True

    def _split_proof(self, proof: str) -> list[str]:
        """Process and split the proof into a list of tactics.

        Removes base indentation, then splits into tactics based on indentation.

        Args:
            proof (str): Proof as a string

        Returns:
            list[str]: Proof as a list of tactics
        """
        # Extract code from ```lean ``` code block if it is present
        if "```lean" in proof:
            proof = proof.split("```lean")[1].split("```")[0]

        lines = proof.split("\n")
        if lines[0].strip() == "by":
            lines = lines[1:]

        # Remove empty lines and base indentation
        lines = [line for line in lines if line.strip()]
        indent = [len(line) - len(line.lstrip()) for line in lines]
        lines = [line[indent[0] :] for line in lines]

        # Check if first line has different indentation than the rest
        # This is usually due to the indentation of the sorry being replaced.
        if len(set(indent)) > 1:
            to_remove = min(indent[1:])
            if to_remove > 0:
                # This is only allowed if first line:
                # - Ends with by
                # - Is refine
                if not (
                    lines[0].strip().endswith("by") or lines[0].strip() == "refine"
                ):
                    # Remove indentation of all following lines
                    lines = [lines[0]] + [line[to_remove:] for line in lines[1:]]

        tactics = []
        for line in lines:
            # Remove trailing ;
            if line.endswith(";"):
                line = line[:-1]

            # Tactic is a group of lines until 0 indentation
            indent = len(line) - len(line.lstrip())
            if indent == 0:
                tactics.append(line)
            else:
                tactics[-1] += "\n" + line

        return tactics

    def _check_proof(
        self, file_text: str, line: int, column: int, proof: list[str]
    ) -> str | None:
        """Check the proof using the REPL.

        Args:
            file_text (str): Lean code
            line (int): Line number of the sorry
            column (int): Column number of the sorry
            proof (list[str]): Proof to check, as list of tactics

        Returns:
            str | None: Proof or None if not solved
        """
        with LeanRepl(self.repo_path, self.repl_binary) as repl:
            reply = repl.send_command({"cmd": file_text})
            if reply is None:
                return None

            for s in reply["sorries"]:
                if s["pos"]["line"] == line and s["pos"]["column"] == column:
                    sorry = s
                    break
            else:
                msg = f"Sorry not found in code!\nREPL reply:\n{reply}"
                logger.info(msg)
                return None

            proof_state = sorry["proofState"]

            complete_proof = []
            for tactic in proof:
                cmd = {"tactic": tactic, "proofState": proof_state}
                reply = repl.send_command(cmd)

                # Check for error messages
                for message in reply.get("messages", []):
                    if message["severity"] == "error":
                        msg = f"REPL error running tactic:\n{tactic}\nREPL:\n{reply}"
                        logger.info(msg)
                        return None

                if "proofState" not in reply:
                    msg = f"No proof state in reply:\n{reply}"
                    logger.info(msg)
                    return None

                complete_proof.append(tactic)
                proof_state = reply["proofState"]

        if reply["goals"] == []:
            return "\n".join(complete_proof)

        msg = f"Failed to solve sorry. Remaining goals:\n{reply['goals']}"
        logger.info(msg)
        return None

    def _solve_sorry(self, sorry_config: dict) -> str | None:
        """Solve the sorry using the LLM model.

        Returns:
            str | None: Proof (list of tactics) or None if not solved.
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
        proof = self._split_proof(proof)
        return self._check_proof(file_text, loc["startLine"], loc["startColumn"], proof)

    def solve_sorry_db(self, sorry_db_url: str, out_json: str):
        """Run all sorries in the sorry DB

        Args:
            sorry_db_url (str): URL of the sorry DB
            out_json (str): Path to the output JSON file
        """
        sorry_db = json.loads(requests.get(sorry_db_url).text)

        num_repos = len(sorry_db["repos"])
        num_sorries = sum(
            len(c["sorries"]) for r in sorry_db["repos"] for c in r["commits"]
        )
        logger.info(f"Attempting to solve {num_sorries} sorries in {num_repos} repos.")

        # # Confirm with user
        # print("Continue? (y/N)")
        # if input().lower() != "y":
        #     return

        t0 = time.time()

        llm_proofs = {}
        for i_repo, repo in enumerate(sorry_db["repos"]):
            logger.info(f"Repo {i_repo+1}/{num_repos}: {repo['remote_url']}")
            for commit in repo["commits"]:

                sorries = [
                    s for s in commit["sorries"] if s["goal"]["parentType"] == "Prop"
                ]
                if not sorries:
                    continue

                success = self._setup_repo(
                    repo["remote_url"],
                    commit["branch"],
                    commit["sha"],
                    commit["lean_version"],
                )

                if not success:
                    logger.error("Failed to setup repo.")
                    continue

                for sorry in sorries:
                    logger.info(f"Attempting sorry {sorry['uuid']}")
                    llm_proofs[sorry["uuid"]] = self._solve_sorry(sorry)
                    logger.info(f"Total model cost: $%.2f $" % self.get_cost())

                    with open(out_json, "w") as f:
                        json.dump(llm_proofs, f)

        msg = f"Solved {len([p for p in llm_proofs.values() if p])} / {len(llm_proofs)} sorries in {(time.time() - t0)/60:.2f} minutes."
        logger.info(msg)
        msg = f"Total token usage: {self.token_usage[0]} input, {self.token_usage[1]} output"
        logger.info(msg)

    def get_cost(self):
        """Get the total cost of using the model.

        Returns:
            float: Total model usage in $
        """
        return sum(
            t * c / 1e6 for t, c in zip(self.token_usage, self.model_config["cost"])
        )

import json
import logging
from pathlib import Path
from typing import Dict

import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.database.sorry import Sorry


# EXAMPLE PROMPTS IN LITERATURE
# https://github.com/cmu-l3/llmlean/blob/77448d68e51166f60bd43c6284b43d65209321b0/LLMlean/API.lean#L258
# https://plmlab.math.cnrs.fr/nuccio/octonions/-/blob/c3569703fd17191c279908509b8845735d5c507e/Mathlib/Tactic/GPT/Sagredo/Dialog.lean
# https://github.com/GasStationManager/LeanTool/blob/main/leantool.py
# https://github.com/quinn-dougherty/fvapps/blob/master/src/baselines/baselines_config.py
# https://github.com/Goedel-LM/Goedel-Prover/blob/5988bb0e3650f0417b61da4b10885e7ad6ca75fc/prover/utils.py#L23
# https://github.com/lean-dojo/LeanCopilot/blob/e2aebdab8e9b1c74a5334b36ba2c288c5a5f175d/python/external_models/hf_runner.py#L41
# https://github.com/oOo0oOo/lean-scribe/blob/main/default_scribe_folder/default_prompts/progress_in_proof.md


PROMPT = """You are an advanced AI that has studied all known mathematics.
Consider the following Lean code:

```lean
{context}
```

The final line contains a sorry at column {column}. It's proof goal is

```lean
{goal}
```

Write Lean 4 code to exactly replace "sorry" with a proof of the goal above.

You cannot import any additional libraries to the ones already imported in the file.
Write a short, simple and elegant proof.
Do not re-state the theorem or "by".
ONLY WRITE EXACTLY THE CODE TO REPLACE THE SORRY, including indentation.
DO NOT WRITE ANY COMMENTS OR EXPLANATIONS! Just write code!
"""

logger = logging.getLogger(__name__)


class LLMStrategy(SorryStrategy):
    """LLMStrategy implements the SorryStrategy protocol using an LLM to generate proofs.

    Args:
        model_config: Dictionary containing:
            - provider: "anthropic", "openai", or "google"
            - cost: [input_cost, output_cost] in $/1M tokens
            - params: Model-specific parameters
    """

    def __init__(self, model_config: Dict | None = None):
        # Load environment variables
        dotenv.load_dotenv()

        # Load model config
        if model_config is None:
            model_config = {
                "provider": "anthropic",
                "cost": [3, 15],
                "params": {"model": "claude-3-7-sonnet-latest"},
            }
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

    def _preprocess_proof(self, proof: str, base_indentation: int) -> str:
        """Process the proof to increase the chance of success.

        Args:
            proof: Proof as a string
            base_indentation: Base indentation level of the sorry

        Returns:
            Processed proof
        """
        # Extract code from ```lean ``` code block if it is present
        if "```lean" in proof:
            proof = proof.split("```lean")[1].split("```")[0]

        # Remove "by" at the beginning of the proof
        if proof.startswith("by"):
            proof = proof[2:]

        # Remove empty lines and base indentation
        lines = [line for line in proof.split("\n") if line.strip()]
        
        if not lines:
            return ""

        # First line is never indented
        lines[0] = lines[0].lstrip()

        # If we only have one line, just return it
        if len(lines) == 1:
            return lines[0]

        # Second line is only indented more than base indentation if:
        # - Ends with by
        # - Is refine
        expected_indentation = base_indentation
        if lines[0].endswith("by") or lines[0].strip() == "refine":
            expected_indentation += 2

        # Assume all following lines are indented the same
        actual_indentation = len(lines[1]) - len(lines[1].lstrip())
        difference = actual_indentation - expected_indentation
        if difference < 0:
            # Increase indentation of all lines
            lines = [lines[0]] + ["  " * abs(difference) + line for line in lines[1:]]
        elif difference > 0:
            # Decrease indentation of all lines
            lines = [lines[0]] + [line[difference:] for line in lines[1:]]

        return "\n".join(lines)

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Attempt to prove a sorry using the LLM.

        Args:
            repo_path: Path to the repository
            sorry: Dictionary containing sorry information

        Returns:
            Proof string or None if no proof was found
        """
        # Load the file and render the prompt
        loc = sorry.location
        file_path = repo_path / loc.path
        file_text = file_path.read_text()

        # Extract the context up to the sorry line
        context_lines = file_text.splitlines()[:loc.start_line]
        context = "\n".join(context_lines)
        
        prompt = PROMPT.format(
            goal=sorry.debug_info.goal,
            context=context,
            column=loc.start_column,
        )

        # Run the prompt
        logger.info("Prompting LLM")
        response = self.model.invoke([HumanMessage(content=prompt)])
        proof = response.content

        # Process the proof
        processed = self._preprocess_proof(proof, loc.start_column)
        logger.info(f"Generated proof: {processed}")

        return processed

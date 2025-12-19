import difflib
import logging
from pathlib import Path
from typing import Dict
from os import getenv
import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from sorrydb.runners.json_runner import SorryStrategy
from sorrydb.database.sorry import Location, Sorry
from sorrydb.utils.verify_lean_interact import position_to_index

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

The final line contains a sorry at column {column}. Its proof goal is

```lean
{goal}
```

Replace the sorry with a valid proof. 
Output the ENTIRE code block above inside a ```lean block with ONLY the sorry replaced.
Do not modify anything else - no formatting changes, no whitespace changes, no other edits.
You cannot import any additional libraries.
Write a short, simple and elegant proof.
DO NOT WRITE ANY COMMENTS OR EXPLANATIONS! Just output the modified code block.
If there are other thoughts or explanations, the last code block will be considered as the answer.
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
                "params": {"model": "claude-4-5-sonnet-latest"},
            }
        self.model_config = model_config

        # Setup LLM
        if model_config["provider"] == "anthropic":
            self.model = ChatAnthropic(**model_config["params"])
        elif model_config["provider"] == "openai":
            self.model = ChatOpenAI(**model_config["params"])
        elif model_config["provider"] == "google":
            self.model = ChatGoogleGenerativeAI(**model_config["params"])
        elif model_config["provider"] == "deepseek":
            self.model = ChatOpenAI(
                api_key=getenv("OPENROUTER_API_KEY"),
                base_url="https://openrouter.ai/api/v1",
                model="deepseek/deepseek-prover-v2",
            )
            # TODO: we may want to update the PROMPT
        elif model_config["provider"] == "kimina":
            if getenv("HUGGINGFACE_API_KEY"):
                logger.info("HUGGINGFACE_API_KEY is set.")
            else:
                logger.warning("HUGGINGFACE_API_KEY is not set.")
            self.model = ChatOpenAI(
                api_key=getenv("HUGGINGFACE_API_KEY"),
                base_url="https://router.huggingface.co/v1",
                model="AI-MO/Kimina-Prover-72B:featherless-ai",
            )
        else:
            raise ValueError(f"Invalid model provider: {model_config['provider']}")

    def _extract_proof_from_diff(
        self, original: str, llm_output: str, location: Location
    ) -> str | None:
        """Extract the proof that replaced 'sorry' by diffing original vs LLM output."""
        # Strip markdown code blocks
        if "```lean" in llm_output:
            llm_output = llm_output.split("```lean")[-1].split("```")[0]
        llm_output = llm_output.strip("`").strip()

        sorry_start = position_to_index(original, location.start_line, location.start_column)
        sorry_end = position_to_index(original, location.end_line, location.end_column)

        matcher = difflib.SequenceMatcher(None, original, llm_output, autojunk=False)
        blocks = matcher.get_matching_blocks()

        # Find blocks before and after the sorry position
        block_before = None
        block_after = None

        for i, j, n in blocks:
            if i + n <= sorry_start:
                block_before = (i, j, n)
            if i >= sorry_end and block_after is None:
                block_after = (i, j, n)
                break

        if block_before is None or block_after is None:
            return None

        # Extract proof: from end of block_before to start of block_after in llm_output
        proof_start = block_before[1] + block_before[2]
        proof_end = block_after[1]

        # Look back past spaces/tabs for a newline and include it
        i = proof_start - 1
        while i >= 0 and llm_output[i] in " \t":
            i -= 1
        if i >= 0 and llm_output[i] == "\n":
            proof_start = i

        return llm_output[proof_start:proof_end]

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
        context_lines = file_text.splitlines()[: loc.start_line]
        context = "\n".join(context_lines)

        prompt = PROMPT.format(
            goal=sorry.debug_info.goal,
            context=context,
            column=loc.start_column,
        )

        # Run the prompt
        logger.info("Prompting LLM")
        response = self.model.invoke([HumanMessage(content=prompt)])

        # Log the full raw LLM response for debugging
        logger.info(f"Full LLM response:\n{response.content}")

        # Extract proof using diff
        proof = self._extract_proof_from_diff(context, response.content, loc)
        logger.info(f"Extracted proof: {proof}")

        return proof

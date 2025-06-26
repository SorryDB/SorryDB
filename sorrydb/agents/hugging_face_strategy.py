import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Protocol

from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.agents.llm_proof_utils import (
    NO_CONTEXT_PROMPT,
    extract_proof_from_code_block,
    extract_proof_from_full_theorem_statement,
)
from sorrydb.database.sorry import Sorry, SorryJSONEncoder

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    def predict(self, prompt: str) -> str:
        """Make a prediction using the LLM"""
        ...


@dataclass
class LLMResponseDebugInfo:
    prompt: str
    raw_llm_response: Optional[str] = None
    post_processed_response: Optional[str] = None
    intermediate_steps: Optional[dict] = None
    sagemaker_exception: Optional[dict] = None


class DebugManager:
    def __init__(self, debug_info_path: Optional[Path] = None):
        self.debug_info_path = debug_info_path
        self.all_debug_info = []
        if self.debug_info_path:
            with open(self.debug_info_path, "w") as f:
                json.dump({}, f)

    def save_debug_info(self, debug_info: LLMResponseDebugInfo):
        self.all_debug_info.append(asdict(debug_info))
        if self.debug_info_path:
            try:
                with open(self.debug_info_path, "w") as f:
                    json.dump(self.all_debug_info, f, indent=4, cls=SorryJSONEncoder)
            except Exception as e:
                logger.error(f"Error saving proofs to {self.debug_info_path}: {e}")
                raise


def extract_context(repo_path: Path, sorry: Sorry) -> tuple[str, str]:
    loc = sorry.location
    file_path = repo_path / loc.path
    file_text = file_path.read_text()

    lines = file_text.splitlines()
    top_context_lines = lines[:50]
    pre_sorry_context_lines = lines[max(0, loc.start_line - 20) : loc.start_line]
    context_top = "\n".join(top_context_lines)
    context_pre_sorry = "\n".join(pre_sorry_context_lines)

    return context_top, context_pre_sorry


class UnifiedHuggingFaceStrategy(SorryStrategy):
    def __init__(
        self, llm_provider: LLMProvider, debug_info_path: Optional[Path] = None
    ):
        self.llm_provider = llm_provider
        self.debug_manager = DebugManager(debug_info_path)

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        context_top, context_pre_sorry = extract_context(repo_path, sorry)
        prompt = NO_CONTEXT_PROMPT.format(
            goal=sorry.debug_info.goal,
            context_pre_sorry=context_pre_sorry,
            column=sorry.location.start_column,
        )

        try:
            raw_llm_response = self.llm_provider.predict(prompt)
        except Exception as e:
            debug_info = LLMResponseDebugInfo(
                prompt=prompt,
                sagemaker_exception={"type": type(e).__name__, "message": str(e)},
            )
            self.debug_manager.save_debug_info(debug_info)
            return None

        processed_proof, intermediate_steps = deepseek_post_processing(
            raw_llm_response, sorry.location.start_column
        )

        debug_info = LLMResponseDebugInfo(
            prompt=prompt,
            raw_llm_response=raw_llm_response,
            post_processed_response=processed_proof,
            intermediate_steps=intermediate_steps,
        )

        self.debug_manager.save_debug_info(debug_info)
        return processed_proof


def deepseek_post_processing(
    raw_llm_response: str, start_column: int
) -> tuple[str, dict]:
    intermediate_processing_steps = {}
    # Process the proof
    # If the proof given includes the theorm statement
    # extract just the proof that will replace the sorry
    extracted_proof = extract_proof_from_code_block(raw_llm_response)
    intermediate_processing_steps["extracted_proof"] = extracted_proof
    logger.info(f"Extacted proof: {extracted_proof}")
    no_theorem_statement_proof = extract_proof_from_full_theorem_statement(
        extracted_proof
    )
    logger.info(f"No theorem statement proof: {no_theorem_statement_proof}")
    intermediate_processing_steps["no_theorem_statement_proof"] = (
        no_theorem_statement_proof
    )
    # TODO: consider removing this one as it can produce extra indentation
    # UPDATE: For now I am going to remove this
    # processed_proof = preprocess_proof(no_theorem_statement_proof, start_column)
    processed_proof = no_theorem_statement_proof

    intermediate_processing_steps["processed_proof"] = processed_proof
    logger.info(f"Fully processed proof: {processed_proof}")
    logger.info(f"Generated proof: {processed_proof}")
    return processed_proof, intermediate_processing_steps

import json
import logging
from pathlib import Path
from typing import Optional, Protocol

from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.agents.llm_proof_utils import (
    deepseek_post_processing,
    extract_context,
)
from sorrydb.database.sorry import Sorry, SorryJSONEncoder

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    """Interface between CloudLLMStrategy and the cloud providers that provide LLM infrastructure"""

    def predict(self, prompt: str) -> str:
        """Make a prediction using the LLM"""
        ...


class CloudLLMDebugManager:
    def __init__(self, debug_info_path: Optional[Path] = None):
        self.debug_info_path = debug_info_path
        self.all_debug_info = []
        if self.debug_info_path:
            with open(self.debug_info_path, "w") as f:
                json.dump({}, f)

    def save_debug_info(
        self,
        prompt: str,
        raw_llm_response: Optional[str] = None,
        post_processed_response: Optional[str] = None,
        intermediate_steps: Optional[dict] = None,
        exception: Optional[dict] = None,
    ):
        debug_info = {
            "prompt": prompt,
            "raw_llm_response": raw_llm_response,
            "post_processed_response": post_processed_response,
            "intermediate_steps": intermediate_steps,
            "exception": exception,
        }
        self.all_debug_info.append(debug_info)
        if self.debug_info_path:
            try:
                with open(self.debug_info_path, "w") as f:
                    json.dump(self.all_debug_info, f, indent=4, cls=SorryJSONEncoder)
            except Exception as e:
                logger.error(f"Error saving proofs to {self.debug_info_path}: {e}")
                raise
        return debug_info


class CloudLLMStrategy(SorryStrategy):
    def __init__(
        self,
        llm_provider: LLMProvider,
        prompt: str,
        debug_info_path: Optional[Path] = None,
    ):
        self.llm_provider = llm_provider
        self.debug_manager = CloudLLMDebugManager(debug_info_path)
        self.debug_info = None
        self.prompt = prompt

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        _, context_pre_sorry = extract_context(repo_path, sorry)
        # TODO: This should be refactored out into a SorryPromptBuilder class or something
        prompt = self.prompt.format(
            goal=sorry.debug_info.goal,
            context_pre_sorry=context_pre_sorry,
            column=sorry.location.start_column,
        )

        try:
            raw_llm_response = self.llm_provider.predict(prompt)
        except Exception as e:
            self.debug_manager.save_debug_info(
                prompt=prompt,
                exception={"type": type(e).__name__, "message": str(e)},
            )
            return None

        # We have harded coded the deepseek post processing function.
        # We may want to parameterize the CloudLLMStrategy by the post processing function
        # as different models will likely need different post processing
        processed_proof, intermediate_steps = deepseek_post_processing(
            raw_llm_response,
        )

        self.debug_info = self.debug_manager.save_debug_info(
            prompt=prompt,
            raw_llm_response=raw_llm_response,
            post_processed_response=processed_proof,
            intermediate_steps=intermediate_steps,
        )
        return processed_proof

    def get_debug_info(self):
        return self.debug_info

    def __str__(self):
        return f"{self.llm_provider.__class__.__name__} CloudLLMStrategy"

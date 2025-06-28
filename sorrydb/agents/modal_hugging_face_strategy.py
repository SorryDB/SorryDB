import logging

from sorrydb.agents.cloud_llm_strategy import LLMProvider
from sorrydb.agents.modal_app import try_sorry_pipeline

logger = logging.getLogger(__name__)


class ModalLLMProvider(LLMProvider):
    def predict(self, prompt: str) -> str:
        return try_sorry_pipeline.remote(prompt)

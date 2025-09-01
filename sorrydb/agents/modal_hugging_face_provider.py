import logging

from sorrydb.agents.cloud_llm_strategy import LLMProvider
from sorrydb.agents.modal_app import KiminaSorrySolver, solve_sorry_deepseek

logger = logging.getLogger(__name__)


class ModalDeepseekProverLLMProvider(LLMProvider):
    def predict(self, prompt: str) -> str:
        logger.info("Sending prompt to DeepseekProver Modal app")
        response = solve_sorry_deepseek.remote(prompt)
        logger.info("Recieved response from modal app")
        return response


class ModalKiminaLLMProvider(LLMProvider):
    def __init__(self):
        self.kimina_solver = KiminaSorrySolver()

    def predict(self, prompt: str) -> str:
        logger.info("Sending prompt to Kimina in Modal app")
        response = self.kimina_solver.predict.remote(prompt)
        logger.info("Recieved response from modal app")
        return response

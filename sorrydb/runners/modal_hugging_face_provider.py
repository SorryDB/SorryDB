import logging

from sorrydb.strategies.cloud_llm_strategy import LLMProvider
from sorrydb.runners.modal_app import solve_sorry_kimina, solve_sorry_deepseek

logger = logging.getLogger(__name__)


class ModalDeepseekProverLLMProvider(LLMProvider):
    def predict(self, prompt: str) -> str:
        logger.info("Sending prompt to DeepseekProver Modal app")
        response = solve_sorry_deepseek.remote(prompt)
        logger.info("Recieved response from modal app")
        return response


class ModalKiminaLLMProvider(LLMProvider):
    def __init__(self):
        # self.kimina_solver = KiminaSorrySolver()
        pass

    def predict(self, prompt: str) -> str:
        logger.info("Sending prompt to Kimina in Modal app")
        response = solve_sorry_kimina.remote(prompt)
        logger.info("Recieved response from modal app")
        return response

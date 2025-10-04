import logging
from google.cloud import aiplatform

from sorrydb.agents.cloud_llm_strategy import LLMProvider

logger = logging.getLogger(__name__)

PROJECT_ID  = "ax-research"
REGION      = "us-central1"
ENDPOINT_ID = "7497010138386006016"

class GoogleVertexLLMProvider(LLMProvider):
    def predict(self, prompt: str) -> str:
        logger.info("Sending theorem to Google Vertex")
        try:
            aiplatform.init(project=PROJECT_ID, location=REGION)
            endpoint = aiplatform.Endpoint(ENDPOINT_ID)
        except Exception as e:
            logger.info(f"Error getting endpoint: {e}")
        
        prompt = f"Complete the following theorem in Lean4\n\n{prompt}"
        instances = [{"prompt": prompt, "max_tokens": 50000}]
        parameters = {}
        
        try:
            response = endpoint.predict(instances=instances, parameters=parameters)
            full_response = response.predictions[0]
            logger.info(f"Recieved response from Google Vertex: {full_response}")
            if "Output:" in full_response:
                return full_response.split("Output:", 1)[1].strip()
            return full_response
        except Exception as e:
            logger.info(f"Error calling model: {e}")








if __name__ == "__main__":

    lean_code = """
    theorem simple_add : 2 + 2 = 4 := by
    sorry
    """
    
    proof = call_deepseek_prover(lean_code)
    print("Generated proof:")
    print(proof)

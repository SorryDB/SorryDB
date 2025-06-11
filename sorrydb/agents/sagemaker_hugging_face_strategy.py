import logging
from pathlib import Path

import boto3
from sagemaker.huggingface.llm_utils import get_huggingface_llm_image_uri
from sagemaker.huggingface.model import HuggingFaceModel
from transformers import AutoTokenizer

from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.agents.llm_proof_utils import PROMPT, preprocess_proof
from sorrydb.database.sorry import Sorry

# Configuration defaults
# TODO: We should parameterize the strategy by some or all of these
AWS_REGION = "us-east-1"
IAM_ROLE_NAME = "AmazonSageMaker-ExecutionRole-20250610T153494"
INSTANCE_TYPE = "ml.g5.xlarge"

# Model must be supported by [Hugging Face TGI](https://huggingface.co/docs/text-generation-inference/en/index).
# I believe DeepSeek Prover works because it has the same underlying architecture as DeepSeek-V3, which is supported.
HF_MODEL_ID = "deepseek-ai/DeepSeek-Prover-V2-7B"
# Possible Quanitzation values for TGI [here](https://huggingface.co/docs/text-generation-inference/en/basic_tutorials/launcher#quantize)
# e.g. `QUANTIZE = "bitsandbytes" for an 8bit quantization`
QUANTIZE = None


logger = logging.getLogger(__name__)


class SagemakerHuggingFaceStrategy(SorryStrategy):
    """SagemakerStrategy implements the SorryStrategy protocol using an custom Sagemaker endpoint
    built from a Hugging Face model to generate proofs.

    By default use the `deepseek-ai/DeepSeek-Prover-V2-7B` model

    SagemakerStrategy requires an AWS account and a authenticated aws cli.

    WARNING: Always us SagemakerStrategy as a context manager. If Sagemaker endpoints are not cleaned up properly they can lead to a large AWS bill.
    """

    def __init__(self):
        logging.info("Sagemaker strategy started. Configuration:")
        logging.info(f"  AWS Region: {AWS_REGION}")
        logging.info(f"  IAM Role Name: {IAM_ROLE_NAME}")
        logging.info(f"  Instance Type: {INSTANCE_TYPE}")
        logging.info(f"  Hugging Face Model ID: {HF_MODEL_ID}")

        self.hf_model_id = HF_MODEL_ID
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.hf_model_id)
        except Exception as e:
            logging.error(f"Failed to load tokenizer for {self.hf_model_id}: {e}")
            # Depending on the desired behavior, you might want to re-raise or handle this
            # For now, we'll let it proceed, but chat templating will fail later.
            self.tokenizer = None

        iam_client = boto3.client("iam")
        role = iam_client.get_role(RoleName=IAM_ROLE_NAME)["Role"]["Arn"]
        environemt_variables = {
            "HF_MODEL_ID": "deepseek-ai/DeepSeek-Prover-V2-7B",  # model_id from hf.co/models
            "HF_TASK": "text-generation",  # NLP task you want to use for predictions
        }

        # Only set the HF_MODEL_QUANTIZE environment variable if QUANTIZE is set
        if QUANTIZE:
            environemt_variables["HF_MODEL_QUANTIZE"] = QUANTIZE

        huggingface_image_uri = get_huggingface_llm_image_uri(
            backend="huggingface",
            region=AWS_REGION,
        )

        self.huggingface_model = HuggingFaceModel(
            env=environemt_variables,
            role=role,
            image_uri=huggingface_image_uri,
        )

        self.predictor = None  # Predictor will be initialized in __enter__
        logging.info(
            "SagemakerStrategy configured. Endpoint will be deployed when entering context."
        )

    def __enter__(self):
        if self.predictor is None:
            logging.info(
                f"Deploying Hugging Face model ({HF_MODEL_ID}) to SageMaker endpoint on {INSTANCE_TYPE}..."
            )
            # TODO: We should also allow users to use a preconfigured SageMaker endpoint
            # This step takes a while! Luckily it is only needed once and then we can hit the end point with each sorry.
            self.predictor = self.huggingface_model.deploy(
                initial_instance_count=1, instance_type=INSTANCE_TYPE
            )
            logging.info(f"SageMaker endpoint deployed: {self.predictor.endpoint_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Clean up the Sagemaker endpoint
        """
        if self.predictor:
            endpoint_name = self.predictor.endpoint_name
            logging.info(f"Deleting SageMaker endpoint: {endpoint_name}...")
            try:
                self.predictor.delete_endpoint()
                logging.info(f"SageMaker endpoint {endpoint_name} deleted.")
            except Exception as e:
                logging.error(f"Error deleting SageMaker endpoint {endpoint_name}: {e}")
            finally:
                self.predictor = None
        # Return False or None to propagate exceptions by default
        return False

    def _sagemaker_predict(self, prompt: str):
        if not self.predictor:
            msg = "SageMaker predictor not available. Ensure SagemakerStrategy is used as a context manager and __enter__ was successful."
            logging.error(msg)
            raise RuntimeError(msg)

        if not self.tokenizer:
            msg = "Tokenizer not available. Failed to initialize tokenizer."
            logging.error(msg)
            raise RuntimeError(msg)

        chat_messages = [{"role": "user", "content": prompt}]
        try:
            # Apply the chat template to format the messages into a single string
            # add_generation_prompt=True is important to ensure the model knows it's its turn to speak.
            formatted_prompt = self.tokenizer.apply_chat_template(
                chat_messages, tokenize=False, add_generation_prompt=True
            )
        except Exception as e:
            logging.error(f"Error applying chat template: {e}")
            # Fallback or re-raise, for now, we'll try to join content if it's a simple user message
            if len(chat_messages) == 1 and chat_messages[0]["role"] == "user":
                formatted_prompt = chat_messages[0]["content"]
                logging.warning(
                    "Falling back to using raw content due to chat template error."
                )
            else:
                raise RuntimeError(
                    f"Could not apply chat template and no simple fallback: {e}"
                )

        data = {
            "inputs": formatted_prompt,
            "parameters": {  # Parameters to control the generation process
                "max_new_tokens": 8192,
                # "return_full_text": False, # TGI default is effectively False.
            },
        }

        # request
        logging.info(
            f"Sending request to SageMaker endpoint: {self.predictor.endpoint_name}"
        )
        response = self.predictor.predict(data)
        logging.info("Received response from SageMaker endpoint.")
        # the response is of the form [{'generated_text': 'RESPONSE'}]
        proof = response[0]["generated_text"]
        return proof

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

        logger.info(f"Built prompt for sorry: {prompt}")

        # Run the prompt
        proof = self._sagemaker_predict(prompt)

        logger.info(f"Generated proof before processing: {proof}")

        # Process the proof
        processed = preprocess_proof(proof, loc.start_column)
        logger.info(f"Generated proof: {processed}")

        return processed

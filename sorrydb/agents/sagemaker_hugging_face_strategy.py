import logging
from pathlib import Path

import boto3
from sagemaker.huggingface.llm_utils import get_huggingface_llm_image_uri
from sagemaker.huggingface.model import HuggingFaceModel, HuggingFacePredictor
from transformers import AutoTokenizer

from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.agents.llm_proof_utils import (
    DEEPSEEK_PROMPT,
    PROMPT,
    extract_proof_from_code_block,
    extract_proof_from_full_theorem_statement,
    preprocess_proof,
)
from sorrydb.database.sorry import Sorry

# Configuration defaults
# TODO: We should parameterize the strategy by some or all of these
DEFAULT_AWS_REGION = "us-east-1"
DEFAULT_IAM_ROLE_NAME = "AmazonSageMaker-ExecutionRole-20250610T153494"
DEFAULT_INSTANCE_TYPE = "ml.g5.xlarge"

# Model must be supported by [Hugging Face TGI](https://huggingface.co/docs/text-generation-inference/en/index).
# I believe DeepSeek Prover works because it has the same underlying architecture as DeepSeek-V3, which is supported.
DEFAULT_HF_MODEL_ID = "deepseek-ai/DeepSeek-Prover-V2-7B"
# Possible Quanitzation values for TGI [here](https://huggingface.co/docs/text-generation-inference/en/basic_tutorials/launcher#quantize)
# e.g. `QUANTIZE = "bitsandbytes" for an 8bit quantization`
DEFAULT_QUANTIZE = None


logger = logging.getLogger(__name__)


def load_existing_sagemaker_endpoint(endpoint_name: str):
    return HuggingFacePredictor(endpoint_name=endpoint_name)


class SagemakerHuggingFaceEndpointManager:
    """
    Manages the lifecycle of a SageMaker Hugging Face TGI endpoint.
    Use as a context manager to ensure endpoints are deployed and deleted correctly.
    """

    def __init__(
        self,
        hf_model_id: str = DEFAULT_HF_MODEL_ID,
        aws_region: str = DEFAULT_AWS_REGION,
        iam_role_name: str = DEFAULT_IAM_ROLE_NAME,
        instance_type: str = DEFAULT_INSTANCE_TYPE,
        quantize: str | None = DEFAULT_QUANTIZE,
        sagemaker_session=None,  # Allow passing a pre-configured session
    ):
        self.hf_model_id = hf_model_id
        self.aws_region = aws_region
        self.iam_role_name = iam_role_name
        self.instance_type = instance_type
        self.quantize = quantize
        self.sagemaker_session = sagemaker_session  # For advanced use cases or testing

        logging.info("SagemakerHuggingFaceEndpointManager initialized. Configuration:")
        logging.info(f"  Hugging Face Model ID: {self.hf_model_id}")
        logging.info(f"  AWS Region: {self.aws_region}")
        logging.info(f"  IAM Role Name: {self.iam_role_name}")
        logging.info(f"  Instance Type: {self.instance_type}")
        logging.info(f"  Quantization: {self.quantize}")

        iam_client = boto3.client("iam", region_name=self.aws_region)
        try:
            self.role_arn = iam_client.get_role(RoleName=self.iam_role_name)["Role"][
                "Arn"
            ]
        except Exception as e:
            logging.error(f"Failed to get IAM role ARN for {self.iam_role_name}: {e}")
            raise ValueError(
                f"Could not retrieve IAM role {self.iam_role_name}. Please ensure it exists and you have permissions."
            ) from e

        environment_variables = {
            "HF_MODEL_ID": self.hf_model_id,
            "HF_TASK": "text-generation",
        }

        if self.quantize:
            environment_variables["HF_MODEL_QUANTIZE"] = self.quantize

        huggingface_image_uri = get_huggingface_llm_image_uri(
            backend="huggingface",  # or "huggingface-llm" depending on SageMaker SDK version and TGI version
            region=self.aws_region,
            # version="<specific_tgi_version>" # Optionally pin TGI version
        )

        self.huggingface_model = HuggingFaceModel(
            env=environment_variables,
            role=self.role_arn,
            image_uri=huggingface_image_uri,
            sagemaker_session=self.sagemaker_session,
        )
        self.predictor = None
        logging.info(
            "SagemakerHuggingFaceEndpointManager configured. Endpoint will be deployed when entering context."
        )

    def deploy(self):
        if self.predictor is not None:
            logging.warning(
                "Endpoint manager entered again, but predictor already exists. Reusing existing predictor."
            )
            return self.predictor

        logging.info(
            f"Deploying Hugging Face model ({self.hf_model_id}) to SageMaker endpoint on {self.instance_type}..."
        )
        try:
            self.predictor = self.huggingface_model.deploy(
                initial_instance_count=1,
                instance_type=self.instance_type,
                # endpoint_name= # Optionally specify a name
            )
            logging.info(f"SageMaker endpoint deployed: {self.predictor.endpoint_name}")
            return self.predictor
        except Exception as e:
            logging.error(
                f"Failed to deploy SageMaker endpoint for model {self.hf_model_id}: {e}"
            )
            # Clean up if partial deployment happened or if model object exists
            if (
                hasattr(self.huggingface_model, "endpoint_name")
                and self.huggingface_model.endpoint_name
            ):
                try:
                    logging.info(
                        f"Attempting to delete potentially partially created endpoint: {self.huggingface_model.endpoint_name}"
                    )
                    self.huggingface_model.delete_model()  # Also delete model if created
                except Exception as del_e:
                    logging.error(
                        f"Error during cleanup of partially deployed endpoint: {del_e}"
                    )
            raise RuntimeError(
                f"SageMaker endpoint deployment failed for {self.hf_model_id}"
            ) from e

    def delete(self):
        if self.predictor:
            endpoint_name = self.predictor.endpoint_name
            logging.info(f"Deleting SageMaker endpoint: {endpoint_name}...")
            try:
                self.predictor.delete_endpoint(
                    delete_endpoint_config=True
                )  # delete_endpoint_config=True is important
                logging.info(f"SageMaker endpoint {endpoint_name} deleted.")
            except Exception as e:
                logging.error(f"Error deleting SageMaker endpoint {endpoint_name}: {e}")
            finally:
                self.predictor = None

    def __enter__(self):
        return self.deploy()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.delete()
        # Return False or None to propagate exceptions by default
        return False


class SagemakerHuggingFaceStrategy(SorryStrategy):
    """SagemakerStrategy implements the SorryStrategy protocol using an custom Sagemaker endpoint
    built from a Hugging Face model to generate proofs.

    By default use the `deepseek-ai/DeepSeek-Prover-V2-7B` model

    SagemakerStrategy requires an AWS account and a authenticated aws cli.

    WARNING: Always us SagemakerStrategy as a context manager. If Sagemaker endpoints are not cleaned up properly they can lead to a large AWS bill.
    """

    def __init__(self, predictor, tokenizer_model_id: str = DEFAULT_HF_MODEL_ID):
        if predictor is None:
            raise ValueError("A SageMaker Predictor object must be provided.")
        self.predictor = predictor
        self.tokenizer_model_id = tokenizer_model_id

        logging.info(f"here is the predictor: {predictor}")

        logging.info("SagemakerHuggingFaceStrategy initialized:")
        logging.info(f"  Using SageMaker Endpoint: {self.predictor.endpoint_name}")
        logging.info(f"  Tokenizer Model ID: {self.tokenizer_model_id}")

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.tokenizer_model_id)
        except Exception as e:
            logging.error(
                f"Failed to load tokenizer for {self.tokenizer_model_id}: {e}"
            )
            # This is critical for formatting prompts, so we should raise an error.
            raise RuntimeError(
                f"Could not load tokenizer for {self.tokenizer_model_id}"
            ) from e

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
                "return_full_text": False,
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

        # Extract limited context: 50 lines from the top, 20 lines before the sorry line
        lines = file_text.splitlines()
        top_context_lines = lines[:50]
        pre_sorry_context_lines = lines[max(0, loc.start_line - 20) : loc.start_line]
        context_top = "\n".join(top_context_lines)
        context_pre_sorry = "\n".join(pre_sorry_context_lines)

        prompt = DEEPSEEK_PROMPT.format(
            goal=sorry.debug_info.goal,
            context_top=context_top,
            context_pre_sorry=context_pre_sorry,
            column=loc.start_column,
        )

        logger.info(f"Built prompt for sorry: {prompt}")

        # Run the prompt
        proof = self._sagemaker_predict(prompt)

        logger.info(f"Generated proof before processing: {proof}")

        # Process the proof
        # If the proof given includes the theorm statement
        # extract just the proof that will replace the sorry
        extracted_proof = extract_proof_from_code_block(proof)
        logger.info(f"Extacted proof: {extracted_proof}")
        no_theorem_statement_proof = extract_proof_from_full_theorem_statement(
            extracted_proof
        )
        logger.info(f"No theorem statement proof: {no_theorem_statement_proof}")

        processed = preprocess_proof(no_theorem_statement_proof, loc.start_column)
        logger.info(f"Fully processed proof: {processed}")
        logger.info(f"Generated proof: {processed}")

        return processed

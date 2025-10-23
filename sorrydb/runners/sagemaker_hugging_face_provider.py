import logging

import boto3
from sagemaker.huggingface.llm_utils import get_huggingface_llm_image_uri
from sagemaker.huggingface.model import HuggingFaceModel, HuggingFacePredictor
from transformers import AutoTokenizer

from sorrydb.strategies.cloud_llm_strategy import LLMProvider

# Configuration defaults
# TODO: We should parameterize the strategy by some or all of these
DEFAULT_AWS_REGION = "us-east-1"
DEFAULT_IAM_ROLE_NAME = "AmazonSageMaker-ExecutionRole-20250610T153494"
DEFAULT_INSTANCE_TYPE = "ml.g6.xlarge"

# Model must be supported by [Hugging Face TGI](https://huggingface.co/docs/text-generation-inference/en/index).
# I believe DeepSeek Prover works because it has the same underlying architecture as DeepSeek-V3, which is supported.
DEFAULT_HF_MODEL_ID = "deepseek-ai/DeepSeek-Prover-V2-7B"
# Possible Quanitzation values for TGI [here](https://huggingface.co/docs/text-generation-inference/en/basic_tutorials/launcher#quantize)
# e.g. `QUANTIZE = "bitsandbytes" for an 8bit quantization`
DEFAULT_QUANTIZE = "eetq"


logger = logging.getLogger(__name__)


class SagemakerLLMProvider(LLMProvider):
    def __init__(self, predictor):
        self.predictor = predictor
        self.tokenizer = AutoTokenizer.from_pretrained(DEFAULT_HF_MODEL_ID)

    def predict(self, prompt: str) -> str:
        # Your existing _sagemaker_predict logic here
        chat_messages = [{"role": "user", "content": prompt}]
        formatted_prompt = self.tokenizer.apply_chat_template(
            chat_messages, tokenize=False, add_generation_prompt=True
        )

        data = {
            "inputs": formatted_prompt,
            "parameters": {"max_new_tokens": 1024, "return_full_text": False},
        }

        response = self.predictor.predict(data)
        return response[0]["generated_text"]


def load_existing_sagemaker_endpoint(endpoint_name: str):
    return HuggingFacePredictor(endpoint_name=endpoint_name)


class SagemakerHuggingFaceEndpointManager:
    """
    Manages the lifecycle of a SageMaker Hugging Face TGI endpoint.
    Requires an AWS account and a authenticated aws cli.
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
            backend="huggingface",
            region=self.aws_region,
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
                self.predictor.delete_endpoint(delete_endpoint_config=True)
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

import asyncio
import logging
import random
from pathlib import Path
from typing import Dict
from os import getenv
import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from sorrydb.runners.json_runner import SorryStrategy
from sorrydb.database.sorry import Sorry, Location
from sorrydb.utils.sorry_extraction import extract_proof_from_diff


class VertexChatModel:
    """Minimal wrapper around Vertex AI predict endpoint with chatCompletions format."""

    def __init__(self, predict_url, credentials, model_name, max_tokens=24000):
        self.predict_url = predict_url
        self.credentials = credentials
        self.model = model_name
        self.max_tokens = max_tokens

    def _refresh_token(self):
        import google.auth.transport.requests
        self.credentials.refresh(google.auth.transport.requests.Request())

    def _build_payload(self, messages):
        msg_list = []
        for m in messages:
            if isinstance(m, SystemMessage):
                msg_list.append({"role": "system", "content": m.content})
            elif isinstance(m, HumanMessage):
                msg_list.append({"role": "user", "content": m.content})
        return {
            "instances": [{
                "@requestFormat": "chatCompletions",
                "messages": msg_list,
                "max_tokens": self.max_tokens,
            }]
        }

    def _parse_response(self, data):
        predictions = data.get("predictions", {})
        choices = predictions.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        usage = predictions.get("usage", {})

        class _Response:
            pass

        resp = _Response()
        resp.text = text
        resp.content = text
        resp.usage_metadata = {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }
        return resp

    def invoke(self, messages):
        import requests
        self._refresh_token()
        logger.info(f"VertexChatModel: POST {self.predict_url}")
        resp = requests.post(
            self.predict_url,
            headers={"Authorization": f"Bearer {self.credentials.token}", "Content-Type": "application/json"},
            json=self._build_payload(messages),
            timeout=1800,
        )
        logger.info(f"VertexChatModel: status={resp.status_code}")
        logger.info(f"VertexChatModel: raw response={resp.text[:2000]}")
        resp.raise_for_status()
        return self._parse_response(resp.json())

    async def ainvoke(self, messages):
        import httpx
        self._refresh_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.predict_url,
                headers={"Authorization": f"Bearer {self.credentials.token}", "Content-Type": "application/json"},
                json=self._build_payload(messages),
                timeout=1800,
            )
            logger.info(f"VertexChatModel: status={resp.status_code}")
            logger.info(f"VertexChatModel: raw response={resp.text[:2000]}")
            resp.raise_for_status()
            return self._parse_response(resp.json())

# Retry configuration for API errors
# For quota errors, we need long waits - quota typically resets every minute
MAX_RETRIES = 20
BASE_DELAY = 5.0  # seconds
MAX_DELAY = 300.0  # 5 minutes max delay between retries

# EXAMPLE PROMPTS IN LITERATURE
# https://github.com/cmu-l3/llmlean/blob/77448d68e51166f60bd43c6284b43d65209321b0/LLMlean/API.lean#L258
# https://plmlab.math.cnrs.fr/nuccio/octonions/-/blob/c3569703fd17191c279908509b8845735d5c507e/Mathlib/Tactic/GPT/Sagredo/Dialog.lean
# https://github.com/GasStationManager/LeanTool/blob/main/leantool.py
# https://github.com/quinn-dougherty/fvapps/blob/master/src/baselines/baselines_config.py
# https://github.com/Goedel-LM/Goedel-Prover/blob/5988bb0e3650f0417b61da4b10885e7ad6ca75fc/prover/utils.py#L23
# https://github.com/lean-dojo/LeanCopilot/blob/e2aebdab8e9b1c74a5334b36ba2c288c5a5f175d/python/external_models/hf_runner.py#L41
# https://github.com/oOo0oOo/lean-scribe/blob/main/default_scribe_folder/default_prompts/progress_in_proof.md


PROMPT = """You are an advanced AI that has studied all known mathematics and world expert in Lean4 theorem proving.
Consider the following Lean code:
<context>
```lean
{context}
```
</context>

Its proof goal is
<proof_goal>
```lean
{goal}
```
</proof_goal>

Target sorry is the following:
<target_sorry>
The given file contains a sorry on the last line, column {column}. 
</target_sorry

Replace the target sorry on the last line with a valid proof. 
Write a short, simple and elegant proof.
Output the ENTIRE code block inside a ```lean block with ONLY the sorry replaced.
If the file is long you should not output again the entire file, but just the last code block that is relevant.
Do not modify anything else - no formatting changes, no whitespace changes, no other edits.
Do not replace other sorries apart from the target one on the last line of the context.
You cannot import any additional libraries. 
DO NOT WRITE COMMENTS OR EXPLANATIONS! Just output the modified code block.
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

        # Track token usage from last API call
        self.last_usage = None
        # Cost per million tokens [input, output] - defaults set per provider below
        self.cost_per_million = model_config.get("cost", [0, 0])

        # Setup LLM
        if model_config["provider"] == "anthropic":
            self.model = ChatAnthropic(**model_config["params"])
        elif model_config["provider"] == "openai":
            self.model = ChatOpenAI(**model_config["params"])
        elif model_config["provider"] == "google":
            self.model = ChatGoogleGenerativeAI(**model_config["params"])
        elif model_config["provider"] == "qwen":
            self.model = ChatOpenAI(
                api_key=getenv("QWEN_API_KEY"),
                base_url="https://api.mulerouter.ai/vendors/openai/v1",
                model="qwen3-max",
            )
        elif model_config["provider"] == "deepseek":
            use_api_provider = model_config.get("params", {}).get("api_provider", False)
            if use_api_provider:
                self.model = ChatOpenAI(
                    api_key=getenv("OPENROUTER_API_KEY"),
                    base_url="https://openrouter.ai/api/v1",
                    model="deepseek/deepseek-prover-v2",
                )
            else:
                # TODO: Alternative configuration to be specified
                raise NotImplementedError("Alternative DeepSeek configuration not yet implemented")
            # TODO: we may want to update the PROMPT
        elif model_config["provider"] == "openrouter":
            model_name = model_config.get("params", {}).get("model", "openai/gpt-5.2")
            # Default pricing for GPT-5.2 via OpenRouter
            if "cost" not in model_config:
                self.cost_per_million = [1.75, 14.0]  # [input, output] $/1M tokens

            # Build model_kwargs for reasoning models (e.g., reasoning_effort)
            model_kwargs = {}
            reasoning_effort = model_config.get("params", {}).get("reasoning_effort")
            if reasoning_effort:
                model_kwargs["reasoning_effort"] = reasoning_effort

            self.model = ChatOpenAI(
                api_key=getenv("OPENROUTER_API_KEY"),
                base_url="https://openrouter.ai/api/v1",
                model=model_name,
                max_tokens=32000,  # Increased from 8096 to prevent empty responses with reasoning models
                model_kwargs=model_kwargs,
            )
        elif model_config["provider"] == "kimina":
            params = model_config.get("params", {})
            # Support both new "backend" string and legacy "api_provider" bool
            backend = params.get("backend", "huggingface")
            if params.get("api_provider", False) and backend == "huggingface":
                backend = "huggingface_router"

            if backend == "huggingface_router":
                if getenv("HUGGINGFACE_API_KEY"):
                    logger.info("HUGGINGFACE_API_KEY is set.")
                else:
                    logger.warning("HUGGINGFACE_API_KEY is not set.")
                self.model = ChatOpenAI(
                    api_key=getenv("HUGGINGFACE_API_KEY"),
                    base_url="https://router.huggingface.co/v1",
                    model="AI-MO/Kimina-Prover-72B:featherless-ai",
                    temperature=0.6,
                    top_p=0.95,
                    max_tokens=8096,
                )
            elif backend == "vertex":
                import google.auth
                import google.auth.transport.requests
                credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                credentials.refresh(google.auth.transport.requests.Request())

                vertex_domain = params.get("vertex_domain", "236623698390417408.us-east5-136811191949.prediction.vertexai.goog")
                vertex_project = params.get("vertex_project", "136811191949")
                vertex_location = params.get("vertex_location", "us-east5")
                vertex_endpoint = params.get("vertex_endpoint", "236623698390417408")
                predict_url = f"https://{vertex_domain}/v1/projects/{vertex_project}/locations/{vertex_location}/endpoints/{vertex_endpoint}:predict"

                self.model = VertexChatModel(
                    predict_url=predict_url,
                    credentials=credentials,
                    model_name="AI-MO/Kimina-Prover-Distill-8B",
                    max_tokens=8096,
                )
            elif backend == "huggingface":
                self.model = ChatOpenAI(
                    api_key=getenv("HUGGINGFACE_API_KEY"),
                    base_url=getenv(
                        "KIMINA_HF_ENDPOINT_URL",
                        "https://st70knfgoj9d789e.us-east4.gcp.endpoints.huggingface.cloud/v1",
                    ),
                    model="AI-MO/Kimina-Prover-Distill-8B",
                    max_tokens=8096,
                )
            self.is_kimina = True
        elif model_config["provider"] == "goedel":
            params = model_config.get("params", {})
            # Support both new "backend" string and legacy "api_provider" bool
            backend = params.get("backend", "huggingface")
            if params.get("api_provider", False) and backend == "huggingface":
                backend = "featherless"

            if backend == "featherless":
                if getenv("FEATHERLESS_API_KEY"):
                    logger.info("FEATHERLESS_API_KEY is set.")
                else:
                    logger.warning("FEATHERLESS_API_KEY is not set.")
                self.model = ChatOpenAI(
                    api_key=getenv("FEATHERLESS_API_KEY"),
                    base_url="https://api.featherless.ai/v1",
                    model="Goedel-LM/Goedel-Prover-V2-32B",
                    max_tokens=32768,
                )
            elif backend == "vertex":
                import google.auth
                import google.auth.transport.requests
                credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                credentials.refresh(google.auth.transport.requests.Request())

                vertex_domain = params.get("vertex_domain", "1540413591490920448.europe-west4-136811191949.prediction.vertexai.goog")
                vertex_project = params.get("vertex_project", "136811191949")
                vertex_location = params.get("vertex_location", "europe-west4")
                vertex_endpoint = params.get("vertex_endpoint", "1540413591490920448")
                predict_url = f"https://{vertex_domain}/v1/projects/{vertex_project}/locations/{vertex_location}/endpoints/{vertex_endpoint}:predict"

                self.model = VertexChatModel(
                    predict_url=predict_url,
                    credentials=credentials,
                    model_name="Goedel-LM/Goedel-Prover-V2-32B",
                    max_tokens=3000,
                )
            elif backend == "huggingface":
                self.model = ChatOpenAI(
                                    api_key=getenv("HUGGINGFACE_API_KEY"),
                                    base_url=getenv("GOEDEL_HF_ENDPOINT_URL", "https://yqfy8xdabe5ox9m5.us-east4.gcp.endpoints.huggingface.cloud/v1"),
                                    model="Goedel-LM/Goedel-Prover-V2-32B",
                                    max_tokens=3000,
                                )
            self.is_goedel = True
        else:
            raise ValueError(f"Invalid model provider: {model_config['provider']}")

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

        # Extract the context up to and including the sorry (for multi-line sorries)
        context_lines = file_text.splitlines()[: loc.end_line]

        # Truncate context for models with limited context windows (16k tokens)
        line_offset = 0
        if getattr(self, 'is_kimina', False) or getattr(self, 'is_goedel', False):
            MAX_CONTEXT_LINES = 300
            if len(context_lines) > MAX_CONTEXT_LINES:
                line_offset = len(context_lines) - MAX_CONTEXT_LINES
                context_lines = context_lines[-MAX_CONTEXT_LINES:]

        context = "\n".join(context_lines)

        # Use model-specific prompting if applicable

        prompt = PROMPT.format(
            goal=sorry.debug_info.goal,
            context=context,
            column=loc.start_column,
        )
        messages = [HumanMessage(content=prompt)]

        # Run the prompt
        logger.info("Prompting LLM")
        full_response = self.model.invoke(messages)

        response = full_response.text
        # Log the full raw LLM response for debugging
        logger.info(f"Full LLM response:\n{response}")
        # Warn if response is empty (common with reasoning models that exhaust token budget)
        if not response or not response.strip():
            logger.warning("Empty LLM response received - model may have exhausted tokens on reasoning")

        # Extract and store token usage for cost tracking
        usage = getattr(full_response, 'usage_metadata', None) or {}
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)

        # Calculate cost
        input_cost = (input_tokens / 1_000_000) * self.cost_per_million[0]
        output_cost = (output_tokens / 1_000_000) * self.cost_per_million[1]

        self.last_usage = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'estimated_cost': input_cost + output_cost
        }
        logger.info(f"Token usage: input={input_tokens}, output={output_tokens}, cost=${input_cost + output_cost:.4f}")

        # Adjust location for truncated context
        if line_offset > 0:
            adjusted_loc = Location(
                path=loc.path,
                start_line=loc.start_line - line_offset,
                start_column=loc.start_column,
                end_line=loc.end_line - line_offset,
                end_column=loc.end_column,
            )
        else:
            adjusted_loc = loc

        # Extract proof using diff
        proof = extract_proof_from_diff(context, response, adjusted_loc)
        logger.info(f"Extracted proof: {proof}")

        return proof

    async def prove_sorry_async(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Async version of prove_sorry using ainvoke for proper cancellation support.

        This method allows asyncio.wait_for() to properly cancel the coroutine
        and close HTTP connections when a timeout occurs, unlike the sync version
        which runs in a thread that cannot be interrupted.

        Args:
            repo_path: Path to the repository
            sorry: Dictionary containing sorry information

        Returns:
            Proof string or None if no proof was found
        """
        # Load the file and render the prompt (sync file I/O is fast)
        loc = sorry.location
        file_path = repo_path / loc.path
        file_text = file_path.read_text()

        # Extract the context up to and including the sorry (for multi-line sorries)
        context_lines = file_text.splitlines()[: loc.end_line]

        # Truncate context for models with limited context windows (16k tokens)
        line_offset = 0
        if getattr(self, 'is_kimina', False) or getattr(self, 'is_goedel', False):
            MAX_CONTEXT_LINES = 300
            if len(context_lines) > MAX_CONTEXT_LINES:
                line_offset = len(context_lines) - MAX_CONTEXT_LINES
                context_lines = context_lines[-MAX_CONTEXT_LINES:]

        context = "\n".join(context_lines)

        prompt = PROMPT.format(
            goal=sorry.debug_info.goal,
            context=context,
            column=loc.start_column,
        )
        messages = [HumanMessage(content=prompt)]

        # Run the prompt asynchronously with exponential backoff for rate limits
        logger.info("Prompting LLM (async) - starting ainvoke call")
        logger.info(f"Model: {getattr(self.model, 'model_name', getattr(self.model, 'model', 'unknown'))}")

        full_response = None
        last_exception = None
        total_wait_time = 0.0

        for attempt in range(MAX_RETRIES + 1):
            try:
                full_response = await self.model.ainvoke(messages)
                if attempt > 0:
                    logger.info(f"LLM ainvoke succeeded after {attempt} retries (waited {total_wait_time:.1f}s total)")
                else:
                    logger.info("LLM ainvoke call completed successfully")
                break
            except asyncio.CancelledError:
                logger.warning("LLM ainvoke call was CANCELLED (timeout or external cancellation)")
                raise
            except Exception as e:
                last_exception = e
                if attempt < MAX_RETRIES:
                    # Exponential backoff with jitter, capped at MAX_DELAY
                    delay = min(BASE_DELAY * (2 ** attempt) + random.uniform(0, 1), MAX_DELAY)
                    total_wait_time += delay
                    logger.warning(
                        f"LLM error (attempt {attempt + 1}/{MAX_RETRIES + 1}), "
                        f"retrying in {delay:.1f}s (total wait: {total_wait_time:.1f}s): "
                        f"{type(e).__name__}: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"LLM error after {MAX_RETRIES + 1} attempts "
                        f"(waited {total_wait_time:.1f}s total): {type(e).__name__}: {e}"
                    )
                    raise

        if full_response is None:
            raise last_exception or RuntimeError("LLM call failed without response")

        response = full_response.text
        # Log the full raw LLM response for debugging
        logger.info(f"Full LLM response:\n{response}")
        # Warn if response is empty (common with reasoning models that exhaust token budget)
        if not response or not response.strip():
            logger.warning("Empty LLM response received - model may have exhausted tokens on reasoning")

        # Extract and store token usage for cost tracking
        usage = getattr(full_response, 'usage_metadata', None) or {}
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)

        # Calculate cost
        input_cost = (input_tokens / 1_000_000) * self.cost_per_million[0]
        output_cost = (output_tokens / 1_000_000) * self.cost_per_million[1]

        self.last_usage = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'estimated_cost': input_cost + output_cost
        }
        logger.info(f"Token usage: input={input_tokens}, output={output_tokens}, cost=${input_cost + output_cost:.4f}")

        # Adjust location for truncated context
        if line_offset > 0:
            adjusted_loc = Location(
                path=loc.path,
                start_line=loc.start_line - line_offset,
                start_column=loc.start_column,
                end_line=loc.end_line - line_offset,
                end_column=loc.end_column,
            )
        else:
            adjusted_loc = loc

        # Extract proof using diff
        proof = extract_proof_from_diff(context, response, adjusted_loc)
        logger.info(f"Extracted proof: {proof}")

        return proof

    def get_usage_info(self):
        """Return token usage from last API call."""
        return self.last_usage

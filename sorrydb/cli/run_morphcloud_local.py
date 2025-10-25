import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from ..strategies.agentic_strategy import AgenticStrategy
from ..strategies.cloud_llm_strategy import CloudLLMStrategy
from ..strategies.llm_proof_utils import DEEPSEEK_PROMPT
from ..strategies.llm_strategy import LLMStrategy
from ..runners.modal_hugging_face_provider import (
    ModalDeepseekProverLLMProvider,
    ModalKiminaLLMProvider,
)
from ..strategies.rfl_strategy import (
    NormNumStrategy,
    RflStrategy,
    SimpStrategy,
    ProveAllStrategy,
)
from ..strategies.tactic_strategy import StrategyMode, TacticByTacticStrategy
from ..database.sorry import Sorry, SorryJSONEncoder, SorryResult
from ..utils.verify_lean_interact import verify_lean_interact


def create_strategy_from_spec(spec_json: str | None):
    """Create a strategy instance from a JSON string spec.

    Spec shape:
    {"name": "agentic" | "llm" | "tactic" | "cloud_llm" | "rfl" | "simp" | "norm_num", "args": { ... }}
    """
    if not spec_json:
        # Default to agentic with defaults
        return AgenticStrategy()

    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON for --agent-strategy: {e}") from e

    if not isinstance(spec, dict):
        raise ValueError(
            "--agent-strategy must be a JSON object with 'name' and optional 'args'"
        )

    name = spec.get("name")
    args = spec.get("args", {})
    if not isinstance(name, str):
        raise ValueError("--agent-strategy JSON must include a string 'name'")
    if not isinstance(args, dict):
        raise ValueError("--agent-strategy 'args' must be an object")

    strategy_name = name.lower()

    match strategy_name:
        case "agentic":
            return AgenticStrategy(**args)

        case "llm":
            return LLMStrategy(**args)

        case "tactic":
            if "strategy_mode" in args and isinstance(args["strategy_mode"], str):
                args = {**args}
                args["strategy_mode"] = StrategyMode(
                    args["strategy_mode"]
                )  # may raise ValueError
            return TacticByTacticStrategy(**args)

        case "cloud_llm":
            provider_name = args.get("provider", "modal_deepseek")
            prompt = args.get("prompt", DEEPSEEK_PROMPT)

            if provider_name == "modal_deepseek":
                provider = ModalDeepseekProverLLMProvider()
            elif provider_name == "modal_kimina":
                provider = ModalKiminaLLMProvider()
            else:
                raise ValueError(f"Unknown cloud LLM provider: {provider_name}")

            debug_info_path = args.get("debug_info_path")
            return CloudLLMStrategy(
                llm_provider=provider, prompt=prompt, debug_info_path=debug_info_path
            )

        case "rfl":
            return RflStrategy()

        case "simp":
            return SimpStrategy()

        case "norm_num":
            return NormNumStrategy()

        case "supersimple":
            return ProveAllStrategy()

        # TODO: create new agents
        # symbolic tactics
        # LLM calls (Claude, Gemini 2.5 flash)
        # Hosted LLMs (Kimina, DeepSeek no-cot)

        case _:
            available = ", ".join(
                [
                    "agentic",
                    "llm",
                    "tactic",
                    "cloud_llm",
                    "rfl",
                    "simp",
                    "norm_num",
                ]
            )
            raise ValueError(f"Unknown strategy '{name}'. Available: {available}")


if __name__ == "__main__":
    load_dotenv()

    argparser = argparse.ArgumentParser(
        description="Run a single agent on a sorrydb JSON file"
    )
    argparser.add_argument(
        "--sorry-json",
        type=str,
        required=False,
        help="JSON string with a single sorry object (not a path)",
    )
    argparser.add_argument(
        "--sorry-path",
        type=str,
        required=False,
        help="Path to a JSON file containing a single sorry object",
    )
    argparser.add_argument(
        "--repo-path", type=str, required=True, help="Path to the local repository"
    )
    argparser.add_argument(
        "--agent-strategy",
        type=str,
        required=False,
        help=(
            "JSON spec for the strategy to use. Example: "
            '\'{\n  "name": "agentic", "args": {"max_iterations": 3}\n}\'. '
            "Available names: agentic, llm, tactic, cloud_llm, rfl, simp, norm_num"
        ),
    )
    argparser.add_argument(
        "--output-path",
        type=str,
        default="/root/repo/result.json",
        help="Path to write the result JSON file (default: /root/repo/result.json)",
    )

    args = argparser.parse_args()

    # Validate that exactly one of --sorry-json or --sorry-path is provided
    if args.sorry_json and args.sorry_path:
        argparser.error("Cannot specify both --sorry-json and --sorry-path")
    if not args.sorry_json and not args.sorry_path:
        argparser.error("Must specify either --sorry-json or --sorry-path")

    # Load sorry data
    if args.sorry_path:
        with open(args.sorry_path, "r") as f:
            sorry_data = json.load(f)
            # Handle both single object and array with one element
            if isinstance(sorry_data, list):
                if len(sorry_data) != 1:
                    argparser.error(
                        f"--sorry-path file must contain exactly 1 sorry, found {len(sorry_data)}"
                    )
                sorry_data = sorry_data[0]
    else:
        sorry_data = json.loads(args.sorry_json)

    # Instantiate strategy from JSON spec (defaults to AgenticStrategy)
    agent = create_strategy_from_spec(args.agent_strategy)
    sorry = Sorry.from_dict(sorry_data)

    print("Running agent...")
    proof = agent.prove_sorry(Path(args.repo_path), sorry)

    print("Proof:")
    print(proof)

    proof_verified = False
    feedback = None
    if proof is not None:
        proof_verified, _ = verify_lean_interact(
            Path(args.repo_path),
            sorry.location,
            proof,
        )

    print(f"Proof verified: {proof_verified}")

    # Create result object and dump to JSON
    result = SorryResult(
        sorry=sorry, proof=proof, proof_verified=proof_verified, feedback=feedback
    )

    result_json = json.dumps(result, cls=SorryJSONEncoder, indent=2)

    # Export to file
    with open(args.output_path, "w") as f:
        f.write(result_json)

    print(f"\nResult exported to: {args.output_path}")
    print("\nResult JSON:")
    print(result_json)

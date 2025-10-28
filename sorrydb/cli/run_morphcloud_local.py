import argparse
import json
import logging
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
    logger = logging.getLogger(__name__)

    if not spec_json:
        # Default to agentic with defaults
        logger.info("No strategy spec provided, using default AgenticStrategy")
        return AgenticStrategy()

    logger.info(f"Parsing strategy spec (length: {len(spec_json)} chars)")
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse strategy JSON: {e}")
        raise ValueError(f"Invalid JSON for --agent-strategy: {e}") from e

    if not isinstance(spec, dict):
        logger.error(f"Strategy spec is not a dict: {type(spec)}")
        raise ValueError(
            "--agent-strategy must be a JSON object with 'name' and optional 'args'"
        )

    name = spec.get("name")
    args = spec.get("args", {})
    logger.info(f"Strategy name: {name}")
    logger.info(f"Strategy args: {args}")

    if not isinstance(name, str):
        logger.error(f"Strategy name is not a string: {type(name)}")
        raise ValueError("--agent-strategy JSON must include a string 'name'")
    if not isinstance(args, dict):
        logger.error(f"Strategy args is not a dict: {type(args)}")
        raise ValueError("--agent-strategy 'args' must be an object")

    strategy_name = name.lower()
    logger.info(f"Creating strategy: {strategy_name}")

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
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger(__name__)

    logger.info("=" * 80)
    logger.info("Starting run_morphcloud_local.py")
    logger.info("=" * 80)

    load_dotenv()
    logger.info("Environment loaded")

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
    logger.info(f"Arguments parsed: repo_path={args.repo_path}, output_path={args.output_path}")
    logger.info(f"Strategy spec: {args.agent_strategy[:100] if args.agent_strategy else 'None'}...")

    # Validate that exactly one of --sorry-json or --sorry-path is provided
    if args.sorry_json and args.sorry_path:
        logger.error("Both --sorry-json and --sorry-path specified")
        argparser.error("Cannot specify both --sorry-json and --sorry-path")
    if not args.sorry_json and not args.sorry_path:
        logger.error("Neither --sorry-json nor --sorry-path specified")
        argparser.error("Must specify either --sorry-json or --sorry-path")

    # Load sorry data
    logger.info("Loading sorry data...")
    if args.sorry_path:
        logger.info(f"Loading sorry from file: {args.sorry_path}")
        with open(args.sorry_path, "r") as f:
            sorry_data = json.load(f)
            # Handle both single object and array with one element
            if isinstance(sorry_data, list):
                if len(sorry_data) != 1:
                    logger.error(f"File contains {len(sorry_data)} sorries, expected 1")
                    argparser.error(
                        f"--sorry-path file must contain exactly 1 sorry, found {len(sorry_data)}"
                    )
                sorry_data = sorry_data[0]
        logger.info("Sorry data loaded from file")
    else:
        logger.info("Parsing sorry from JSON string...")
        sorry_data = json.loads(args.sorry_json)
        logger.info("Sorry data parsed from JSON string")

    # Instantiate strategy from JSON spec (defaults to AgenticStrategy)
    logger.info("Creating strategy from spec...")
    agent = create_strategy_from_spec(args.agent_strategy)
    logger.info(f"Strategy created: {type(agent).__name__}")

    logger.info("Creating Sorry object...")
    sorry = Sorry.from_dict(sorry_data)
    logger.info(f"Sorry object created: id={sorry.id}")
    logger.info(f"Sorry location: {sorry.location.path}:{sorry.location.start_line}")
    logger.info(f"Sorry goal: {sorry.debug_info.goal[:100] if sorry.debug_info.goal else 'None'}...")

    logger.info("Starting agent proof generation...")
    logger.info(f"Repository path: {args.repo_path}")
    proof = agent.prove_sorry(Path(args.repo_path), sorry)
    logger.info("Agent proof generation completed")

    logger.info("Generated proof:")
    print(proof)
    if proof:
        logger.info(f"Proof length: {len(proof)} chars")
    else:
        logger.warning("No proof generated (None)")

    proof_verified = False
    feedback = None
    verification_message = None
    if proof is not None:
        logger.info("Starting proof verification...")
        logger.info(f"Verifying at: {sorry.location.path}:{sorry.location.start_line}")
        proof_verified, error_msg = verify_lean_interact(
            Path(args.repo_path),
            sorry.location,
            proof,
        )
        verification_message = error_msg if error_msg else "Proof verified successfully"
        logger.info("Proof verification completed")
    else:
        logger.info("Skipping verification (no proof generated)")

    logger.info(f"Proof verified: {proof_verified}")
    if verification_message:
        logger.info(f"Verification message: {verification_message}")

    # Create result object and dump to JSON
    logger.info("Creating result object...")
    result = SorryResult(
        sorry=sorry,
        proof=proof,
        proof_verified=proof_verified,
        feedback=feedback,
        verification_message=verification_message,
    )
    logger.info("Result object created")

    logger.info("Serializing result to JSON...")
    result_json = json.dumps(result, cls=SorryJSONEncoder, indent=2)
    logger.info(f"Result JSON size: {len(result_json)} chars")

    # Export to file
    logger.info(f"Writing result to file: {args.output_path}")
    with open(args.output_path, "w") as f:
        f.write(result_json)
    logger.info("Result file written successfully")

    logger.info(f"Result exported to: {args.output_path}")
    print("\nResult JSON:")
    print(result_json)

    logger.info("run_morphcloud_local.py completed successfully")

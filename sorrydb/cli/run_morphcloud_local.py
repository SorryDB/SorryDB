import argparse
import json
import logging
import sys
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
    SingleTacticStrategy,
)
from ..strategies.tactic_strategy import StrategyMode, TacticByTacticStrategy
from ..database.sorry import Sorry, SorryJSONEncoder, SorryResult
from ..utils.verify_lean_interact import verify_lean_interact


# Default tactics to try for the "multi" strategy (Core + Mathlib)
DEFAULT_TACTICS = [
    "rfl",
    "simp",
    "simp_all",
    "exact?",
    "grind",
    "ring",
    "norm_num",
    "omega",
    "linarith",
    "nlinarith",
    "aesop",
]


def create_strategy_from_spec(spec_json: str | None) -> tuple:
    """Create a strategy instance from a JSON string spec and extract k parameter.

    Spec shape:
    {"name": "agentic" | "llm" | "tactic" | "cloud_llm" | "rfl" | "simp" | "norm_num" | "supersimple" | "multi_tactic", "args": { ... }}

    For "multi_tactic" strategy, returns a list of SingleTacticStrategy instances.
    Use args.tactics to specify which tactics to try (defaults to DEFAULT_TACTICS).
    Use args.k to specify the number of pass@k attempts (defaults to 1).

    Returns:
        tuple: (strategy or list of strategies, k value for pass@k)
    """
    logger = logging.getLogger(__name__)

    if not spec_json:
        # Default to agentic with defaults
        logger.info("No strategy spec provided, using default AgenticStrategy")
        return AgenticStrategy(), 1

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

    # Extract k for pass@k (remove from args so it's not passed to strategy constructors)
    k = args.pop("k", 1) if isinstance(args, dict) else 1

    logger.info(f"Strategy name: {name}")
    logger.info(f"Strategy args: {args}")
    logger.info(f"Pass@k value: {k}")

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
            return AgenticStrategy(**args), k

        case "llm":
            return LLMStrategy(**args), k

        case "tactic":
            if "strategy_mode" in args and isinstance(args["strategy_mode"], str):
                args = {**args}
                args["strategy_mode"] = StrategyMode(
                    args["strategy_mode"]
                )  # may raise ValueError
            return TacticByTacticStrategy(**args), k

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
            ), k

        case "rfl":
            return RflStrategy(), k

        case "simp":
            return SimpStrategy(), k

        case "norm_num":
            return NormNumStrategy(), k

        case "supersimple":
            return ProveAllStrategy(), k

        case "multi_tactic":
            tactics = args.get("tactics", DEFAULT_TACTICS)
            logger.info(f"Creating multi_tactic strategy with tactics: {tactics}")
            return [SingleTacticStrategy(t) for t in tactics], k

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
                    "supersimple",
                    "multi_tactic",
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

    # Add file handler to also write logs to a file
    file_handler = logging.FileHandler('/root/repo/run.log')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logging.getLogger().addHandler(file_handler)

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
            "Available names: agentic, llm, tactic, cloud_llm, rfl, simp, norm_num, supersimple, multi_tactic. "
            "For 'multi_tactic', use: '{\"name\": \"multi_tactic\", \"args\": {\"tactics\": [\"rfl\", \"simp\", ...]}}'. "
            "Pass@k: Add 'k' to args to run strategy up to k times with early exit on success. "
            "Example: '{\"name\": \"agentic\", \"args\": {\"k\": 3}}'"
        ),
    )
    argparser.add_argument(
        "--output-path",
        type=str,
        default="/root/repo/result.json",
        help="Path to write the result JSON file (default: /root/repo/result.json)",
    )

    args = argparser.parse_args()
    logger.info(f"Full command: {' '.join(sys.argv)}")
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
    # Initialize sorry to None so it's available in except block if creation fails
    sorry = None

    try:
        logger.info("Creating strategy from spec...")
        strategies, k = create_strategy_from_spec(args.agent_strategy)
        # Normalize to list for uniform handling
        if not isinstance(strategies, list):
            strategies = [strategies]
        logger.info(f"Strategies created: {[s.name() if hasattr(s, 'name') else type(s).__name__ for s in strategies]}")
        logger.info(f"Pass@k value: {k}")

        logger.info("Creating Sorry object...")
        sorry = Sorry.from_dict(sorry_data)
        logger.info(f"Sorry object created: id={sorry.id}")
        logger.info(f"Sorry location: {sorry.location.path}:{sorry.location.start_line}")
        file_lines = (Path(args.repo_path) / sorry.location.path).read_text().splitlines()
        start_context = max(0, sorry.location.start_line - 6)
        logger.info(f"Context before sorry (lines {start_context + 1}-{sorry.location.start_line}):")
        for i in range(start_context, sorry.location.start_line):
            logger.info(f"  {i + 1}: {file_lines[i]}")
        logger.info(f"Sorry line: {file_lines[sorry.location.start_line - 1]}")
        logger.info(f"Sorry goal: {sorry.debug_info.goal[:100] if sorry.debug_info.goal else 'None'}...")

        # Pass@k: iterate through strategies, each gets k attempts, early exit on success
        results = []
        found_success = False
        failed_attempts = []  # Collect all proof attempts for visibility when all fail
        usage_info = {}  # Track token usage from last attempt

        for strategy in strategies:
            if found_success:
                break

            strategy_name = strategy.name() if hasattr(strategy, 'name') else type(strategy).__name__
            logger.info(f"=" * 40)
            logger.info(f"Trying strategy: {strategy_name} (up to {k} attempts)")

            for attempt in range(1, k + 1):
                logger.info(f"-" * 20)
                logger.info(f"Strategy {strategy_name}, attempt {attempt}/{k}")

                logger.info("Starting proof generation...")
                logger.info(f"Repository path: {args.repo_path}")
                proof = strategy.prove_sorry(Path(args.repo_path), sorry)
                logger.info("Proof generation completed")

                # Get usage info if available (for cost tracking)
                usage_info = {}
                if hasattr(strategy, 'get_usage_info'):
                    usage_info = strategy.get_usage_info() or {}

                logger.info("Generated proof:")
                logger.info(proof)
                if proof:
                    logger.info(f"Proof length: {len(proof)} chars")
                else:
                    logger.warning("No proof generated (None)")

                proof_verified = False
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
                    verification_message = "No proof generated"

                logger.info(f"Strategy {strategy_name} attempt {attempt}: verified={proof_verified}")
                if verification_message:
                    logger.info(f"Verification message: {verification_message}")

                if proof_verified:
                    # SUCCESS: Return only this result
                    result = SorryResult(
                        sorry=sorry,
                        proof=proof,
                        proof_verified=True,
                        feedback=None,
                        verification_message=verification_message,
                        strategy_name=f"{strategy_name}" if k == 1 else f"{strategy_name}_attempt_{attempt}",
                        input_tokens=usage_info.get('input_tokens'),
                        output_tokens=usage_info.get('output_tokens'),
                        estimated_cost=usage_info.get('estimated_cost'),
                    )
                    results = [result]
                    found_success = True
                    logger.info(f"SUCCESS! Proof verified on attempt {attempt}")
                    break
                else:
                    # Verification failed - collect the attempt for visibility
                    if proof is not None:
                        failed_attempts.append(proof)
                    logger.info(f"Attempt {attempt} failed verification, continuing...")

        # If no success after all strategies and attempts
        if not found_success:
            total_attempts = len(strategies) * k
            result = SorryResult(
                sorry=sorry,
                proof=None,
                proof_verified=False,
                feedback=None,
                verification_message=f"All {total_attempts} attempts failed ({len(strategies)} strategies x {k} attempts each)",
                strategy_name=f"all_failed_k={k}",
                proof_attempts=failed_attempts if failed_attempts else None,
                input_tokens=usage_info.get('input_tokens'),
                output_tokens=usage_info.get('output_tokens'),
                estimated_cost=usage_info.get('estimated_cost'),
            )
            results = [result]

        logger.info(f"=" * 40)
        logger.info(f"Pass@k completed. Total results: {len(results)}")
        if found_success:
            logger.info(f"SUCCESS: {results[0].strategy_name}")
        else:
            logger.info(f"FAILED: All {len(strategies)} strategies x {k} attempts")

    except Exception as e:
        # Handle any error during execution and create error result
        import traceback
        error_traceback = traceback.format_exc()

        logger.error(f"Error during execution: {type(e).__name__}: {str(e)}")
        logger.error("Full traceback:")
        logger.error(error_traceback)

        # Create error result - sorry may be None if Sorry creation failed
        error_result = SorryResult(
            sorry=sorry,
            proof=None,
            proof_verified=False,
            feedback=None,
            verification_message=f"Error occurred during execution: {str(e)}",
            success=False,
            error_type=type(e).__name__,
            error_message=f"{str(e)}\n\nTraceback:\n{error_traceback}",
            strategy_name="error",
        )
        results = [error_result]
        logger.info("Error result created")

    # Always write results.json (array of results), whether successful or error
    logger.info(f"Writing results to file: {args.output_path}")
    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, cls=SorryJSONEncoder, indent=2, ensure_ascii=False)
    logger.info("Result file written successfully")

    logger.info(f"Results exported to: {args.output_path}")
    print("\nResults JSON:")
    results_json = json.dumps(results, cls=SorryJSONEncoder, indent=2, ensure_ascii=False)
    print(results_json)

    logger.info("run_morphcloud_local.py completed successfully")

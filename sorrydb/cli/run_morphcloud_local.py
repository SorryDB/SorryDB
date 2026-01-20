import argparse
import asyncio
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
from ..utils.verify_lean_interact import verify_lean_interact, VerificationContext
from ..utils.sorry_extraction import extract_proof_from_diff


# Default tactics to try for the "multi" strategy (Core + Mathlib)
DEFAULT_TACTICS = [
    "rfl",
    "trivial",
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

# Timeout for individual LLM calls (5 minutes)
LLM_CALL_TIMEOUT = 1200


async def generate_proofs_parallel(
    strategy,
    repo_path: Path,
    sorry: Sorry,
    k: int,
    logger: logging.Logger,
    llm_timeout: int = LLM_CALL_TIMEOUT,
) -> list[tuple[str | None, dict | None]]:
    """
    Generate k proofs in parallel using asyncio.

    Args:
        strategy: The proof strategy to use
        repo_path: Path to the repository
        sorry: The sorry to prove
        k: Number of proof attempts to generate
        logger: Logger instance for output
        llm_timeout: Timeout in seconds for each LLM call (default: LLM_CALL_TIMEOUT)

    Returns:
        List of (proof, usage_info) tuples for each attempt
    """

    async def generate_one(attempt: int) -> tuple[str | None, dict | None]:
        logger.info(f"Starting parallel proof generation for attempt {attempt}")
        use_async = hasattr(strategy, 'prove_sorry_async')
        logger.info(f"Attempt {attempt}: using {'async (ainvoke)' if use_async else 'sync (thread pool)'} method")
        try:
            # Use async method if available (proper cancellation), otherwise fall back to thread
            if use_async:
                logger.info(f"Attempt {attempt}: calling prove_sorry_async with timeout={llm_timeout}s")
                proof = await asyncio.wait_for(
                    strategy.prove_sorry_async(repo_path, sorry),
                    timeout=llm_timeout
                )
            else:
                logger.info(f"Attempt {attempt}: calling prove_sorry via asyncio.to_thread with timeout={llm_timeout}s")
                # Fallback for strategies without async support
                proof = await asyncio.wait_for(
                    asyncio.to_thread(strategy.prove_sorry, repo_path, sorry),
                    timeout=llm_timeout
                )
            # Get usage info immediately (before another thread overwrites it)
            usage = None
            if hasattr(strategy, "get_usage_info"):
                usage = strategy.get_usage_info()
            logger.info(f"Attempt {attempt}: completed successfully")
            return proof, usage
        except asyncio.TimeoutError:
            logger.warning(f"Attempt {attempt}: TIMEOUT after {llm_timeout}s - coroutine cancelled")
            raise
        except asyncio.CancelledError:
            logger.warning(f"Attempt {attempt}: CANCELLED - coroutine was cancelled")
            raise
        except Exception as e:
            logger.error(f"Attempt {attempt}: FAILED with {type(e).__name__}: {e}")
            raise

    # Launch all k attempts in parallel
    tasks = [generate_one(i + 1) for i in range(k)]
    # Use return_exceptions=True to capture failures without cancelling other tasks
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


def replay_from_responses(
    responses: list[str],
    repo_path: Path,
    sorry: Sorry,
    logger: logging.Logger,
    debug_extraction: bool = False,
) -> tuple[list[tuple[str | None, dict | None]], dict | None]:
    """Extract proofs from pre-stored LLM responses (NO LLM calls, NO verification here).

    This is used for replaying experiments with a fixed extraction algorithm.
    Each response is processed through extract_proof_from_diff to extract the proof.
    The returned results have the same format as generate_proofs_parallel for
    compatibility with the existing verification loop.

    Args:
        responses: List of raw LLM response strings
        repo_path: Path to the repository
        sorry: The sorry object containing location info
        logger: Logger instance for output
        debug_extraction: If True, collect debug data for each attempt

    Returns:
        Tuple of:
        - List of (proof, usage_info) tuples, same format as generate_proofs_parallel
        - Debug data dict if debug_extraction is True, else None
    """
    results = []
    loc = sorry.location

    # Load file content once (same as LLMStrategy does)
    file_path = repo_path / loc.path
    file_text = file_path.read_text()

    # Extract context up to and including the sorry line (same as LLMStrategy)
    context_lines = file_text.splitlines()[:loc.end_line]
    context = "\n".join(context_lines)

    logger.info(f"Replay mode: processing {len(responses)} pre-stored LLM responses")
    logger.info(f"Context length: {len(context)} chars, {len(context_lines)} lines")

    # Collect debug data if enabled
    debug_attempts = [] if debug_extraction else None

    for i, response in enumerate(responses, 1):
        logger.info(f"Replay attempt {i}/{len(responses)}: extracting proof from response ({len(response)} chars)")

        # Log the full LLM response for debugging (same format as normal runs)
        logger.info(f"Full LLM response:\n{response}")

        # Extract proof using the (fixed) extraction algorithm
        proof = extract_proof_from_diff(context, response, loc)

        if proof is None:
            logger.warning(f"Replay attempt {i}: extraction returned None (failed to extract proof)")
            results.append((None, {"replay": True, "extraction_failed": True}))
        else:
            logger.info(f"Extracted proof: {proof}")
            logger.info(f"Replay attempt {i}: extracted proof ({len(proof)} chars)")
            results.append((proof, {"replay": True}))

        # Collect debug data for this attempt
        if debug_extraction:
            debug_attempts.append({
                "attempt_index": i,
                "llm_response": response,
                "extracted_proof": proof,
            })

    logger.info(f"Replay extraction complete. {len([r for r in results if r[0] is not None])}/{len(responses)} proofs extracted")

    # Build debug data structure
    debug_data = None
    if debug_extraction:
        debug_data = {
            "sorry_id": sorry.id,
            "context": context,
            "location": {
                "path": loc.path,
                "start_line": loc.start_line,
                "start_column": loc.start_column,
                "end_line": loc.end_line,
                "end_column": loc.end_column,
            },
            "attempts": debug_attempts,
        }

    return results, debug_data


def create_strategy_from_spec(spec_json: str | None) -> tuple:
    """Create a strategy instance from a JSON string spec and extract k and llm_timeout parameters.

    Spec shape:
    {"name": "agentic" | "llm" | "tactic" | "cloud_llm" | "rfl" | "simp" | "norm_num" | "supersimple" | "multi_tactic", "args": { ... }}

    For "multi_tactic" strategy, returns a list of SingleTacticStrategy instances.
    Use args.tactics to specify which tactics to try (defaults to DEFAULT_TACTICS).
    Use args.k to specify the number of pass@k attempts (defaults to 1).
    Use args.llm_timeout to specify timeout in seconds for each LLM call (defaults to LLM_CALL_TIMEOUT).

    Returns:
        tuple: (strategy or list of strategies, k value for pass@k, llm_timeout in seconds)
    """
    logger = logging.getLogger(__name__)

    if not spec_json:
        # Default to agentic with defaults
        logger.info("No strategy spec provided, using default AgenticStrategy")
        return AgenticStrategy(), 1, LLM_CALL_TIMEOUT

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
    # Extract llm_timeout (remove from args so it's not passed to strategy constructors)
    llm_timeout = args.pop("llm_timeout", LLM_CALL_TIMEOUT) if isinstance(args, dict) else LLM_CALL_TIMEOUT

    logger.info(f"Strategy name: {name}")
    logger.info(f"Strategy args: {args}")
    logger.info(f"Pass@k value: {k}")
    logger.info(f"LLM call timeout: {llm_timeout}s")

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
            return AgenticStrategy(**args), k, llm_timeout

        case "llm":
            return LLMStrategy(**args), k, llm_timeout

        case "tactic":
            if "strategy_mode" in args and isinstance(args["strategy_mode"], str):
                args = {**args}
                args["strategy_mode"] = StrategyMode(
                    args["strategy_mode"]
                )  # may raise ValueError
            return TacticByTacticStrategy(**args), k, llm_timeout

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
            ), k, llm_timeout

        case "rfl":
            return RflStrategy(), k, llm_timeout

        case "simp":
            return SimpStrategy(), k, llm_timeout

        case "norm_num":
            return NormNumStrategy(), k, llm_timeout

        case "supersimple":
            return ProveAllStrategy(), k, llm_timeout

        case "multi_tactic":
            tactics = args.get("tactics", DEFAULT_TACTICS)
            logger.info(f"Creating multi_tactic strategy with tactics: {tactics}")
            return [SingleTacticStrategy(t) for t in tactics], k, llm_timeout

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
    try:
        file_handler = logging.FileHandler('/root/repo/run.log')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logging.getLogger().addHandler(file_handler)
    except Exception as e:
        # Allow running this script also locally for debugging
        print(e)
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
    argparser.add_argument(
        "--replay-responses",
        type=str,
        required=False,
        help=(
            "JSON string containing a list of pre-stored LLM responses to replay. "
            "When provided, skips LLM calls and uses these responses for proof extraction "
            "and verification. Used for re-running experiments with a fixed extraction algorithm."
        ),
    )
    argparser.add_argument(
        "--replay-responses-file",
        type=str,
        required=False,
        help=(
            "Path to a JSON file containing a list of pre-stored LLM responses to replay. "
            "Alternative to --replay-responses for large response sets that exceed argument limits."
        ),
    )
    argparser.add_argument(
        "--debug-extraction",
        action="store_true",
        default=False,
        help=(
            "When in replay mode, output a debug JSON file containing LLM responses, "
            "context, and extracted proofs. File is written to {repo-path}/debug_extraction.json"
        ),
    )

    args = argparser.parse_args()
    logger.info(f"Full command: {' '.join(sys.argv)}")
    logger.info(f"Arguments parsed: repo_path={args.repo_path}, output_path={args.output_path}")
    logger.info(f"Strategy spec: {args.agent_strategy[:100] if args.agent_strategy else 'None'}...")
    logger.info(f"Replay mode: {'ENABLED' if args.replay_responses or args.replay_responses_file else 'disabled'}")

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
        # Parse replay responses if provided (for replay mode)
        replay_responses = None
        if args.replay_responses_file:
            logger.info(f"Loading replay responses from file: {args.replay_responses_file}")
            try:
                with open(args.replay_responses_file, "r") as f:
                    replay_responses = json.load(f)
                if not isinstance(replay_responses, list):
                    raise ValueError("replay_responses must be a JSON array of strings")
                logger.info(f"Replay mode: loaded {len(replay_responses)} pre-stored LLM responses from file")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse replay responses file: {e}")
                raise ValueError(f"Invalid JSON in --replay-responses-file: {e}") from e
            except FileNotFoundError as e:
                logger.error(f"Replay responses file not found: {args.replay_responses_file}")
                raise ValueError(f"File not found: {args.replay_responses_file}") from e
        elif args.replay_responses:
            logger.info("Parsing replay responses JSON from argument...")
            try:
                replay_responses = json.loads(args.replay_responses)
                if not isinstance(replay_responses, list):
                    raise ValueError("replay_responses must be a JSON array of strings")
                logger.info(f"Replay mode: loaded {len(replay_responses)} pre-stored LLM responses")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse replay responses JSON: {e}")
                raise ValueError(f"Invalid JSON for --replay-responses: {e}") from e

        # Only create strategy if NOT in replay mode
        strategies = []
        k = 1
        llm_timeout = LLM_CALL_TIMEOUT
        if replay_responses is None:
            logger.info("Creating strategy from spec...")
            strategies, k, llm_timeout = create_strategy_from_spec(args.agent_strategy)
            # Normalize to list for uniform handling
            if not isinstance(strategies, list):
                strategies = [strategies]
            logger.info(f"Strategies created: {[s.name() if hasattr(s, 'name') else type(s).__name__ for s in strategies]}")
            logger.info(f"Pass@k value: {k}")
            logger.info(f"LLM call timeout: {llm_timeout}s")
        else:
            logger.info("Replay mode: skipping strategy creation (no LLM calls will be made)")
            # Cap replay responses to avoid replaying retried attempts
            MAX_REPLAY_RESPONSES = 32
            if len(replay_responses) > MAX_REPLAY_RESPONSES:
                logger.info(f"Capping replay responses from {len(replay_responses)} to {MAX_REPLAY_RESPONSES}")
                replay_responses = replay_responses[:MAX_REPLAY_RESPONSES]

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

        # Create VerificationContext ONCE for efficient pass@k verification
        # This shares the LeanServer and original file analysis across all k attempts
        logger.info("Creating VerificationContext for pass@k verification...")
        verify_ctx = VerificationContext(Path(args.repo_path), sorry.location)
        logger.info("VerificationContext created successfully")

        # Pass@k: iterate through strategies, each gets k attempts, run ALL attempts
        results = []
        failed_attempts = []  # Collect all failed proof attempts
        successful_attempts = []  # Collect all verified proofs
        # Track CUMULATIVE token usage across all attempts
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0

        # REPLAY MODE: use pre-stored responses instead of calling LLM
        if replay_responses is not None:
            logger.info(f"=" * 40)
            logger.info(f"REPLAY MODE: extracting proofs from {len(replay_responses)} pre-stored responses")
            if args.debug_extraction:
                logger.info("Debug extraction enabled")

            # Extract proofs from stored responses (no LLM calls)
            proof_results, debug_data = replay_from_responses(
                replay_responses, Path(args.repo_path), sorry, logger,
                debug_extraction=args.debug_extraction
            )
            logger.info(f"Replay extraction complete. Got {len(proof_results)} results.")

            # Write debug extraction file if enabled
            if args.debug_extraction and debug_data is not None:
                debug_file_path = Path(args.repo_path) / "debug_extraction.json"
                with open(debug_file_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
                logger.info(f"Wrote debug extraction file: {debug_file_path}")

            # Strategy name for replay mode
            strategy_name = "replay"
            k = len(replay_responses)

        # NORMAL MODE: iterate through strategies
        else:
            # This block generates proof_results via LLM
            for strategy in strategies:
                strategy_name = strategy.name() if hasattr(strategy, 'name') else type(strategy).__name__
                logger.info(f"=" * 40)
                logger.info(f"Trying strategy: {strategy_name} (generating {k} proofs in parallel)")

                # Generate all k proofs in parallel
                logger.info(f"Starting parallel proof generation for {k} attempts...")
                logger.info(f"Repository path: {args.repo_path}")
                proof_results = asyncio.run(
                    generate_proofs_parallel(
                        strategy, Path(args.repo_path), sorry, k, logger, llm_timeout
                    )
                )
                logger.info(f"Parallel proof generation complete. Got {len(proof_results)} results.")

        # Verify proofs serially (using shared VerificationContext)
        # This runs for both replay mode and normal mode
        for attempt, result in enumerate(proof_results, 1):
            logger.info(f"-" * 20)
            logger.info(f"Strategy {strategy_name}, verifying attempt {attempt}/{k}")

            # Handle exception results from parallel generation
            if isinstance(result, Exception):
                logger.warning(f"Attempt {attempt} failed with exception: {type(result).__name__}: {result}")
                failed_attempts.append(f"EXCEPTION: {type(result).__name__}: {result}")
                continue

            proof, usage = result

            # Accumulate usage from this attempt (for cost tracking)
            if usage:
                total_input_tokens += usage.get("input_tokens", 0)
                total_output_tokens += usage.get("output_tokens", 0)
                total_cost += usage.get("estimated_cost", 0)

            logger.info("Generated proof:")
            logger.info(proof)
            if proof:
                logger.info(f"Proof length: {len(proof)} chars")
            else:
                logger.warning("No proof generated (None)")

            proof_verified = False
            verification_message = None
            if proof:
                logger.info("Starting proof verification...")
                logger.info(f"Verifying at: {sorry.location.path}:{sorry.location.start_line}")
                proof_verified, error_msg = verify_ctx.verify_proof(proof)
                verification_message = error_msg if error_msg else "Proof verified successfully"
                logger.info("Proof verification completed")
            else:
                logger.info("Skipping verification (no proof generated)")
                verification_message = "No proof generated"

            logger.info(f"Strategy {strategy_name} attempt {attempt}: verified={proof_verified}")
            if verification_message:
                logger.info(f"Verification message: {verification_message}")

            if proof_verified:
                # SUCCESS: append to successful_attempts
                successful_attempts.append(proof)
                logger.info(f"SUCCESS! Proof verified on attempt {attempt}")
            else:
                # Verification failed - collect the attempt for visibility
                if proof is not None:
                    failed_attempts.append(proof)
                logger.info(f"Attempt {attempt} failed verification, continuing...")

        # Create final result with both successful and failed attempts
        # For replay mode: strategies is empty, so use k directly
        if replay_responses is not None:
            total_attempts = k
            strategy_names = "replay"
        else:
            total_attempts = len(strategies) * k
            strategy_names = "_".join(s.name() if hasattr(s, 'name') else type(s).__name__ for s in strategies)

        result = SorryResult(
            sorry=sorry,
            proof=successful_attempts[0] if successful_attempts else None,
            proof_verified=bool(successful_attempts),
            feedback=None,
            verification_message=f"{len(successful_attempts)} succeeded, {len(failed_attempts)} failed out of {total_attempts} attempts",
            strategy_name=f"{strategy_names}_pass_at_{k}",
            successful_attempts=successful_attempts if successful_attempts else None,
            failed_attempts=failed_attempts if failed_attempts else None,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            estimated_cost=total_cost,
        )
        results = [result]

        logger.info(f"=" * 40)
        logger.info(f"Pass@k completed. Total attempts: {total_attempts}")
        logger.info(f"Successful: {len(successful_attempts)}, Failed: {len(failed_attempts)}")

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

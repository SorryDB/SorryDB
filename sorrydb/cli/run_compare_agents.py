#!/usr/bin/env python3

import argparse
import json
import logging
import sys
from pathlib import Path

import modal

from sorrydb.agents.cloud_llm_strategy import CloudLLMStrategy
from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.agents.llm_proof_utils import NO_CONTEXT_PROMPT
from sorrydb.agents.modal_app import app
from sorrydb.agents.modal_hugging_face_provider import (
    ModalDeepseekProverLLMProvider,
    ModalKiminaLLMProvider,
)
from sorrydb.agents.strategy_comparison_agent import StrategyComparisonAgent
from sorrydb.agents.rfl_strategy import NormNumStrategy, RflStrategy, SimpStrategy

TEST_STRATEGIES: list[SorryStrategy] = [
    RflStrategy(),
    SimpStrategy(),
    NormNumStrategy(),
]

USE_TEST_STRATEGIES = True


def main():
    parser = argparse.ArgumentParser(description="Reproduce a sorry with REPL.")
    parser.add_argument(
        "--sorry-file",
        type=str,
        required=True,
        help="Path to the sorry JSON file",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        required=True,
        help="Path to the output JSON file",
    )
    parser.add_argument(
        "--lean-data",
        type=str,
        default=None,
        help="Directory to store Lean data (default: use temporary directory)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-file", type=str, help="Log file path (default: output to stdout)"
    )

    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Do not build the Lean package or verify the sorry results",
    )
    parser.add_argument(
        "--llm-debug-info",
        type=str,
        default="modal_debug_info.json",
        help="Path to save llm debug info JSON (default: ./modal_debug_info.json)",
    )
    args = parser.parse_args()

    # Configure logging
    log_kwargs = {
        "level": getattr(logging, args.log_level),
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    }
    if args.log_file:
        log_kwargs["filename"] = args.log_file
    logging.basicConfig(**log_kwargs)

    logger = logging.getLogger(__name__)
    # Convert file names arguments to Path
    sorry_file = Path(args.sorry_file)
    output_file = Path(args.output_file)

    if args.lean_data:
        lean_data_path = Path(args.lean_data)
        # If lean_data is provided, make sure it exists
        lean_data_path.mkdir(exist_ok=True)
    else:
        lean_data_path = None

    # Process the sorry JSON file
    try:
        logger.info(f"Solving sorries from: {sorry_file} using compare agents")
        agent = StrategyComparisonAgent(lean_data_path)

        agent.load_sorries(sorry_file, build_lean_projects=not args.no_verify)

        if USE_TEST_STRATEGIES:
            for strategy in TEST_STRATEGIES:
                agent.attempt_sorries(strategy)
                agent.write_report(output_file)

        else:
            with modal.enable_output():  # this context manager enables modals logging
                with app.run():
                    deepseek_provider = ModalDeepseekProverLLMProvider()
                    deepseek_strategy = CloudLLMStrategy(
                        deepseek_provider,
                        prompt=NO_CONTEXT_PROMPT,
                        debug_info_path=args.llm_debug_info,
                    )
                    agent.attempt_sorries(deepseek_strategy)

                    kimina_modal_provider = ModalKiminaLLMProvider()
                    kimina_strategy = CloudLLMStrategy(
                        kimina_modal_provider,
                        prompt=NO_CONTEXT_PROMPT,
                        debug_info_path=args.llm_debug_info,
                    )
                    agent.attempt_sorries(kimina_strategy)

        if not args.no_verify:
            agent.verify_proofs()
            agent.write_report(output_file)

        return 0

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3

import argparse
import json
import logging
import sys
from pathlib import Path

import modal

from sorrydb.runners.cloud_llm_strategy import CloudLLMStrategy
from sorrydb.runners.llm_proof_utils import NO_CONTEXT_PROMPT
from sorrydb.runners.modal_app import app
from sorrydb.runners.modal_hugging_face_provider import ModalDeepseekProverLLMProvider
from sorrydb.runners.strategy_comparison_runner import StrategyComparisonRunner


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
        default="lean_data",
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
        logger.info(
            f"Solving sorries from: {sorry_file} using ModalHuggingFaceStrategy"
        )
        runner = StrategyComparisonRunner(lean_data_path)

        runner.load_sorries(sorry_file, build_lean_projects=not args.no_verify)

        with modal.enable_output():  # this context manager enables modals logging
            with app.run():
                modal_provider = ModalDeepseekProverLLMProvider()
                modal_strategy = CloudLLMStrategy(
                    modal_provider,
                    prompt=NO_CONTEXT_PROMPT,
                    debug_info_path=args.llm_debug_info,
                )
                runner.attempt_sorries(modal_strategy)

        if not args.no_verify:
            runner.verify_proofs()
            runner.write_report(output_file)

        return 0

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())

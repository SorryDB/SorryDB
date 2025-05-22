#!/usr/bin/env python3

"""Run a tactic-by-tactic agent on a sorry."""

import argparse
import json
import logging
import sys
from pathlib import Path

from sorrydb.agents.json_agent import JsonAgent
from sorrydb.agents.tactic_strategy import StrategyMode, TacticByTacticStrategy


def main():
    """Main function to run the tactic-by-tactic agent."""
    parser = argparse.ArgumentParser(
        description="Run a tactic-by-tactic agent on a specified sorry."
    )
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
        "--strategy-mode",
        type=str,
        choices=[mode.value for mode in StrategyMode],
        default=StrategyMode.LLM.value,
        help=f"Strategy mode to use: {', '.join([mode.value for mode in StrategyMode])}",
    )
    parser.add_argument(
        "--model-json",
        type=str,
        default=None,
        help="Path to the model config JSON file (default: None)",
    )
    parser.add_argument(
        "--lean-data",
        type=str,
        default=None,
        help="Directory to store Lean data (default: use temporary directory)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum number of proof step attempts (default: 100).",
    )
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=3,
        help="Maximum number of consecutive tactic failures before giving up (default: 3).",
    )
    # Logging options
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
    lean_data = Path(args.lean_data) if args.lean_data else None

    # Load model config if provided
    model_config = None
    if args.model_json:
        try:
            with open(args.model_json, "r") as f:
                model_config = json.load(f)
        except FileNotFoundError as e:
            logger.error(f"Model config file not found: {e}")
            return 1
        except json.JSONDecodeError as e:
            logger.error(f"Invalid model config JSON: {e}")
            return 1

    # Process the sorry JSON file
    try:
        logger.info(f"Solving sorries from: {sorry_file}")

        # Set the strategy mode
        strategy_mode = StrategyMode(args.strategy_mode)

        # Configure the tactic strategy
        tactic_strategy = TacticByTacticStrategy(
            strategy_mode=strategy_mode,
            model_config=model_config,
            max_consecutive_failures=args.max_consecutive_failures,
            max_iterations=args.max_iterations,
        )

        # Set any additional parameters from command line
        if hasattr(tactic_strategy, "max_consecutive_failures"):
            tactic_strategy.max_consecutive_failures = args.max_consecutive_failures

        # Create and run the agent
        agent = JsonAgent(tactic_strategy, lean_data)
        agent.process_sorries(sorry_file, output_file)
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

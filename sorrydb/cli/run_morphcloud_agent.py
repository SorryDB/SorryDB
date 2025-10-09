#!/usr/bin/env python3

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from sorrydb.agents.morphcloud_agent import MorphCloudAgent


def main():
    parser = argparse.ArgumentParser(
        description="Run agent on MorphCloud instances for parallel proof generation"
    )
    parser.add_argument(
        "--sorry-file",
        type=str,
        required=True,
        help="Path to the sorry JSON file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="Directory to save results (default: outputs)",
    )
    parser.add_argument(
        "--agent-strategy",
        type=str,
        default='{"name": "rfl"}',
        help=(
            "JSON spec for the strategy to use. Example: "
            '\'{"name": "agentic", "args": {"max_iterations": 3}}\'. '
            "Available names: agentic, llm, tactic, cloud_llm, rfl, simp, norm_num"
        ),
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of concurrent workers for both repository preparation and instance execution (default: 4)",
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

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Configure logging
    log_kwargs = {
        "level": getattr(logging, args.log_level),
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    }
    if args.log_file:
        log_kwargs["filename"] = args.log_file
    logging.basicConfig(**log_kwargs)
    logger = logging.getLogger(__name__)

    # Parse strategy spec
    try:
        strategy_spec = json.loads(args.agent_strategy)
        strategy_name = strategy_spec.get("name", "rfl")
        strategy_args = strategy_spec.get("args", {})
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON for --agent-strategy: {e}")
        return 1

    # Convert file paths
    sorry_file = Path(args.sorry_file)
    output_dir = Path(args.output_dir)

    # Create and run agent
    try:
        logger.info(f"Processing sorries from: {sorry_file}")
        logger.info(f"Using strategy: {strategy_name} with args: {strategy_args}")
        logger.info(f"Max workers: {args.max_workers}")

        agent = MorphCloudAgent(
            strategy_name=strategy_name,
            strategy_args=strategy_args,
            batch_size=args.max_workers,
            max_workers=args.max_workers,
        )

        results = agent.process_sorries(sorry_file, output_dir)
        logger.info(f"Successfully processed {len(results)} sorries")
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

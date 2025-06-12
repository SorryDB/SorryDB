#!/usr/bin/env python3

import argparse
import logging

from sorrydb.agents.sagemaker_hugging_face_strategy import (
    SagemakerHuggingFaceEndpointManager,
)


def main():
    parser = argparse.ArgumentParser(description="Reproduce a sorry with REPL.")

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

    manager = SagemakerHuggingFaceEndpointManager()
    try:
        predictor = manager.deploy()
        print(f"Endpoint '{predictor.endpoint_name}' is active.")
    except Exception as e:
        print(f"Failed to deploy: {e}")
        manager.delete()

#!/usr/bin/env python3

import argparse
import logging

from sorrydb.runners.sagemaker_hugging_face_provider import (
    SagemakerHuggingFaceEndpointManager,
)


def main():
    parser = argparse.ArgumentParser(
        description="Deploy a sagemaker endpoint using the default settings in `SagemakerHuggingFaceEndpointManager`. Useful for testing."
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
        logger.info("'Trying to deploy endpoint")
        predictor = manager.deploy()
        logger.info(f"Endpoint deployed: {predictor.endpoint_name}")
    except Exception as e:
        logger.error(f"Failed to deploy: {e}")
        manager.delete()


if __name__ == "__main__":
    main()

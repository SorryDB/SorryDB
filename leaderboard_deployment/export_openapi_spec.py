#!/usr/bin/env python3
"""
Script to export the OpenAPI specification from the FastAPI app.
This can be used to generate API documentation or client libraries.
"""

import json
import sys
from pathlib import Path

# Add the project root to the Python path so we can import the app
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sorrydb.leaderboard.api.app import app


def export_openapi_spec(output_file: str = "openapi.json"):
    """Export the OpenAPI specification to a JSON file."""
    openapi_schema = app.openapi()
    
    with open(output_file, "w") as f:
        json.dump(openapi_schema, f, indent=2)
    
    print(f"OpenAPI specification exported to {output_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Export OpenAPI specification")
    parser.add_argument(
        "--output", 
        "-o", 
        default="openapi.json",
        help="Output file path (default: openapi.json)"
    )
    
    args = parser.parse_args()
    export_openapi_spec(args.output)

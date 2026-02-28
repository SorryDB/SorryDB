"""Utilities for extracting proof bodies from LLM-generated theorems."""

import logging
import re

logger = logging.getLogger(__name__)


def extract_proof_body_from_theorem(llm_output: str) -> str | None:
    """Extract the proof body from an LLM's theorem output.

    Looks for a theorem definition with `:=` and extracts everything after it.
    Handles both term-mode proofs and tactic-mode proofs (with `by`).

    Args:
        llm_output: The raw LLM output containing a theorem

    Returns:
        The proof body (everything after `:=`), or None if not found
    """
    # First, try to extract code from markdown code blocks
    code_block_pattern = r"```(?:lean4?|lean)?\s*\n(.*?)```"
    code_matches = re.findall(code_block_pattern, llm_output, re.DOTALL)

    # Use the last code block if present, otherwise use the raw output
    text_to_parse = code_matches[-1] if code_matches else llm_output

    # Find the theorem definition and extract the body
    # Pattern matches: theorem name ... := <body>
    # We need to handle multi-line bodies and nested structures

    # Look for := that marks the start of the proof body
    # This regex finds "theorem ... :=" and captures everything after
    theorem_pattern = r"theorem\s+\w+[^:]*:=\s*(.*)$"
    match = re.search(theorem_pattern, text_to_parse, re.DOTALL)

    if not match:
        logger.warning("Could not find theorem body in LLM output")
        logger.debug(f"LLM output (first 500 chars): {llm_output[:500]}")
        return None

    body = match.group(1).strip()

    # Remove trailing "sorry" if present (the LLM might not have solved it)
    if body == "sorry":
        logger.warning("LLM output contains only 'sorry' as proof body")
        return None

    # Clean up the body - remove any trailing comments or extra content
    # Stop at any new top-level declaration
    declaration_keywords = [
        "\ntheorem ",
        "\nlemma ",
        "\ndef ",
        "\nstructure ",
        "\ninductive ",
        "\nclass ",
        "\ninstance ",
        "\naxiom ",
        "\n#",
    ]

    for keyword in declaration_keywords:
        if keyword in body:
            body = body[: body.index(keyword)]

    body = body.strip()

    if not body:
        logger.warning("Extracted empty proof body")
        return None

    logger.info(f"Extracted proof body: {body[:100]}...")
    return body


def wrap_as_exact_by(proof_body: str) -> str:
    """Transform a proof body to `exact (by {{BODY}})` format.

    If the body starts with `by`, wraps it as `exact (by <tactics>)`.
    If the body is a term, wraps it as `exact (<term>)`.

    Args:
        proof_body: The proof body extracted from a theorem

    Returns:
        The wrapped proof string suitable for replacing a sorry
    """
    proof_body = proof_body.strip()

    if proof_body.startswith("by"):
        # Extract the tactics after "by"
        tactics = proof_body[2:].strip()
        result = f"exact (by {tactics})"
    else:
        # It's a term-mode proof
        result = f"exact ({proof_body})"

    logger.info(f"Wrapped proof: {result[:100]}...")
    return result

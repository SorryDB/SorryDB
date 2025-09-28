import logging
import re
from pathlib import Path

from sorrydb.database.sorry import Sorry

logger = logging.getLogger(__name__)


def extract_proof_from_code_block(proof):
    # Extract code from ```lean or ```lean4 code block if present
    if "```lean4" in proof or "```lean" in proof:
        # Find all code blocks for both ```lean4 and ```lean
        matches = list(re.finditer(r"```lean4?\s*([\s\S]*?)```", proof))
        if matches:
            proof = matches[-1].group(1)
    return proof.strip()


def extract_proof_from_full_theorem_statement(stmt: str):
    # Match := by, :=, or by as proof introducer (with optional whitespace)
    # TODO: Consider cases where there is a `:=` in the way,
    # e.g. `theorem proof : { data := #[1.0, 2.0, 3.0, 4.0, 3.0] }.toByteArray.size % 8 = 0 := by`
    match = re.search(
        r"^(lemma|theorem|example)(?:.|\n)*?(?::=\s*by\b|:=\s*by\b|:=|by\b)",
        stmt,
        re.MULTILINE,
    )
    if not match:
        return stmt
    # The proof starts after the introducer
    proof_start = match.end()
    proof = stmt[proof_start:]
    # Remove leading/trailing whitespace/newlines
    return proof.strip()


def extract_context(repo_path: Path, sorry: Sorry) -> tuple[str, str]:
    loc = sorry.location
    file_path = repo_path / loc.path
    file_text = file_path.read_text()

    lines = file_text.splitlines()
    top_context_lines = lines[:50]
    pre_sorry_context_lines = lines[max(0, loc.start_line - 20) : loc.start_line]
    context_top = "\n".join(top_context_lines)
    context_pre_sorry = "\n".join(pre_sorry_context_lines)

    return context_top, context_pre_sorry


def deepseek_post_processing(raw_llm_response: str) -> tuple[str, dict]:
    """The steps of postprocessing steps that seem to work for deepseek provers responses"""
    intermediate_processing_steps = {}
    # Process the proof
    # If the proof given includes the theorm statement
    # extract just the proof that will replace the sorry
    extracted_proof = extract_proof_from_code_block(raw_llm_response)
    intermediate_processing_steps["extracted_proof"] = extracted_proof
    logger.info(f"Extacted proof: {extracted_proof}")
    no_theorem_statement_proof = extract_proof_from_full_theorem_statement(
        extracted_proof
    )
    logger.info(f"No theorem statement proof: {no_theorem_statement_proof}")
    intermediate_processing_steps["no_theorem_statement_proof"] = (
        no_theorem_statement_proof
    )
    # TODO: consider removing this one as it can produce extra indentation
    # UPDATE: For now I am going to remove this
    # processed_proof = preprocess_proof(no_theorem_statement_proof, start_column)
    processed_proof = no_theorem_statement_proof

    intermediate_processing_steps["processed_proof"] = processed_proof
    logger.info(f"Fully processed proof: {processed_proof}")
    logger.info(f"Generated proof: {processed_proof}")
    return processed_proof, intermediate_processing_steps


DEEPSEEK_PROMPT = """You are an advanced AI that has studied all known mathematics.
Consider the following Lean code (top of file):

```lean
{context_top}
```

And the lines immediately before the sorry:

```lean
{context_pre_sorry}
```

The final line contains a sorry at column {column}. It's proof goal is

```lean
{goal}
```

Write Lean 4 code to exactly replace "sorry" with a proof of the goal above.

You cannot import any additional libraries to the ones already imported in the file.
Write a short, simple and elegant proof.
Do not re-state the theorem or "by".
ONLY WRITE EXACTLY THE CODE TO REPLACE THE SORRY, including indentation.
DO NOT WRITE ANY COMMENTS OR EXPLANATIONS! Just write code!
"""

# Prompt without extensive code context to try and reduce the input token size
NO_CONTEXT_PROMPT = """You are an advanced AI that has studied all known mathematics.
Consider the following Lean code (top of file):

And the lines immediately before the sorry:

```lean
{context_pre_sorry}
```

The final line contains a sorry at column {column}. It's proof goal is

```lean
{goal}
```

Write Lean 4 code to exactly replace "sorry" with a proof of the goal above.

You cannot import any additional libraries to the ones already imported in the file.
Write a short, simple and elegant proof.
Do not re-state the theorem or "by".
ONLY WRITE EXACTLY THE CODE TO REPLACE THE SORRY, including indentation.
DO NOT WRITE ANY COMMENTS OR EXPLANATIONS! Just write code!
"""

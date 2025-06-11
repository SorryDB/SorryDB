# EXAMPLE PROMPTS IN LITERATURE
# https://github.com/cmu-l3/llmlean/blob/77448d68e51166f60bd43c6284b43d65209321b0/LLMlean/API.lean#L258
# https://plmlab.math.cnrs.fr/nuccio/octonions/-/blob/c3569703fd17191c279908509b8845735d5c507e/Mathlib/Tactic/GPT/Sagredo/Dialog.lean
# https://github.com/GasStationManager/LeanTool/blob/main/leantool.py
# https://github.com/quinn-dougherty/fvapps/blob/master/src/baselines/baselines_config.py
# https://github.com/Goedel-LM/Goedel-Prover/blob/5988bb0e3650f0417b61da4b10885e7ad6ca75fc/prover/utils.py#L23
# https://github.com/lean-dojo/LeanCopilot/blob/e2aebdab8e9b1c74a5334b36ba2c288c5a5f175d/python/external_models/hf_runner.py#L41
# https://github.com/oOo0oOo/lean-scribe/blob/main/default_scribe_folder/default_prompts/progress_in_proof.md


PROMPT = """You are an advanced AI that has studied all known mathematics.
Consider the following Lean code:

```lean
{context}
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


def preprocess_proof(proof: str, base_indentation: int) -> str:
    """Process the proof to increase the chance of success.

    Args:
        proof: Proof as a string
        base_indentation: Base indentation level of the sorry

    Returns:
        Processed proof
    """
    # Extract code from ```lean ``` code block if it is present
    if "```lean" in proof:
        proof = proof.split("```lean")[1].split("```")[0]

    # Remove "by" at the beginning of the proof
    if proof.startswith("by"):
        proof = proof[2:]

    # Remove empty lines and base indentation
    lines = [line for line in proof.split("\n") if line.strip()]

    if not lines:
        return ""

    # First line is never indented
    lines[0] = lines[0].lstrip()

    # If we only have one line, just return it
    if len(lines) == 1:
        return lines[0]

    # Second line is only indented more than base indentation if:
    # - Ends with by
    # - Is refine
    expected_indentation = base_indentation
    if lines[0].endswith("by") or lines[0].strip() == "refine":
        expected_indentation += 2

    # Assume all following lines are indented the same
    actual_indentation = len(lines[1]) - len(lines[1].lstrip())
    difference = actual_indentation - expected_indentation
    if difference < 0:
        # Increase indentation of all lines
        lines = [lines[0]] + ["  " * abs(difference) + line for line in lines[1:]]
    elif difference > 0:
        # Decrease indentation of all lines
        lines = [lines[0]] + [line[difference:] for line in lines[1:]]

    return "\n".join(lines)

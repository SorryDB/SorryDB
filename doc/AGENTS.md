# Sorry-proving agents



## Specification

The input to an agent is a JSON file with a list of sorries, as specified in
[DATABASE.md](DATABASE.md). 
The output is a JSON containg the same list of sorries, but where each record
contains a new field `proof` containing either `null` or a
proof string to replace the sorry string.

See [sample_sorry_list.json](sample_sorry_list.json) and
[sample_proof_list.json](sample_proof_list.json) for sample input and output files.

## Template agents

To aid the development of agents, we provide two naive sample agents.

### `llm_prover`

### `rfl_prover`
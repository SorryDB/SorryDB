# Sorry-proving agents

Sorry-proving *agents* attempt to fill sorries provided by SorryDB. They
recreate the repository locally, locate the sorry, and use symbolic or neural
tools to attempt to find a proof of the sorry. The "context" consists of all
definitions above the given sorry in the current file, and all (transitively)
imported files. In particular, this may include all or part of Mathlib. It is
the responsibility of the agent to extract the relevant information from this context.

## Specification

The input to an agent is a JSON file with a list of sorries, as specified in
[DATABASE.md](DATABASE.md).
The output is a JSON containing the same list of sorries, but where each record
contains a new field `proof` containing either `null` or a
proof string to replace the sorry string.

See [sample_sorry_list.json](sample_sorry_list.json) and
[sample_proof_list.json](sample_proof_list.json) for sample input and output files.

## Datasets

To develop, test, or benchmark agents, one can use various lists of sorries:

1. [sample_sorry_list.json](sample_sorry_list.json) with 2 easy "mock" sorries
2. A static list of sorries from [sorrydb-data](https://github.com/SorryDB/sorrydb-data), for example [this list of 100 sorries](https://github.com/SorryDB/sorrydb-data/blob/master/static_100_varied_recent_deduplicated_sorries.json)
3. The nightly updated [deduplicated_sorries.json](https://github.com/SorryDB/sorrydb-data/blob/master/deduplicated_sorries.json)

## Demo agents

To aid the development of agents, we provide two naive sample agents. These are
not meant for consumption, but we hope they can serve as templates for the
development of more serious agents.

### rfl_agent

The agent `rfl_agent` simply attempts to replace each sorry with the tactic
`rfl`. Usage:

`poetry run sorrydb/cli/run_rfl_agent.py --sorry-file doc/sample_sorry_list.json
--output-file proofs.json`

### llm_agent

The agent `llm_agent` does a one-shot attempt at generating a full proof with a
large language model. It uses [langchain](https://www.langchain.com/langchain)
and at present works with models from Anthropic, OpenAI or Google. To run this
agent:

1. Get an API key for the model of your choice

2. Create a `.env` file in the root of this repository, and add your keys:

```
ANTHROPIC_API_KEY=your-key
GOOGLE_API_KEY=your-key
OPENAI_API_KEY=your-key
```

3. Create a configuration file, see [sample_llm_config.json](sample_llm_config.json) for a sample using Claude from [Anthropic](https://www.anthropic.com/).

4. Run the agent using poetry:

`poetry run sorrydb/cli/run_llm_agent.py --sorry-file doc/sample_sorry_list.json --model-json doc/sample_llm_config.json --output-file proofs.json`

### tactic_agent

The agent `tactic_agent` uses a large language model to generate a tactic-by-tactic proof through interaction with the Lean REPL.

Using an LLM:

`poetry run sorrydb/cli/run_tactic_agent.py --max-context-lines 100 --sorry-file doc/sample_sorry_list.json --model-json doc/sample_llm_config.json --output-file proofs.json`

Users can also manually interact with sorries through the same interface provided to the LLM. In this mode, the script prompts the user for each sorry, allowing them to supply tactics to resolve it. These tactics are then executed, with the results displayed to the user. This interactive approach is particularly useful for debugging, and crafting more effective prompts for LLMs. You can run it with:

`poetry run sorrydb/cli/run_tactic_agent.py --max-context-lines 100 --sorry-file doc/sample_sorry_list.json --model-json doc/sample_llm_config.json --output-file proofs_interactive.json --strategy-mode interactive`

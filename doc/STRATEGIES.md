# Sorry-proving strategies

Sorry-proving *strategies* attempt to fill sorries provided by SorryDB. They
recreate the repository locally, locate the sorry, and use symbolic or neural
tools to attempt to find a proof of the sorry. The "context" consists of all
definitions above the given sorry in the current file, and all (transitively)
imported files. In particular, this may include all or part of Mathlib. It is
the responsibility of the strategy to extract the relevant information from this context.

## Specification

The input to a strategy is a JSON file with a list of sorries, as specified in
[DATABASE.md](DATABASE.md).
The output is a JSON containing the same list of sorries, but where each record
contains a new field `proof` containing either `null` or a
proof string to replace the sorry string.

See [sample_sorry_list.json](sample_sorry_list.json) and
[sample_proof_list.json](sample_proof_list.json) for sample input and output files.

## Datasets

To develop, test, or benchmark strategies, one can use various lists of sorries:

1. [sample_sorry_list.json](sample_sorry_list.json) with 2 easy "mock" sorries
2. A static list of sorries from [sorrydb-data](https://github.com/SorryDB/sorrydb-data), for example [this list of 100 sorries](https://github.com/SorryDB/sorrydb-data/blob/master/static_100_varied_recent_deduplicated_sorries.json)
3. The nightly updated [deduplicated_sorries.json](https://github.com/SorryDB/sorrydb-data/blob/master/deduplicated_sorries.json)

## Testing strategies
You can use the [SorryDB/Checklist](https://github.com/SorryDB/Checklist) repo and the corresponding `checklist_sorry_list.json` provided in the docs folder
to test your strategy against a variety sorry patterns which may present engineering challenges.

> [!NOTE]
> **SorryDB/Checklist** is for testing strategy engineering, not the effectiveness at proving.

## Efficiently comparing strategies
When building a strategy, you may want to compare it to existing strategies.
Or you may want compare multiple similar strategies to see which one performs best, for example by adjusting LLM parameters.
We provide a `StrategyComparisonRunner` which compares multiple sorry strategies while reusing the compiled Lean files and REPL setup to reduce the overall runtime.
This runner provides a few advantages over creating individual runners to compare:
- Sharing build files and REPL will reduce the required time when running more than one sorry strategy on the same set of sorries.
- It gives you fine grained control over the order in which you attempt and verify the sorries so that you can spin up an infrastructure only when you need it.
For example, only using GPUs when you actually need to attempt sorries, not when you are verifying them.
- It organizes the results into a report.

To use `StrategyComparisonRunner` you:
- Load the sorries and then you can attempt those sorries with as many sorry strategies as you would like.
- After you have attempted the sorries with all the strategies you wish, you can then verify all of the proofs at once.
- Finally you can generate a report of all the results. See the `run_compare_agents.py` script for an example. You can modify this script or create your own.

## Using a persistent location for compiled Lean files
Some SorryDB scripts provide a `--lean-data` option which allows the user to specify a directory
to store and reuse the compiled Lean files across different runs.
Reusing compile files can significantly improve runtime across multiple runs.
Note, these files take up a lot of disk space because most scripts don't share files across different repos.
Consider the trade off between disk space and run time when using the `--lean-data` option.


## Demo strategies

To aid the development of strategies, we provide naive sample strategies. These are
not meant for consumption, but we hope they can serve as templates for the
development of more serious strategies.

### rfl_strategy

The `rfl_strategy` simply attempts to replace each sorry with the tactic
`rfl`. Usage:

`poetry run sorrydb/cli/run_rfl_agent.py --sorry-file doc/sample_sorry_list.json
--output-file proofs.json`

### llm_strategy

The `llm_strategy` does a one-shot attempt at generating a full proof with a
large language model. It uses [langchain](https://www.langchain.com/langchain)
and at present works with models from Anthropic, OpenAI or Google. To run this
strategy:

1. Get an API key for the model of your choice

2. Create a `.env` file in the root of this repository, and add your keys:

```
ANTHROPIC_API_KEY=your-key
GOOGLE_API_KEY=your-key
OPENAI_API_KEY=your-key
```

3. Create a configuration file, see [sample_llm_config.json](sample_llm_config.json) for a sample using Claude from [Anthropic](https://www.anthropic.com/).

4. Run the strategy using poetry:

`poetry run sorrydb/cli/run_llm_agent.py --sorry-file doc/sample_sorry_list.json --model-json doc/sample_llm_config.json --output-file proofs.json`

### tactic_strategy

The `tactic_strategy` uses a large language model to generate a tactic-by-tactic proof through interaction with the Lean REPL.

Using an LLM:

`poetry run sorrydb/cli/run_tactic_agent.py --max-context-lines 100 --sorry-file doc/sample_sorry_list.json --model-json doc/sample_llm_config.json --output-file proofs.json`

Users can also manually interact with sorries through the same interface provided to the LLM. In this mode, the script prompts the user for each sorry, allowing them to supply tactics to resolve it. These tactics are then executed, with the results displayed to the user. This interactive approach is particularly useful for debugging, and crafting more effective prompts for LLMs. You can run it with:

`poetry run sorrydb/cli/run_tactic_agent.py --max-context-lines 100 --sorry-file doc/sample_sorry_list.json --model-json doc/sample_llm_config.json --output-file proofs_interactive.json --strategy-mode interactive`

### Building strategies with specialized language models and CloudLLMStrategy

AI labs build specialized models for writing Lean code,
some of which are available on Hugging Face,
for example, [DeepSeek Prover](https://huggingface.co/deepseek-ai/DeepSeek-Prover-V2-7B) and [Kamina Prover](https://huggingface.co/AI-MO/Kimina-Prover-Preview-Distill-7B).

We provide a `CloudLLMStrategy`, which you can use in combination with your own deployment of a specialized model to build a sorry strategy.

We provide two demo strategies built with `CloudLLMStrategy`
backed by different cloud computing platforms: [Amazon SageMaker](https://aws.amazon.com/sagemaker/) and [Modal](https://modal.com/).
Because the Modal implementation is more straightforward to get up and running with your own account, we recommend starting there.


> [!NOTE]
> To use these strategies, you must set up an account with a cloud computing provider and will likely pay for compute.
> Note: Modal has a generous free allotment of credits to get you started.


> [!WARNING]
> Deploying models on SageMaker or Modal and running inference can be expensive.
> Make sure you understand the pricing of the GPU instances.
> We recommend testing your strategy on a small set of sorries to understand the cost.

#### Running the Modal Deepseek Prover strategy
First, set up a Modal account and complete the [Getting started](https://modal.com/docs/guide) steps.

Then you can run the Modal strategy via the `run_modal_agent.py` script. For example:

`poetry run sorrydb/cli/run_modal_agent.py --sorry-file doc/sample_sorry_list.json --output-file proofs.json --no-verify`

> [!NOTE]
> You can use the `--no-verify` option to skip `lake build` and verification of the proof the strategy produces.
> This can significantly cut down on the strategy's run time, so we recommend using this option to avoid extra cloud compute costs.

The Modal strategy is configured to use `DeepSeek-Prover-V2-7B` by default, but with minor adjustments, it should work with other models hosted on Hugging Face.
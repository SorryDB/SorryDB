# Evaluation Commands

Example scripts to run evaluation with the morphcloud agent.

> **Note:** Work in progress — adapt as needed.

---

## For 100

poetry run python -m sorrydb.cli.run_morphcloud_agent       --sorry-file data/2025_12_experiment_all_reservoir/100_all_reservoir.json       --max-workers 25       --output-dir intermediate_experiment_outputs/gpt-5       --agent-strategy '{"name":"llm","args":{"model_config":{"provider":"openrouter","params":{"model":"openai/gpt-5.2"}}}}'

poetry run python -m sorrydb.cli.run_morphcloud_agent       --sorry-file data/2025_12_experiment_all_reservoir/100_all_reservoir.json       --max-workers 25       --output-dir intermediate_experiment_outputs_full_reservoir/qwen       --agent-strategy '{"name":"llm","args":{"model_config":{"provider":"openrouter","params":{"model":"qwen/qwen3-8b"}}}}'

poetry run python -m sorrydb.cli.run_morphcloud_agent     --sorry-file data/2025_12_experiment_all_reservoir/1000_all_reservoir.json     --max-workers 25     --output-dir intermediate_experiment_outputs_full_reservoir/multi_tactic     --agent-strategy '{"name":"multi_tactic"}'

poetry run python -m sorrydb.cli.run_morphcloud_agent \    
    --sorry-file doc/sample_sorry_list.json \
    --max-workers 25 \
    --output-dir output/goedel \
    --agent-strategy '{"name":"llm","args":{"model_config":{"provider":"goedel"}}}'


poetry run python -m sorrydb.cli.run_morphcloud_agent     --sorry-file data/2025_12_experiment_all_reservoir_3_months/100_3_months_reservoir.json --max-workers 25  --output-dir intermediate_experiment_outputs_full_reservoir_3_months/agentic/100 --agent-strategy '{         
    "name": "agentic",
    "args": {
      "model": "claude-sonnet-4-5",
      "max_iterations": 5,
      "enable_tools": false,
      "enable_thinking": true,
      "thinking_budget": 10000
    }
  }'
## Cloud Evaluation

| Strategy | Command |
|----------|---------|
| **RFL** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/rfl --agent-strategy '{"name": "rfl"}'` |
| **Super Simple** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/simple --agent-strategy '{"name": "supersimple"}'` |
| **Multi Tactic** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/multi_tactic --agent-strategy '{"name":"multi_tactic"}'` |
| **Claude (Anthropic)** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/claude --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "anthropic", "params": {"model": "claude-sonnet-4-5"}}}}'` |
| **Gemini Flash (Google)** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/gemini-flash --agent-strategy '{ "name": "llm", "args": {"k": 32, "model_config": {"provider": "google", "params": {"model": "gemini-3-flash-preview"}}}}'` |
| **GPT-5.2 (OpenAI)** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir intermediate_experiment_outputs_full_reservoir_3_months/gpt/1000 --agent-strategy '{"name":"llm","args":{"k":32,"model_config":{"provider":"openai","params":{"model":"gpt-5.2"}}}}'` |
| **Gemini (Google)** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/gemini-pro --agent-strategy '{ "name": "llm", "args": {"k": 32,"model_config": {"provider": "google", "params": {"model": "gemini-3-pro-preview"}}}}'` |
| **DeepSeek** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/deepseek --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "deepseek"}}}'` |
| **Kimina** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/kimina --agent-strategy '{"name": "llm", "args": {"k":32, "model_config": {"provider": "kimina"}}}'` |
| **Goedel** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/goedel --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "goedel"}}}'` |
| **Qwen** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/qwen --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "qwen"}}}'` |
| **Agentic Claude** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/agentic --agent-strategy '{"name": "agentic", "args": {"model": "claude-opus-4-5", "max_iterations": 16, "enable_tools": false}}'` |
| **Agentic Gemini** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/agentic --agent-strategy '{"name": "agentic", "args": {"model": "google_genai:gemini-3-flash-preview", "max_iterations": 16, "enable_tools": false}}'` |
| **Agentic Goedel** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/agentic --agent-strategy '{"name": "agentic", "args": {"model": "Goedel-LM/Goedel-Prover-V2-32B", "max_iterations": 16, "enable_tools": false, "enable_thinking": false, "max_tokens":3000}}'` |
| **Agentic With Tools** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 25 --output-dir outputs/agentic --agent-strategy '{"name": "agentic", "args": {"model": "claude-sonnet-4-5-20250929", "temperature": 0.7, "max_iterations": 16, "enable_tools": true}}'` |

---

## Local Evaluation

| Strategy | Command |
|----------|---------|
| **RFL** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "rfl"}' --output-path outputs/local` |
| **Super Simple** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "supersimple"}' --output-path outputs/local` |
| **Claude (Anthropic)** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "anthropic", "params": {"model": "claude-sonnet-4-5"}}}}' --output-path outputs/local` |
| **Gemini (Google)** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "google", "params": {"model": "gemini-3-flash-preview"}}}}' --output-path outputs/local` |
| **Gemini (Google)** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "google", "params": {"model": "gemini-3-pro-preview"}}}}' --output-path outputs/local` |
| **DeepSeek** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "deepseek"}}}' --output-path outputs/local` |
| **Kimina** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "kimina"}}}' --output-path outputs/local` |
| **Goedel** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "goedel"}}}' --output-path outputs/local` |
| **Qwen** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "qwen"}}}' --output-path outputs/local` |
| **Agentic Claude** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "agentic", "args": {"model": "claude-opus-4-5", "max_iterations": 16, "enable_tools": false}}' --output-path outputs/local` |
| **Agentic Gemini** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "agentic", "args": {"model": "google_genai:gemini-3-flash-preview", "max_iterations": 16, "enable_tools": false}}' --output-path outputs/local` |
| **Agentic Goedel** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "agentic", "args": {"model": "Goedel-LM/Goedel-Prover-V2-32B", "max_iterations": 16, "enable_tools": false, "enable_thinking": false, "max_tokens":3000}}' --output-path outputs/local` |
| **Agentic With Tools** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "agentic", "args": {"model": "claude-sonnet-4-5-20250929", "temperature": 0.7, "max_iterations": 16, "enable_tools": true}}' --output-path outputs/local` |

---

## Using API Provider Configuration

For DeepSeek, Kimina, and Goedel, you can use the `api_provider` parameter to choose between different API endpoints.

### Cloud Evaluation with API Provider

| Strategy | Command |
|----------|---------|
| **DeepSeek (API Provider)** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 100 --output-dir outputs/deepseek_api --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "deepseek", "params": {"api_provider": true}}}}'` |
| **Kimina (API Provider)** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 100 --output-dir outputs/kimina_api --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "kimina", "params": {"api_provider": true}}}}'` |
| **Goedel (API Provider)** | `poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/2025_12_experiment_all_reservoir_3_months/1000_3_months_reservoir.json --max-workers 100 --output-dir outputs/goedel_api --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "goedel", "params": {"api_provider": true}}}}'` |

### Local Evaluation with API Provider

| Strategy | Command |
|----------|---------|
| **DeepSeek (API Provider)** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "deepseek", "params": {"api_provider": true}}}}' --output-path outputs/local` |
| **Kimina (API Provider)** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "kimina", "params": {"api_provider": true}}}}' --output-path outputs/local` |
| **Goedel (API Provider)** | `poetry run python -m sorrydb.cli.run_morphcloud_local --repo-path tests/mock_lean_repository --sorry-path tests/mock_sorries/single_sorry.json --agent-strategy '{"name": "llm", "args": {"model_config": {"provider": "goedel", "params": {"api_provider": true}}}}' --output-path outputs/local` |

> **Note:** When `api_provider: true` is set:
> - **DeepSeek** uses OpenRouter API with `OPENROUTER_API_KEY`
> - **Kimina** uses HuggingFace Router with `HUGGINGFACE_API_KEY`
> - **Goedel** uses Featherless API with `FEATHERLESS_API_KEY`
>
> When `api_provider: false` (default), alternative configurations will be used (to be specified).

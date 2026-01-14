# Evaluation Commands

Example scripts to run evaluation with the morphcloud agent.

> **Note:** Work in progress — adapt as needed.

---

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

Base command:
```bash
poetry run python -m sorrydb.cli.run_morphcloud_agent \
  --sorry-file <path> \
  --max-workers <n> \
  --output-dir <path> \
  --agent-strategy '<json>'
```

### RFL Strategy

```bash
poetry run python -m sorrydb.cli.run_morphcloud_agent \
  --sorry-file data/100_recent_varied_sorries.json \
  --max-workers 100 \
  --output-dir outputs/rfl \
  --agent-strategy '{"name": "rfl"}'
```

### Super Simple Strategy

```bash
poetry run python -m sorrydb.cli.run_morphcloud_agent \
  --sorry-file data/100_recent_varied_sorries.json \
  --max-workers 100 \
  --output-dir outputs/simple \
  --agent-strategy '{"name": "supersimple"}'
```

### Multi Tactic Strategy

```bash
poetry run python -m sorrydb.cli.run_morphcloud_agent \
    --sorry-file doc/sample_sorry_list.json \
    --max-workers 25 \
    --output-dir outputs/ \
    --agent-strategy '{"name":"multi_tactic"}'
```

### LLM Strategies

#### Claude (Anthropic)

```bash
poetry run python -m sorrydb.cli.run_morphcloud_agent \
  --sorry-file mock_sorry_small.json \
  --max-workers 100 \
  --output-dir outputs/claude \
  --agent-strategy '{
    "name": "llm",
    "args": {
      "model_config": {
        "provider": "anthropic",
        "params": {"model": "claude-sonnet-4-5"}
      }
    }
  }'
```

#### Gemini (Google)

```bash
poetry run python -m sorrydb.cli.run_morphcloud_agent \
  --sorry-file mock_sorry_small.json \
  --max-workers 100 \
  --output-dir outputs/gemini \
  --agent-strategy '{
    "name": "llm",
    "args": {
      "model_config": {
        "provider": "google",
        "params": {"model": "gemini-3-flash-preview"}
      }
    }
  }'
```

#### DeepSeek

```bash
poetry run python -m sorrydb.cli.run_morphcloud_agent \
  --sorry-file mock_sorry_small.json \
  --max-workers 100 \
  --output-dir outputs/deepseek \
  --agent-strategy '{
    "name": "llm",
    "args": {
      "model_config": {"provider": "deepseek"}
    }
  }'
```

#### Kimina

```bash
poetry run python -m sorrydb.cli.run_morphcloud_agent \
  --sorry-file mock_sorry_small.json \
  --max-workers 100 \
  --output-dir outputs/kimina \
  --agent-strategy '{
    "name": "llm",
    "args": {
      "model_config": {"provider": "kimina"}
    }
  }'
```

### Agentic Strategy

```bash
poetry run python -m sorrydb.cli.run_morphcloud_agent \
  --sorry-file mock_sorry_small.json \
  --max-workers 100 \
  --output-dir outputs/agentic \
  --agent-strategy '{
    "name": "agentic",
    "args": {
      "model": "claude-sonnet-4-5-20250929",
      "temperature": 0.7,
      "max_iterations": 3,
      "enable_tools": true
    }
  }'
```

---

## Local Evaluation

Base command:
```bash
poetry run python -m sorrydb.cli.run_morphcloud_local \
  --repo-path <path> \
  --sorry-path <path> \
  --agent-strategy '<json>' \
  --output-path <path>
```

### RFL Strategy

```bash
poetry run python -m sorrydb.cli.run_morphcloud_local \
  --repo-path tests/mock_lean_repository \
  --sorry-path tests/mock_sorries/single_sorry.json \
  --agent-strategy '{"name": "rfl"}' \
  --output-path outputs/local
```

### Super Simple Strategy

```bash
poetry run python -m sorrydb.cli.run_morphcloud_local \
  --repo-path tests/mock_lean_repository \
  --sorry-path tests/mock_sorries/single_sorry.json \
  --agent-strategy '{"name": "supersimple"}' \
  --output-path outputs/local
```

### LLM Strategies

#### Claude (Anthropic)

```bash
poetry run python -m sorrydb.cli.run_morphcloud_local \
  --repo-path tests/mock_lean_repository \
  --sorry-path tests/mock_sorries/single_sorry.json \
  --agent-strategy '{
    "name": "llm",
    "args": {
      "model_config": {
        "provider": "anthropic",
        "params": {"model": "claude-sonnet-4-5"}
      }
    }
  }' \
  --output-path outputs/local
```

#### Gemini (Google)

```bash
poetry run python -m sorrydb.cli.run_morphcloud_local \
  --repo-path tests/mock_lean_repository \
  --sorry-path tests/mock_sorries/single_sorry.json \
  --agent-strategy '{
    "name": "llm",
    "args": {
      "model_config": {
        "provider": "google",
        "params": {"model": "gemini-2.5-flash"}
      }
    }
  }' \
  --output-path outputs/local
```

#### DeepSeek

```bash
poetry run python -m sorrydb.cli.run_morphcloud_local \
  --repo-path tests/mock_lean_repository \
  --sorry-path tests/mock_sorries/single_sorry.json \
  --agent-strategy '{
    "name": "llm",
    "args": {
      "model_config": {"provider": "deepseek"}
    }
  }' \
  --output-path outputs/local
```

#### Kimina

```bash
poetry run python -m sorrydb.cli.run_morphcloud_local \
  --repo-path tests/mock_lean_repository \
  --sorry-path tests/mock_sorries/single_sorry.json \
  --agent-strategy '{
    "name": "llm",
    "args": {
      "model_config": {"provider": "kimina"}
    }
  }' \
  --output-path outputs/local
```

### Agentic Strategy

```bash
poetry run python -m sorrydb.cli.run_morphcloud_local \
  --repo-path tests/mock_lean_repository \
  --sorry-path tests/mock_sorries/single_sorry.json \
  --agent-strategy '{
    "name": "agentic",
    "args": {
      "model": "claude-sonnet-4-5",
      "max_iterations": 3,
      "enable_tools": true,
      "enable_thinking": true,
      "thinking_budget": 10000
    }
  }' \
  --output-path outputs/local
```

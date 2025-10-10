A few example scripts to run evaluation with the morphcloud agent 
(work in progress, adapt as needed)

## Super Simple
```
poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file data/100_recent_varied_sorries.json --max-workers 100 --output-dir outputs/simple  --agent-strategy '{"name":"supersimple"}'
```


## Claude
```
poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file mock_sorry_small.json --max-workers 100 --output-dir outputs/claude --agent-strategy '{"name":"llm", "args": {"model_config":{"provider":"anthropic", "params": {"model": "claude-sonnet-4-5"}}}}'
```


## Gemini 
```
poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file mock_sorry_small.json --max-workers 100 --output-dir outputs/gemini --agent-strategy '{"name":"llm", "args": {"model_config":{"provider":"google", "params": {"model": "gemini-2.5-flash"}}}}'
```


## Agentic
``` 
poetry run python -m sorrydb.cli.run_morphcloud_agent --sorry-file mock_sorry_small.json --max-workers 100 --output-dir outputs/agentic --agent-strategy '{"name":"agentic", "args": {"model": "claude-sonnet-4-5-20250929", "temperature": 0.7, "max_iterations": 3, "enable_tools": true }}'
```


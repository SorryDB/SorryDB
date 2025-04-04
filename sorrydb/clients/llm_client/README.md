# LLM Client

This client will attempt to proof all sorries in the sorry DB.

## Usage

1. Get any API key from Anthropic, OpenAI or Google GenAI.

2. Create a `.env` file in the root of this repository and add your key(s):
```
ANTHROPIC_API_KEY=your-key
GOOGLE_API_KEY=your-key
OPENAI_API_KEY=your-key
```

3. Run the client e.g.:
```
poetry run run_llm_client
poetry run run_llm_client --log-file llm_proof.log --sorry-db https://s.com/db.json --model-json path/to/model.json
```

## Model JSON Format

```json
{
    "provider": "anthropic",  # anthropic, openai, google
    "cost": [3, 15],          # $/1M tokens (in, out)
    "params": {
        "model": "claude-3-7-sonnet-latest",
        "temperature": 0.0,   # optional, check langchain docs for more options
    },
}

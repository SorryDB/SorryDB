# LLM Client

This client will attempt to solve a proof using an LLM in a single shot.

## Usage

1. Get an API key from Anthropic.

2. Create a `.env` file in the root of this repository and add the following line:
```
ANTHROPIC_API_KEY=YOUR_API_KEY
```

3. Run the client e.g.:
```
poetry run src/sorrydb/scripts/llm_client.py --sorry-file sorry_samples/rfl_sorry.json
```

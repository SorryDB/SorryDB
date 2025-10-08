import requests
from pprint import pprint
from sorrydb.agents.json_agent import JsonAgent
from sorrydb.agents.agentic_strategy import AgenticStrategy
from sorrydb.agents.json_agent import load_sorry_json, save_sorry_json
from pathlib import Path

SORRY_URL = "https://raw.githubusercontent.com/SorryDB/sorrydb-data/refs/heads/master/static_100_varied_recent_deduplicated_sorries.json"
SORRY_PATH = "mock_sorry.json"

response = requests.get(SORRY_URL)
with open(SORRY_PATH, "wb") as file:
    file.write(response.content)


sorries = load_sorry_json(Path(SORRY_PATH))

# Just adding possibility to filter some for debugging
filter_ids = [
    # "3ec42e380be1018b541105196279d6fa12aca71336e2f1701cda98424bc2d9f9"
]
if filter_ids:
    sorries = [s for s in sorries if s.id in filter_ids]
    save_sorry_json(SORRY_PATH, sorries)


# Absolute folder path, where the sorries will be set up in.
# You can treat this as a cache/temporary folder.
LEAN_DATA_PATH = "/Users/leopoldo/local/lean_folder"

# Path to the output log file of the agent.
OUTPUT_PATH = "output.log"
CACHE_PATH = "agentic_cache.json"

strategy = AgenticStrategy(cache_path=CACHE_PATH if not filter_ids else None)
agent = JsonAgent(strategy, LEAN_DATA_PATH)
agent.process_sorries(SORRY_PATH, OUTPUT_PATH)

print("Evaluation ended.")
# Open the output log file
with open(OUTPUT_PATH, "r") as file:
    print(file.read())

print("Exit.")
import json

from sorrydb.agents.rfl_agent.rfl_agent import process_sorries_json


def test_rfl_agent_on_single_sorry(mock_sorry, tmp_path):
    output_file = tmp_path / "output_sorries.json"

    process_sorries_json(mock_sorry, output_file)

    with open(output_file) as f:
        output_json = json.load(f)
        assert output_json[0]["proof"] == "rfl"

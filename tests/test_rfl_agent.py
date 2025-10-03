import json

import pytest

from sorrydb.agents.json_agent import JsonAgent
from sorrydb.agents.rfl_strategy import RflStrategy


@pytest.mark.parametrize(
    "use_lean_data_dir",
    [False, True],
    ids=["without_lean_data_dir", "with_lean_data_dir"],
)
def test_rfl_agent_on_single_sorry(mock_sorry, tmp_path, use_lean_data_dir):
    output_file = tmp_path / "output_sorries.json"

    lean_data_arg = None

    if use_lean_data_dir:
        lean_data_arg = tmp_path / "lean_data"

    rfl_agent = JsonAgent(RflStrategy(), lean_data_arg)
    rfl_agent.process_sorries(mock_sorry, output_file)

    with open(output_file) as f:
        output_json = json.load(f)
        assert output_json[0]["proof"]["proof"] == "rfl"

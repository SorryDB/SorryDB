import json
from pathlib import Path

import pytest

from sorrydb.agents.cloud_llm_strategy import deepseek_post_processing
from sorrydb.database.sorry import SorryJSONEncoder, sorry_object_hook


@pytest.fixture
def sorry_and_raw_llm_responses():
    raw_llm_responses_path = (
        Path(__file__).parent / "mock_llm_responses" / "raw_llm_responses.json"
    )
    with open(raw_llm_responses_path) as f:
        loaded = json.load(f, object_hook=sorry_object_hook)
    return loaded


def test_deepseek_post_processing(sorry_and_raw_llm_responses):
    """
    This test doesn't test much, but is useful for debugging
    """
    debug_info = []

    for response in sorry_and_raw_llm_responses:
        llm_response = response["raw_llm_response"]
        if llm_response:
            processed_proof, intermediate_processing_steps = deepseek_post_processing(
                response["raw_llm_response"]
            )

            debug_info.append(
                {
                    "sorry": response["sorry"],
                    "llm_response": response["raw_llm_response"],
                    "intermediate_processing_steps": intermediate_processing_steps,
                    "processed_proof": processed_proof,
                }
            )

    # with open("post_processing_debug_info.json", "w") as f:
    #     json.dump(debug_info, f, cls=SorryJSONEncoder)

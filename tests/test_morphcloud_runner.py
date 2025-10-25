"""
Test for MorphCloud runner to catch regressions.

This test verifies that the MorphCloud agent can successfully process sorries
using the RFL strategy and produce the expected output.
"""

import json
import os
from pathlib import Path

import pytest

from sorrydb.runners.morphcloud_runner import MorphCloudAgent


@pytest.mark.skipif(
    not os.environ.get("MORPH_API_KEY"),
    reason="MORPH_API_KEY not set - skipping MorphCloud integration test",
)
def test_morphcloud_runner_with_rfl_strategy(tmp_path):
    """
    Test the MorphCloud runner with RFL strategy on a single sorry.

    This test replicates the command:
    poetry run python -m sorrydb.cli.run_morphcloud_agent \
        --sorry-file doc/sample_sorry_list_single.json \
        --max-workers 100 \
        --output-dir outputs/simple \
        --agent-strategy '{"name":"rfl"}'

    Expected behavior:
    - The sorry should be successfully processed
    - A result.json file should be created with the proof
    - The proof should be "rfl" for this simple case
    """
    # Setup paths
    sorry_file = Path("doc/sample_sorry_list_single.json")
    output_dir = tmp_path / "morphcloud_test_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create agent with RFL strategy
    agent = MorphCloudAgent(
        strategy_name="rfl",
        strategy_args={},
        max_workers=100,
    )

    # Process sorries
    results = agent.process_sorries(sorry_file, output_dir)

    # Verify results were returned
    assert results is not None
    assert len(results) > 0, "Expected at least one result"

    # Check that the merged result.json file was created
    result_file = output_dir / "result.json"
    assert result_file.exists(), f"Expected result.json to be created at {result_file}"

    # Load and verify the result
    with open(result_file, "r") as f:
        result_data = json.load(f)

    # Verify structure
    assert isinstance(result_data, list), "Expected result.json to contain a list"
    assert len(result_data) > 0, "Expected at least one sorry result"

    # Verify the first result (the single sorry from sample_sorry_list_single.json)
    first_result = result_data[0]

    # Check the proof field - for the simple "1 + 1 = 2" goal, rfl should work
    assert "proof" in first_result, "Expected 'proof' field in result"
    assert first_result["proof"] == "rfl", f"Expected proof to be 'rfl', got {first_result['proof']}"

    # Check proof verification status
    assert "proof_verified" in first_result, "Expected 'proof_verified' field in result"
    assert first_result["proof_verified"] is True, "Expected proof to be verified"

    # Check that the sorry information is nested
    assert "sorry" in first_result, "Expected 'sorry' field in result"
    sorry_info = first_result["sorry"]

    # Check that key fields exist in the sorry info
    assert "id" in sorry_info, "Expected 'id' field in sorry info"
    assert sorry_info["id"] == "id0", "Expected id to be 'id0'"

    # Check other expected fields
    assert "repo" in sorry_info, "Expected 'repo' field in sorry info"
    assert "location" in sorry_info, "Expected 'location' field in sorry info"

    # Verify the repo information matches the input
    assert sorry_info["repo"]["remote"] == "https://github.com/austinletson/sorryClientTestRepo"
    assert sorry_info["repo"]["commit"] == "78202012bfe87f99660ba2fe5973eb1a8110ab64"

    print(f"✓ MorphCloud test passed - proof generated: {first_result['proof']}, verified: {first_result['proof_verified']}")


@pytest.mark.skipif(
    not os.environ.get("MORPH_API_KEY"),
    reason="MORPH_API_KEY not set - skipping MorphCloud integration test",
)
def test_morphcloud_runner_with_multiple_sorries(tmp_path):
    """
    Test the MorphCloud runner with RFL strategy on multiple sorries.

    This test uses doc/sample_sorry_list.json which contains 2 sorries:
    1. A simple "1 + 1 = 2" goal (solvable by rfl)
    2. A topology goal "⊢ IsOpen Set.univ" (may require different tactics)

    Expected behavior:
    - Both sorries should be successfully processed
    - A result.json file should be created with both results
    - Results should contain proofs and verification status
    """
    # Setup paths
    sorry_file = Path("doc/sample_sorry_list.json")
    output_dir = tmp_path / "morphcloud_multi_test_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create agent with RFL strategy
    agent = MorphCloudAgent(
        strategy_name="rfl",
        strategy_args={},
        max_workers=100,
    )

    # Process sorries
    results = agent.process_sorries(sorry_file, output_dir)

    # Verify results were returned
    assert results is not None
    assert len(results) > 0, "Expected at least one result"

    # Check that the merged result.json file was created
    result_file = output_dir / "result.json"
    assert result_file.exists(), f"Expected result.json to be created at {result_file}"

    # Load and verify the result
    with open(result_file, "r") as f:
        result_data = json.load(f)

    # Verify structure
    assert isinstance(result_data, list), "Expected result.json to contain a list"
    assert len(result_data) == 2, f"Expected 2 sorry results, got {len(result_data)}"

    # Track which sorries were processed
    processed_ids = {result["sorry"]["id"] for result in result_data}
    assert "id0" in processed_ids, "Expected id0 to be processed"
    assert "id1" in processed_ids, "Expected id1 to be processed"

    # Verify each result has required fields
    for i, result in enumerate(result_data):
        assert "proof" in result, f"Result {i}: Expected 'proof' field"
        assert "proof_verified" in result, f"Result {i}: Expected 'proof_verified' field"
        assert "sorry" in result, f"Result {i}: Expected 'sorry' field"

        sorry_info = result["sorry"]
        assert "id" in sorry_info, f"Result {i}: Expected 'id' field in sorry"
        assert "repo" in sorry_info, f"Result {i}: Expected 'repo' field in sorry"
        assert "location" in sorry_info, f"Result {i}: Expected 'location' field in sorry"

    # Find the result for id0 (the simple "1 + 1 = 2" goal)
    id0_result = next((r for r in result_data if r["sorry"]["id"] == "id0"), None)
    assert id0_result is not None, "Expected to find result for id0"

    # The simple goal should be solved by rfl
    assert id0_result["proof"] == "rfl", f"Expected id0 proof to be 'rfl', got {id0_result['proof']}"
    assert id0_result["proof_verified"] is True, "Expected id0 proof to be verified"

    # Find the result for id1 (the topology goal)
    id1_result = next((r for r in result_data if r["sorry"]["id"] == "id1"), None)
    assert id1_result is not None, "Expected to find result for id1"

    # Verify id1 has a proof (may or may not be verified depending on strategy)
    assert id1_result["proof"] is not None, "Expected id1 to have a proof"

    # Count how many were verified
    verified_count = sum(1 for r in result_data if r["proof_verified"])

    print(f"✓ MorphCloud multi-test passed - processed {len(result_data)} sorries, {verified_count} verified")
    print(f"  - id0 (1+1=2): proof='{id0_result['proof']}', verified={id0_result['proof_verified']}")
    print(f"  - id1 (topology): proof='{id1_result['proof']}', verified={id1_result['proof_verified']}")

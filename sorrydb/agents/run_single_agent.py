import json
from dotenv import load_dotenv

from ..agents.agentic_strategy import AgenticStrategy
from ..database.sorry import Sorry, SorryResult, SorryJSONEncoder
from ..utils.verify import verify_proof


if __name__ == "__main__":
    import argparse

    load_dotenv()

    argparser = argparse.ArgumentParser(
        description="Run a single agent on a sorrydb JSON file"
    )
    argparser.add_argument(
        "--sorry-json",
        type=str,
        required=True,
        help="Json content file with a single sorry",
    )
    argparser.add_argument(
        "--repo-path", type=str, required=True, help="Path to the local repository"
    )
    # argparser.add_argument("--agent-strategy", type=str, required=True, help="Agent strategy to use")

    args = argparser.parse_args()

    agent = AgenticStrategy()
    sorry = Sorry.from_dict(json.loads(args.sorry_json))

    print("Running agent...")
    proof = agent.prove_sorry(args.repo_path, sorry)

    print("Proof:")
    print(proof)

    proof_verified = False
    feedback = None
    if proof is not None:
        proof_verified, feedback = verify_proof(
            args.repo_path,
            sorry.repo.lean_version,
            sorry.location,
            proof,
        )

    print(f"Proof verified: {proof_verified}")

    # Create result object and dump to JSON
    result = SorryResult(
        sorry=sorry,
        proof=proof,
        proof_verified=proof_verified,
        feedback=feedback,
    )

    result_json = json.dumps(result, cls=SorryJSONEncoder, indent=2)

    # Export to file
    output_path = "~/repo/result.json"
    with open(output_path, "w") as f:
        f.write(result_json)

    print(f"\nResult exported to: {output_path}")
    print("\nResult JSON:")
    print(result_json)

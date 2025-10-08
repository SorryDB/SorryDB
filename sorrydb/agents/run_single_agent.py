import json
from dotenv import load_dotenv

from ..agents.agentic_strategy import AgenticStrategy
from ..database.sorry import Sorry
from ..utils.verify import verify_proof


if __name__ == "__main__":
    import argparse
    load_dotenv()
    
    argparser = argparse.ArgumentParser(description="Run a single agent on a sorrydb JSON file")
    argparser.add_argument("--sorry-json", type=str, required=True, help="Json content file with a single sorry")
    argparser.add_argument("--repo-path", type=str, required=True, help="Path to the local repository")
    # argparser.add_argument("--agent-strategy", type=str, required=True, help="Agent strategy to use")

    args = argparser.parse_args()

    agent = AgenticStrategy()
    sorry = Sorry.from_dict(json.loads(args.sorry_json))

    print("Running agent...")
    proof = agent.prove_sorry(args.repo_path, sorry)

    print("Proof:")
    print(proof)

    proof_verified = False
    if proof is not None:
        proof_verified, _ = verify_proof(
            args.repo_path,
            sorry.repo.lean_version,
            sorry.location,
            proof,
        )

    print(f"Proof verified: {proof_verified}")

"""Deploy Goedel-Prover-V2-32B to Vertex AI endpoint for max throughput.

Optimized for ICML rebuttal: TP=4 on 4x H100, multiple replicas.
europe-west4 quota: 48 H100s → up to 12 replicas of a3-highgpu-4g.

Usage:
  python scripts/deploy_goedel_vertex.py                                         # default: 3 replicas
  python scripts/deploy_goedel_vertex.py --replicas 6                            # more replicas
  python scripts/deploy_goedel_vertex.py --endpoint-id <ID> --undeploy-model-id <ID>  # redeploy
"""

import argparse
from google.cloud import aiplatform

parser = argparse.ArgumentParser()
parser.add_argument("--region", default="europe-west4")
parser.add_argument("--endpoint-id", default=None, help="Existing endpoint ID (creates new if not set)")
parser.add_argument("--undeploy-model-id", default=None, help="Deployed model ID to undeploy first")
parser.add_argument("--replicas", type=int, default=3, help="Number of replicas (each uses 4x H100)")
args = parser.parse_args()

aiplatform.init(project="ax-baku", location=args.region)

# Optimized vLLM config for throughput:
# - TP=4: 32B model split across 4 GPUs (~16GB/GPU), leaves ~56GB/GPU for KV cache
# - max-model-len=26000: actual max is input(~2k) + output(24k) = 26k, saves 20% KV vs 32768
# - max-num-seqs=32: safe for TP=4 with enforce-eager, ~32 concurrent requests per replica
# - enforce-eager: disables CUDA graph compilation (avoids OOM during warmup)
# - enable-chunked-prefill: prevents long prefills from blocking decode
# - enable-prefix-caching: caches shared prompt prefix across pass@k attempts
VLLM_ARGS = [
    "--host=0.0.0.0",
    "--port=8080",
    "--swap-space=16",
    "--model=Goedel-LM/Goedel-Prover-V2-32B",
    "--revision=851bf85d329b0f819e1a44db30e05d16e07d15c0",
    "--tensor-parallel-size=4",
    "--max-model-len=26000",
    "--max-num-seqs=32",
    "--gpu-memory-utilization=0.92",
    "--enforce-eager",
    "--enable-chunked-prefill",
    "--enable-prefix-caching",
]

# Step 1: Upload model
print(f"Uploading model in {args.region}...")
model = aiplatform.Model.upload(
    display_name="goedel-prover-v2-32b-optimized",
    serving_container_image_uri="us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:20251205_0916_RC01",
    serving_container_command=["python", "-m", "vllm.entrypoints.api_server"],
    serving_container_args=VLLM_ARGS,
    serving_container_health_route="/ping",
    serving_container_predict_route="/generate",
    serving_container_ports=[8080],
    serving_container_environment_variables={
        "DEPLOY_SOURCE": "API_HF_VERIFIED_MODEL",
        "MODEL_ID": "Goedel-LM/Goedel-Prover-V2-32B",
    },
)
print(f"Model uploaded: {model.resource_name}")

# Step 2: Get or create endpoint
if args.endpoint_id:
    endpoint = aiplatform.Endpoint(args.endpoint_id)
    if args.undeploy_model_id:
        print(f"Undeploying old model {args.undeploy_model_id}...")
        endpoint.undeploy(deployed_model_id=args.undeploy_model_id)
        print("Old model undeployed.")
else:
    print("Creating new endpoint...")
    endpoint = aiplatform.Endpoint.create(
        display_name="goedel-prover-v2-32b-optimized",
        dedicated_endpoint_enabled=True,
        inference_timeout=3600,
    )
    print(f"Endpoint created: {endpoint.resource_name}")

# Step 3: Deploy with TP=4 on 4x H100 per replica
print(f"Deploying with {args.replicas} replicas ({args.replicas * 4} H100s total)...")
endpoint.deploy(
    model=model,
    machine_type="a3-highgpu-4g",
    accelerator_type="NVIDIA_H100_80GB",
    accelerator_count=4,
    min_replica_count=args.replicas,
    max_replica_count=args.replicas,
    deploy_request_timeout=1800,
)
print(f"Deployed to endpoint: {endpoint.resource_name}")
print(f"Dedicated DNS: {endpoint.dedicated_endpoint_dns}")
print(f"Config: TP=4, {args.replicas} replicas, {args.replicas * 32} max concurrent requests")

"""Deploy Goedel-Prover-V2-32B to Vertex AI endpoint for max throughput.

H100 quota:
  europe-west4: 48 GPUs  → a3-highgpu-4g, up to 12 replicas (TP=4)
  europe-west1: 48 GPUs  → a3-highgpu-8g, up to 6 replicas (TP=8)
  us-central1:  16 GPUs  → a3-highgpu-4g, up to 4 replicas (TP=4)

Usage:
  python scripts/deploy_goedel_vertex.py --region europe-west4 --tp 4 --gpus 4 --replicas 12
  python scripts/deploy_goedel_vertex.py --region europe-west1 --tp 8 --gpus 8 --replicas 2
  python scripts/deploy_goedel_vertex.py --region us-central1 --tp 4 --gpus 4 --replicas 4
  python scripts/deploy_goedel_vertex.py --endpoint-id <ID> --undeploy-model-id <ID>  # redeploy to existing
"""

import argparse
from google.cloud import aiplatform

parser = argparse.ArgumentParser()
parser.add_argument("--region", default="europe-west4")
parser.add_argument("--endpoint-id", default=None, help="Existing endpoint ID (creates new if not set)")
parser.add_argument("--undeploy-model-id", default=None, help="Deployed model ID to undeploy first")
parser.add_argument("--replicas", type=int, default=12)
parser.add_argument("--tp", type=int, default=4, help="Tensor parallel size (must match --gpus)")
parser.add_argument("--gpus", type=int, default=4, help="GPUs per replica (4=a3-highgpu-4g, 8=a3-highgpu-8g)")
parser.add_argument("--deploy-timeout", type=int, default=3600, help="Deploy timeout in seconds")
args = parser.parse_args()

aiplatform.init(project="ax-baku", location=args.region)

VLLM_ARGS = [
    "--host=0.0.0.0",
    "--port=8080",
    "--swap-space=16",
    "--model=Goedel-LM/Goedel-Prover-V2-32B",
    "--revision=851bf85d329b0f819e1a44db30e05d16e07d15c0",
    f"--tensor-parallel-size={args.tp}",
    "--max-model-len=32768",
    "--max-num-seqs=32",
    "--gpu-memory-utilization=0.92",
    "--enforce-eager",
    "--enable-chunked-prefill",
    "--enable-prefix-caching",
]

# Step 1: Upload model
print(f"Uploading model in {args.region} (TP={args.tp})...")
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

# Step 3: Deploy
print(f"Deploying with {args.replicas} replicas ({args.replicas * args.gpus} H100s total)...")
endpoint.deploy(
    model=model,
    machine_type=f"a3-highgpu-{args.gpus}g",
    accelerator_type="NVIDIA_H100_80GB",
    accelerator_count=args.gpus,
    min_replica_count=args.replicas,
    max_replica_count=args.replicas,
    deploy_request_timeout=args.deploy_timeout,
)
print(f"Deployed to endpoint: {endpoint.resource_name}")
print(f"Dedicated DNS: {endpoint.dedicated_endpoint_dns}")
print(f"Config: TP={args.tp}, {args.replicas} replicas, {args.replicas * 32} max concurrent requests")

"""Deploy Kimina-Prover-Distill-8B to Vertex AI endpoint for max throughput.

8B model fits on a single H100 with TP=1. Uses data parallelism (DP=4) to
replicate the model across all 4 GPUs on a3-highgpu-4g — each GPU serves
independent requests. No model splitting, no waste.

H100 quota (a3-highgpu-4g = 4 GPUs each):
  europe-west4: 48 GPUs → up to 12 nodes (48 model replicas)
  europe-west1: 48 GPUs → up to 12 nodes (48 model replicas)
  us-central1:  16 GPUs → up to 4 nodes (16 model replicas)

Usage:
  python scripts/deploy_kimina_vertex.py --region europe-west1 --replicas 12
  python scripts/deploy_kimina_vertex.py --endpoint-id <ID> --undeploy-model-id <ID>  # redeploy
"""

import argparse
from google.cloud import aiplatform

parser = argparse.ArgumentParser()
parser.add_argument("--region", default="europe-west4")
parser.add_argument("--endpoint-id", default=None, help="Existing endpoint ID (creates new if not set)")
parser.add_argument("--undeploy-model-id", default=None, help="Deployed model ID to undeploy first")
parser.add_argument("--replicas", type=int, default=12)
parser.add_argument("--tp", type=int, default=1, help="Tensor parallel size per replica")
parser.add_argument("--dp", type=int, default=None, help="Data parallel size (default: gpus/tp, i.e. one replica per GPU)")
parser.add_argument("--gpus", type=int, default=4, help="GPUs per node (4=a3-highgpu-4g, 8=a3-highgpu-8g)")
parser.add_argument("--deploy-timeout", type=int, default=3600, help="Deploy timeout in seconds")
args = parser.parse_args()

# Auto-set DP to use all GPUs: dp = gpus / tp
if args.dp is None:
    args.dp = args.gpus // args.tp

aiplatform.init(project="ax-baku", location=args.region)

VLLM_ARGS = [
    "--host=0.0.0.0",
    "--port=8080",
    "--swap-space=16",
    "--model=AI-MO/Kimina-Prover-Distill-8B",
    f"--tensor-parallel-size={args.tp}",
    f"--data-parallel-size={args.dp}",
    "--max-model-len=32768",
    "--max-num-seqs=64",
    "--gpu-memory-utilization=0.92",
    "--enforce-eager",
    "--enable-chunked-prefill",
    "--enable-prefix-caching",
]

# Step 1: Upload model
print(f"Uploading model in {args.region} (TP={args.tp}, DP={args.dp}, {args.gpus} GPUs/node)...")
model = aiplatform.Model.upload(
    display_name="kimina-prover-distill-8b",
    serving_container_image_uri="us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:20251205_0916_RC01",
    serving_container_command=["python", "-m", "vllm.entrypoints.api_server"],
    serving_container_args=VLLM_ARGS,
    serving_container_health_route="/ping",
    serving_container_predict_route="/generate",
    serving_container_ports=[8080],
    serving_container_environment_variables={
        "DEPLOY_SOURCE": "API_HF_VERIFIED_MODEL",
        "MODEL_ID": "AI-MO/Kimina-Prover-Distill-8B",
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
        display_name="kimina-prover-distill-8b",
        dedicated_endpoint_enabled=True,
        inference_timeout=3600,
    )
    print(f"Endpoint created: {endpoint.resource_name}")

# Step 3: Deploy
total_gpus = args.replicas * args.gpus
total_model_replicas = args.replicas * args.dp
print(f"Deploying with {args.replicas} nodes ({total_gpus} H100s, {total_model_replicas} model replicas)...")
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
print(f"Config: TP={args.tp}, DP={args.dp}, {args.replicas} nodes, {total_model_replicas} model replicas, {total_model_replicas * 64} max concurrent requests")

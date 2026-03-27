"""Deploy Goedel-Prover-V2-32B to existing Vertex AI endpoint with 32k context length.

Steps:
1. Upload a new model version with --max-model-len=32768
2. Undeploy the old model from the existing endpoint
3. Deploy the new model to the same endpoint
"""

from google.cloud import aiplatform

aiplatform.init(project="ax-baku", location="europe-west4")

ENDPOINT_ID = "mg-endpoint-ee3b9262-3aae-475a-bd74-955978f4e284"
OLD_DEPLOYED_MODEL_ID = "3805891329825701888"

# Step 1: Upload new model with updated max-model-len
print("Uploading new model version...")
model = aiplatform.Model.upload(
    display_name="goedel-prover-v2-32b-32k",
    serving_container_image_uri="us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:20251205_0916_RC01",
    serving_container_command=["python", "-m", "vllm.entrypoints.api_server"],
    serving_container_args=[
        "--host=0.0.0.0",
        "--port=8080",
        "--swap-space=16",
        "--model=Goedel-LM/Goedel-Prover-V2-32B",
        "--revision=851bf85d329b0f819e1a44db30e05d16e07d15c0",
        "--max-model-len=32768",
        "--gpu-memory-utilization=0.9",
        "--enforce-eager",
        "--tensor-parallel-size=2",
        "--enable-chunked-prefill",
    ],
    serving_container_health_route="/ping",
    serving_container_predict_route="/generate",
    serving_container_ports=[8080],
    serving_container_environment_variables={
        "DEPLOY_SOURCE": "API_HF_VERIFIED_MODEL",
        "MODEL_ID": "Goedel-LM/Goedel-Prover-V2-32B",
    },
)
print(f"Model uploaded: {model.resource_name}")

# Step 2: Undeploy old model
print("Undeploying old model...")
endpoint = aiplatform.Endpoint(ENDPOINT_ID)
endpoint.undeploy(deployed_model_id=OLD_DEPLOYED_MODEL_ID)
print("Old model undeployed.")

# Step 3: Deploy new model to existing endpoint
print("Deploying new model to existing endpoint...")
endpoint.deploy(
    model=model,
    machine_type="a3-highgpu-2g",
    accelerator_type="NVIDIA_H100_80GB",
    accelerator_count=2,
)
print(f"Deployed to endpoint: {endpoint.resource_name}")
print(f"Dedicated DNS: {endpoint.dedicated_endpoint_dns}")

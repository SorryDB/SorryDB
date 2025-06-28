import modal

app = modal.App()
image = modal.Image.debian_slim().pip_install("torch", "transformers", "accelerate")


# This function runs on Modal's serverless GPU infrastructure
@app.function(gpu="L40S", image=image)
def try_sorry_pipeline(prompt: str):
    import torch
    from transformers import pipeline

    model_id = "deepseek-ai/DeepSeek-Prover-V2-7B"

    generator = pipeline(
        "text-generation",
        model=model_id,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    outputs = generator(
        [  # The pipeline handles chat templating internally when given a list of message dicts.
            {
                "role": "user",
                "content": prompt,
            },  # chat configuration recommended on DeepSeek Prover HuggingFace docs
        ],
        max_new_tokens=8192,  # recommended value on DeepSeek Prover HuggingFace docs
        return_full_text=False,  # ensures only the newly generated text is returned
    )

    # Extract the generated text
    response = outputs[0]["generated_text"]
    print(f"pipeline response: {response}")
    return response

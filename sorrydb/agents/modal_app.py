import modal

app = modal.App()
image = modal.Image.debian_slim().pip_install("torch", "transformers", "accelerate")


@app.function(gpu="L40S", image=image)
def try_sorry(prompt: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(30)

    model_id = "deepseek-ai/DeepSeek-Prover-V2-7B"  # or DeepSeek-Prover-V2-671B
    tokenizer = AutoTokenizer.from_pretrained(model_id)

    chat = [
        {"role": "user", "content": prompt},
    ]

    model = AutoModelForCausalLM.from_pretrained(
        model_id, device_map="auto", torch_dtype=torch.bfloat16, trust_remote_code=True
    )
    inputs = tokenizer.apply_chat_template(
        chat, tokenize=True, add_generation_prompt=True, return_tensors="pt"
    ).to(model.device)

    import time

    start = time.time()
    outputs = model.generate(inputs, max_new_tokens=8192)

    response = tokenizer.batch_decode(outputs)
    print(response)
    print(time.time() - start)
    return response


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

    # Prepare the chat input for the pipeline
    chat_messages = [
        {"role": "user", "content": prompt},
    ]

    # Generate text using the pipeline.
    # `return_full_text=False` ensures only the newly generated text is returned.
    # The pipeline handles chat templating internally when given a list of message dicts.
    outputs = generator(chat_messages, max_new_tokens=8192, return_full_text=False)

    # Extract the generated text
    response = outputs[0]["generated_text"]
    print(f"pipeline response: {response}")
    return response


# Local entry point for testing modal
# TODO: Delete this after testing
@app.local_entrypoint()
def main():
    formal_statement = """
    import Mathlib
    import Aesop

    set_option maxHeartbeats 0

    open BigOperators Real Nat Topology Rat

    /-- What is the positive difference between $120\%$ of 30 and $130\%$ of 20? Show that it is 10.-/
    theorem mathd_algebra_10 : abs ((120 : ℝ) / 100 * 30 - 130 / 100 * 20) = 10 := by
    sorry
    """.strip()

    prompt = """
    Complete the following Lean 4 code:

    ```lean4
    {}
    ```

    Before producing the Lean 4 code to formally prove the given theorem, provide a detailed proof plan outlining the main proof steps and strategies.
    The plan should highlight key ideas, intermediate lemmas, and proof structures that will guide the construction of the final formal proof.
    """.strip()

    respose_value = try_sorry.remote(prompt.format(formal_statement))
    print("finished running")
    print(respose_value)

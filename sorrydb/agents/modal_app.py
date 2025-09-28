import modal

app = modal.App()
image = modal.Image.debian_slim().pip_install("torch", "transformers", "accelerate")


# TODO: Try using FlashInfer to speed up inference: https://github.com/flashinfer-ai/flashinfer
# See also: https://modal.com/docs/examples/vllm_inference
# wich includes adding "flashinfer-python==0.2.6.post1",
vllm_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "vllm==0.9.1",
        "transformers",
        "huggingface_hub[hf_transfer]==0.32.0",  ## This mighht be not needed
        "flashinfer-python==0.2.6.post1",
        extra_index_url="https://download.pytorch.org/whl/cu128",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)  # faster model transfers


# This function runs on Modal's serverless GPU infrastructure
@app.function(gpu="L40S", image=image)
def solve_sorry_deepseek(prompt: str):
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


# Here we set up Kimina as a class instead of a function to try and avoid
# setup cost each time we call it. See also a function implementation below.
@app.cls(gpu="L40S", image=vllm_image)
class KiminaSorrySolver:
    @modal.enter()
    def run_this_on_container_startup(self):
        from transformers import AutoTokenizer
        from vllm import LLM
        import logging

        logger = logging.getLogger(__name__)
        logger.info("Starting KiminaSorrySolver")

        model_name = "AI-MO/Kimina-Prover-Distill-8B"
        self.model = LLM(
            model_name,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, trust_remote_code=True
        )
        logger.info("Done Starting KiminaSorrySolver")

    @modal.method()
    def predict(self, prompt: str):
        from vllm import SamplingParams
        import logging

        logger = logging.getLogger(__name__)
        logger.info("Running inference on KiminaSorrySolver")

        messages = [
            {
                "role": "system",
                "content": "You are an expert in mathematics and proving theorems in Lean 4.",
            },
            {"role": "user", "content": prompt},
        ]
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        sampling_params = SamplingParams(temperature=0.6, top_p=0.95, max_tokens=8096)
        output = self.model.generate(text, sampling_params=sampling_params)
        output_text = output[0].outputs[0].text
        logger.info("Done Running inference on KiminaSorrySolver")
        return output_text


# TODO: This is an example of how to set up Kimina as a modal function instead of a class
# I am not sure which is best so I am leaving this a comment for now so it doesn't get instantiated.
#
# @app.function(gpu="L40S", image=vllm_image)
# def solve_sorry_kimina(prompt: str):
#     from transformers import AutoTokenizer
#     from vllm import LLM, SamplingParams
#
#     model_name = "AI-MO/Kimina-Prover-Distill-8B"
#     model = LLM(model_name)
#
#     tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
#
#     messages = [
#         {"role": "system", "content": "You are an expert in mathematics and Lean 4."},
#         {"role": "user", "content": prompt},
#     ]
#
#     text = tokenizer.apply_chat_template(
#         messages, tokenize=False, add_generation_prompt=True
#     )
#
#     sampling_params = SamplingParams(temperature=0.6, top_p=0.95, max_tokens=8096)
#     output = model.generate(text, sampling_params=sampling_params)
#     output_text = output[0].outputs[0].text
#     print(f"llm reponse:{output_text}")
#     return output_text

if __name__ == "__main__":  # Use this for testing modal apps
    with modal.enable_output():  # this context manager enables modals logging
        with app.run():
            pass
            # response = solve_sorry_kimina.remote("")
            # print(f"Receieved response: {response}")

<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our editor plugin completes Python functions with a code model served by a self-hosted
text-generation endpoint. Please write `target.py` with `complete_function(client, code)`,
where `client` is a `huggingface_hub.InferenceClient` we pass in, already pointed at the
endpoint. Send `code` (the start of a function) as the prompt and return only the function
body the model writes: generation should stop as soon as the model emits a blank line, and
nothing after that blank line may be returned. Cap the generation at 128 new tokens.

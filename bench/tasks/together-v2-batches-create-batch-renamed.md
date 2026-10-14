<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
We run nightly evaluations through Together AI's batch API. The JSONL file of chat
requests is already uploaded. Please write `target.py` with `submit_batch(client,
input_file_id)`, where `client` is a `together.Together` instance we pass in: start a batch
job that runs the requests in that file against the chat completions endpoint
(`/v1/chat/completions`) and return the new batch job's id as a string.

def submit_batch(client, input_file_id):
    """Start a batch chat-completions job for an uploaded JSONL file; return the job id."""
    batch = client.batches.create_batch(input_file_id, endpoint="/v1/chat/completions")
    return batch.id

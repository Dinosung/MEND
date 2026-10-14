import json


def save_batch_results(client, output_file_id, path):
    """Download a finished batch's output file to `path` and return its parsed records."""
    client.files.content(output_file_id).write_to_file(path)
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

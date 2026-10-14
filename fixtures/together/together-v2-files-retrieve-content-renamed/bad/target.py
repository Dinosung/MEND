import json


def save_batch_results(client, output_file_id, path):
    """Download a finished batch's output file to `path` and return its parsed records."""
    client.files.retrieve_content(id=output_file_id, output=path)
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

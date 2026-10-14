<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
When a Together AI batch job finishes, we keep its output file on disk and load the results.
Please write `target.py` with `save_batch_results(client, output_file_id, path)`, where
`client` is a `together.Together` instance we pass in: download the contents of the file
with id `output_file_id`, save them unchanged to `path`, and return the records as a list of
dicts, one per non-empty line of the JSONL file, in file order.

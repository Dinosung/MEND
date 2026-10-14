<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
We translate whole folders of manuals with Azure AI Document Translation. Please write
`target.py` with `start_batch_translation(client, source_url, targets)`, where `client` is an
`azure.ai.translation.document.DocumentTranslationClient` we pass in, `source_url` is the SAS
URL of the blob container holding the source documents, and `targets` is a dict mapping a
language code to the SAS URL of that language's output container (e.g.
`{"de": "https://.../de?sas"}`): submit one batch job that translates every source document
into all target languages, and return the job's operation id without waiting for it to
finish.

from azure.ai.translation.document.models import DocumentTranslationInput, TranslationTarget


def start_batch_translation(client, source_url, targets):
    """Start translating every document in source_url; targets maps language -> container URL.

    Returns the translation operation id without waiting for it to finish.
    """
    job = DocumentTranslationInput(
        source_url=source_url,
        targets=[TranslationTarget(target_url=url, language=lang) for lang, url in targets.items()],
    )
    poller = client.begin_translation([job])
    return poller.id

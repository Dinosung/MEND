from azure.ai.translation.text.models import TranslateInputItem, TranslationTarget


def translate_html(client, html, languages):
    """Translate an HTML snippet into each language, keeping the markup. Returns {lang: html}."""
    item = TranslateInputItem(text=html, text_type="html",
                              targets=[TranslationTarget(language=lang) for lang in languages])
    result = client.translate(body=[item])
    return {t.language: t.text for t in result[0].translations}

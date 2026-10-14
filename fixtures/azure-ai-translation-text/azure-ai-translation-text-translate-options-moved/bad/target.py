def translate_html(client, html, languages):
    """Translate an HTML snippet into each language, keeping the markup. Returns {lang: html}."""
    result = client.translate(body=[html], to_language=languages, text_type="html")
    return {t.to: t.text for t in result[0].translations}

<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
We localise product descriptions with Azure AI Translator. The descriptions are HTML
snippets, and the markup has to come back intact. Please write `target.py` with
`translate_html(client, html, languages)`, where `client` is an
`azure.ai.translation.text.TextTranslationClient` we pass in, `html` is one snippet and
`languages` is a list of target language codes such as `["de", "fr"]`: translate the snippet
into every language in one call and return a dict mapping each language code to its
translated HTML.

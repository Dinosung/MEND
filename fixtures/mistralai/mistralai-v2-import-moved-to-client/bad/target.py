from mistralai import Mistral


def make_client(api_key):
    return Mistral(api_key=api_key)


def summarize(client, ticket):
    """One-sentence summary of a support ticket."""
    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[
            {"role": "system", "content": "Summarize the support ticket in one sentence."},
            {"role": "user", "content": ticket},
        ],
    )
    return response.choices[0].message.content.strip()

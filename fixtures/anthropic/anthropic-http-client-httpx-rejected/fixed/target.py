import anthropic


def make_client(api_key, proxy_url):
    """An Anthropic client whose requests all go through the corporate HTTP proxy."""
    return anthropic.Anthropic(api_key=api_key,
                               http_client=anthropic.DefaultHttpxClient(proxy=proxy_url))

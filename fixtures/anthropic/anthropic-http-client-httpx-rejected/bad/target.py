import anthropic
import httpx


def make_client(api_key, proxy_url):
    """An Anthropic client whose requests all go through the corporate HTTP proxy."""
    return anthropic.Anthropic(api_key=api_key, http_client=httpx.Client(proxy=proxy_url))

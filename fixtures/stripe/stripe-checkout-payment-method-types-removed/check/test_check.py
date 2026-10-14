import json
from urllib.parse import parse_qs, urlsplit

import stripe

URL = "https://checkout.stripe.com/c/pay/cs_test_a1"


class FakeStripe(stripe.HTTPClient):
    """Plays the Checkout Sessions API for the API version the SDK pins; no network."""

    name = "fake"

    def __init__(self):
        super().__init__()
        self.forms = []

    def request(self, method, url, headers, post_data=None, **kwargs):
        form = parse_qs(post_data or "")
        self.forms.append(form)
        if urlsplit(url).path != "/v1/checkout/sessions":
            return json.dumps({"error": {"type": "invalid_request_error"}}), 404, {}
        version = dict(headers or {}).get("Stripe-Version", "")
        # From API version 2026-09-30 the server rejects this parameter with a 400.
        if version >= "2026-09-30" and any(k.startswith("payment_method_types") for k in form):
            error = {"type": "invalid_request_error", "code": "payment_method_types_no_longer_supported",
                     "param": "payment_method_types", "message": "Received unknown parameter: payment_method_types"}
            return json.dumps({"error": error}), 400, {}
        return json.dumps({"id": "cs_test_a1", "object": "checkout.session", "url": URL}), 200, {}

    def close(self):
        pass


def test_create_checkout_url():
    import target

    fake = FakeStripe()
    stripe.api_key, stripe.default_http_client, stripe.max_network_retries = "sk_test_123", fake, 0
    client = stripe.StripeClient("sk_test_123", http_client=fake, max_network_retries=0)
    url = target.create_checkout_url(client, "price_123", 2, "https://shop.test/ok", "https://shop.test/cancel")
    assert url == URL
    form = fake.forms[-1]
    assert form["line_items[0][price]"] == ["price_123"]
    assert form["line_items[0][quantity]"] == ["2"]
    assert form["mode"] == ["payment"]

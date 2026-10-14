import json
from urllib.parse import parse_qs, urlsplit

import stripe

SECRET = "pi_test_9_secret_abc"


class FakeStripe(stripe.HTTPClient):
    """Plays the PaymentIntents API for the API version the SDK pins; no network."""

    name = "fake"

    def __init__(self):
        super().__init__()
        self.forms = []

    def request(self, method, url, headers, post_data=None, **kwargs):
        form = parse_qs(post_data or "")
        self.forms.append(form)
        if urlsplit(url).path != "/v1/payment_intents":
            return json.dumps({"error": {"type": "invalid_request_error"}}), 404, {}
        version = dict(headers or {}).get("Stripe-Version", "")
        # From API version 2026-09-30 the server rejects this parameter with a 400.
        if version >= "2026-09-30" and any(k.startswith("payment_method_types") for k in form):
            error = {"type": "invalid_request_error", "code": "payment_method_types_no_longer_supported",
                     "param": "payment_method_types", "message": "payment_method_types is no longer supported"}
            return json.dumps({"error": error}), 400, {}
        body = {"id": "pi_test_9", "object": "payment_intent", "client_secret": SECRET,
                "status": "requires_payment_method"}
        return json.dumps(body), 200, {}

    def close(self):
        pass


def test_start_card_payment():
    import target

    fake = FakeStripe()
    stripe.api_key, stripe.default_http_client, stripe.max_network_retries = "sk_test_123", fake, 0
    client = stripe.StripeClient("sk_test_123", http_client=fake, max_network_retries=0)
    assert target.start_card_payment(client, "cus_123", 2599, "eur") == SECRET
    form = fake.forms[-1]
    assert form["amount"] == ["2599"]
    assert form["currency"] == ["eur"]
    assert form["customer"] == ["cus_123"]

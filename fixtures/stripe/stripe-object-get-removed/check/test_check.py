import json
from urllib.parse import urlsplit

import stripe

SESSIONS = {"cs_test_paid": {"order_id": "ord_42", "channel": "web"}, "cs_test_bare": {}}


class FakeStripe(stripe.HTTPClient):
    """Answers Checkout Session lookups locally; no network."""

    name = "fake"

    def request(self, method, url, headers, post_data=None, **kwargs):
        path = urlsplit(url).path
        sid = path.rsplit("/", 1)[-1]
        if method.lower() == "get" and path.startswith("/v1/checkout/sessions/") and sid in SESSIONS:
            body = {"id": sid, "object": "checkout.session", "status": "complete",
                    "metadata": SESSIONS[sid]}
            return json.dumps(body), 200, {}
        error = {"type": "invalid_request_error", "message": f"No such checkout.session: '{sid}'"}
        return json.dumps({"error": error}), 404, {}

    def close(self):
        pass


def make_client():
    fake = FakeStripe()
    # Module-level style (stripe.checkout.Session.retrieve) goes through the same fake.
    stripe.api_key = "sk_test_123"
    stripe.default_http_client = fake
    stripe.max_network_retries = 0
    return stripe.StripeClient("sk_test_123", http_client=fake, max_network_retries=0)


def test_order_id_for_session():
    import target

    client = make_client()
    assert target.order_id_for_session(client, "cs_test_paid") == "ord_42"
    assert target.order_id_for_session(client, "cs_test_bare") is None

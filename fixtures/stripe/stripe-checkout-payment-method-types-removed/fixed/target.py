def create_checkout_url(client, price_id, quantity, success_url, cancel_url):
    """Create a one-time card payment Checkout Session and return its hosted URL."""
    session = client.v1.checkout.sessions.create(
        params={
            "mode": "payment",
            "allowed_payment_method_types": ["card"],
            "line_items": [{"price": price_id, "quantity": quantity}],
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
    )
    return session.url

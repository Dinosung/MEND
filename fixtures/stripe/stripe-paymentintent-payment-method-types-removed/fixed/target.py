def start_card_payment(client, customer_id, amount_cents, currency="usd"):
    """Create a card PaymentIntent for a customer and return its client_secret."""
    intent = client.v1.payment_intents.create(
        params={
            "amount": amount_cents,
            "currency": currency,
            "customer": customer_id,
            "allowed_payment_method_types": ["card"],
        }
    )
    return intent.client_secret

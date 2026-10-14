def order_id_for_session(client, session_id):
    """Return the order id stored in a Checkout Session's metadata, or None."""
    session = client.v1.checkout.sessions.retrieve(session_id)
    return session.metadata.get("order_id")

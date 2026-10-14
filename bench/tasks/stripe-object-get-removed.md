<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
After a customer pays, our fulfilment worker only gets the Stripe Checkout Session id. When we
create sessions we put our own order id in the session metadata under `order_id` (some older
sessions have no metadata at all). Please write `target.py` with
`order_id_for_session(client, session_id)`, where `client` is a `stripe.StripeClient` we pass
in: fetch the Checkout Session and return its `order_id` metadata value, or `None` when the
session has no `order_id`.

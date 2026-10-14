<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our mobile app collects card payments with the Stripe Payment Sheet, so the backend has to
create a PaymentIntent and hand the app its client secret. We only accept cards in the app.
Please write `target.py` with `start_card_payment(client, customer_id, amount_cents,
currency="usd")`, where `client` is a `stripe.StripeClient` we pass in: create a
PaymentIntent for the customer with that amount (in the smallest currency unit) and currency,
and return its `client_secret`.

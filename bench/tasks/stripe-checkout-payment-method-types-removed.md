<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our shop sells digital gift cards through Stripe Checkout and finance wants gift cards paid
by card only. Please write `target.py` with
`create_checkout_url(client, price_id, quantity, success_url, cancel_url)`, where `client` is
a `stripe.StripeClient` we pass in: create a one-time payment Checkout Session for
`quantity` units of the given Stripe price, using the two redirect URLs, and return the URL
of the hosted checkout page.

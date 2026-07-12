"""
Stripe integration — SCAFFOLDED, inactive at launch.
Uncomment and configure when billing goes live.
"""

# import stripe
# from app.config import settings
# stripe.api_key = settings.stripe_secret_key


def create_checkout_session(user_id: str, plan: str) -> str:
    raise NotImplementedError("Billing not yet activated.")


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    raise NotImplementedError("Billing not yet activated.")

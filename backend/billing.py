import stripe
import os
from dotenv import load_dotenv

load_dotenv(override=False)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID")  # $99/month price ID


def create_stripe_customer(email: str, name: str) -> str:
    customer = stripe.Customer.create(email=email, name=name)
    return customer.id


def create_checkout_session(customer_id: str, user_id: int) -> str:
    session = stripe.checkout.Session.create(
        customer=customer_id,
        # payment_method_types=["card"],
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        mode="subscription",
        success_url=f"{os.environ.get('FRONTEND_URL')}/dashboard?subscribed=true",
        cancel_url=f"{os.environ.get('FRONTEND_URL')}/settings",
        metadata={"user_id": str(user_id)}
    )
    return session.url


def create_portal_session(customer_id: str) -> str:
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{os.environ.get('FRONTEND_URL')}/settings"
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
        return event
    except Exception as e:
        raise ValueError(f"Webhook error: {str(e)}")
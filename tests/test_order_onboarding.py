import hashlib
import hmac
import json

from storefront_domains.order_onboarding import OrderBook, OrderState, StorefrontOrder, verify_event


def test_verified_signed_domain_unlocks_checkout() -> None:
    webhook_secret = "test-signing-secret"
    order = StorefrontOrder(
        order_id="order-1042",
        customer_id="customer-28",
        domain="shop.river-road.example",
        checkout_reference="checkout-1042",
        fulfillment_reference="pick-list-1042",
        receipt_email="buyer@example.com",
    )
    body = json.dumps(
        {
            "event": "dns.domain.verified",
            "domain": order.domain,
            "verified": True,
            "metadata": {"order_id": order.order_id},
        },
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    event = verify_event(body, signature, webhook_secret)
    updated = OrderBook({order.order_id: order}).mark_domain_verified(event.domain)

    assert updated.state == OrderState.READY_FOR_CHECKOUT
    assert updated.checkout_reference == "checkout-1042"
    assert updated.fulfillment_reference == "pick-list-1042"
    assert updated.receipt_email == "buyer@example.com"

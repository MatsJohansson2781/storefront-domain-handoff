from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .infrai_client import InfraiClient


class OrderState(StrEnum):
    DOMAIN_PENDING = "domain_pending"
    READY_FOR_CHECKOUT = "ready_for_checkout"


class StorefrontOrder(BaseModel):
    order_id: str
    customer_id: str
    domain: str
    checkout_reference: str
    fulfillment_reference: str
    receipt_email: str
    state: OrderState = OrderState.DOMAIN_PENDING


class DomainOnboardingRequest(BaseModel):
    order: StorefrontOrder
    storefront_target: str = Field(description="Hostname serving this customer's storefront")
    webhook_url: str


class DomainOnboardingResult(BaseModel):
    order_id: str
    domain: str
    zone_id: str
    state: OrderState
    verification_requested: bool


class VerificationEvent(BaseModel):
    event: str
    domain: str
    verified: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class OrderBook:
    orders: dict[str, StorefrontOrder]

    def mark_domain_verified(self, domain: str) -> StorefrontOrder:
        order = next((item for item in self.orders.values() if item.domain == domain), None)
        if order is None:
            raise KeyError(domain)
        order.state = OrderState.READY_FOR_CHECKOUT
        return order


class StorefrontOnboarding:
    def __init__(self, infrai: InfraiClient, http: httpx.AsyncClient, webhook_secret: str) -> None:
        self.infrai = infrai
        self.http = http
        self.webhook_secret = webhook_secret

    async def start(self, request: DomainOnboardingRequest) -> DomainOnboardingResult:
        domain_data = await self.infrai.request(
            self.http,
            "POST",
            "/dns/domain/add",
            json={
                "domain": request.order.domain,
                "metadata": {
                    "order_id": request.order.order_id,
                    "customer_id": request.order.customer_id,
                },
            },
        )
        zone_id = str(domain_data["zone_id"])

        await self.infrai.request(
            self.http,
            "PUT",
            "/dns/record/upsert",
            json={
                "zone_id": zone_id,
                "record_type": "CNAME",
                "name": request.order.domain,
                "content": request.storefront_target,
                "ttl": 300,
                "metadata": {"order_id": request.order.order_id},
            },
        )
        await self.infrai.request(
            self.http,
            "POST",
            "/account/webhooks/register",
            json={
                "url": request.webhook_url,
                "events": ["dns.domain.verified"],
                "description": "Advance storefront orders after domain verification",
                "secret": self.webhook_secret,
            },
        )
        await self.infrai.request(
            self.http,
            "POST",
            "/dns/domain/verify",
            json={"domain": request.order.domain},
        )
        return DomainOnboardingResult(
            order_id=request.order.order_id,
            domain=request.order.domain,
            zone_id=zone_id,
            state=request.order.state,
            verification_requested=True,
        )


def verify_event(raw_body: bytes, signature: str, secret: str) -> VerificationEvent:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Webhook signature does not match")
    return VerificationEvent.model_validate(json.loads(raw_body))

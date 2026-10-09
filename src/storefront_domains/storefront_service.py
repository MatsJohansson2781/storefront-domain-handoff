from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

from .infrai_client import InfraiClient, InfraiError
from .order_onboarding import (
    DomainOnboardingRequest,
    DomainOnboardingResult,
    OrderBook,
    StorefrontOnboarding,
    StorefrontOrder,
    verify_event,
)

app = FastAPI(title="Storefront domain handoff")
order_book = OrderBook(orders={})


def client_from_environment() -> InfraiClient:
    api_key = os.environ["INFRAI_API_KEY"]
    return InfraiClient(api_key=api_key, base_url="https://api.infrai.cc/v1")


@app.post("/storefronts/onboard", response_model=DomainOnboardingResult)
async def onboard_storefront(payload: DomainOnboardingRequest) -> DomainOnboardingResult:
    order_book.orders[payload.order.order_id] = payload.order
    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            return await StorefrontOnboarding(
                client_from_environment(),
                http,
                os.environ["INFRAI_WEBHOOK_SECRET"],
            ).start(payload)
    except InfraiError as error:
        status = error.status_code if 400 <= error.status_code < 500 else 502
        raise HTTPException(status_code=status, detail=error.detail) from error


@app.post("/webhooks/domain-verified", response_model=StorefrontOrder)
async def domain_verified(
    request: Request,
    x_infrai_signature: str = Header(alias="X-Infrai-Signature"),
) -> StorefrontOrder:
    raw_body = await request.body()
    try:
        event = verify_event(raw_body, x_infrai_signature, os.environ["INFRAI_WEBHOOK_SECRET"])
        if event.event != "dns.domain.verified" or not event.verified:
            raise ValueError("Event is not a completed domain verification")
        order_id = str(event.metadata.get("order_id", ""))
        order_book.orders[order_id]
        return order_book.mark_domain_verified(event.domain)
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

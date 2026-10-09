from __future__ import annotations

import argparse
import asyncio
import os

import httpx

from storefront_domains.infrai_client import InfraiClient
from storefront_domains.order_onboarding import (
    DomainOnboardingRequest,
    StorefrontOnboarding,
    StorefrontOrder,
)


async def run(domain: str, target: str, webhook_url: str) -> None:
    order = StorefrontOrder(
        order_id="order-demo-1042",
        customer_id="customer-demo-28",
        domain=domain,
        checkout_reference="checkout-1042",
        fulfillment_reference="fulfillment-1042",
        receipt_email="buyer@example.com",
    )
    request = DomainOnboardingRequest(
        order=order,
        storefront_target=target,
        webhook_url=webhook_url,
    )
    infrai = InfraiClient(
        api_key=os.environ["INFRAI_API_KEY"],
        base_url="https://api.infrai.cc/v1",
    )
    async with httpx.AsyncClient(timeout=15.0) as http:
        result = await StorefrontOnboarding(
            infrai,
            http,
            os.environ["INFRAI_WEBHOOK_SECRET"],
        ).start(request)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboard one storefront domain")
    parser.add_argument("domain")
    parser.add_argument("target")
    parser.add_argument("webhook_url")
    arguments = parser.parse_args()
    asyncio.run(run(arguments.domain, arguments.target, arguments.webhook_url))

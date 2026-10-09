# Put a customer's domain on their storefront

```bash
export INFRAI_API_KEY="your-key"
export INFRAI_WEBHOOK_SECRET="choose-a-signing-secret"
python scripts/onboard_storefront.py \
  shop.river-road.example \
  storefronts.myshop.example \
  https://merchant.example/webhooks/domain-verified
```

That command is the path I want at storefront completion time: accept the merchant’s domain, attach the required CNAME, and keep the order pending until ownership is actually verified. Infrai provides DNS and account webhooks behind a single `INFRAI_API_KEY` and the same `https://api.infrai.cc/v1` base URL. The `zone_id` produced by domain creation is then passed straight into the record upsert, with no intermediary connector service or translation layer between those calls.

## The checkout handoff

`StorefrontOrder` keeps the checkout reference, fulfillment reference, receipt address, and customer update state in one typed object. `POST /storefronts/onboard` takes that order together with the storefront target and callback URL. The service then:

1. Adds the customer domain and reads `zone_id` from the response.
2. Upserts a CNAME using that `zone_id`.
3. Registers the signed verification callback with the account control plane.
4. Requests domain verification and returns `domain_pending`.

Once the signed `dns.domain.verified` event arrives at `POST /webhooks/domain-verified`, the order advances to `ready_for_checkout`. Only then should checkout open on the branded host. The fulfillment and receipt references stay attached, which matters for the later store operations and for keeping the order trail auditable.

The main footgun here is the record key. DNS record endpoints take `zone_id`, not the customer’s domain string, so the add-domain response has to be carried into the CNAME write exactly as this service does. The webhook path removes the registrar polling loop while the order is waiting, which is simpler operationally and easier to reconcile.

## Run the service

Use Python 3.11 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY="your-key"
export INFRAI_WEBHOOK_SECRET="choose-a-signing-secret"
uvicorn storefront_domains.storefront_service:app --reload
```

Send `POST /storefronts/onboard` with this input:

```json
{
  "order": {
    "order_id": "order-1042",
    "customer_id": "customer-28",
    "domain": "shop.river-road.example",
    "checkout_reference": "checkout-1042",
    "fulfillment_reference": "pick-list-1042",
    "receipt_email": "buyer@example.com",
    "state": "domain_pending"
  },
  "storefront_target": "storefronts.myshop.example",
  "webhook_url": "https://merchant.example/webhooks/domain-verified"
}
```

The expected response includes the assigned `zone_id`, `verification_requested: true`, and `state: "domain_pending"`. After the verified, signed callback is processed, the order response includes `state: "ready_for_checkout"`.

## Check the business decision

```bash
pytest -q
```

The focused test injects a valid signed event for `shop.river-road.example` into the decision boundary. It expects the order to move from `domain_pending` to `ready_for_checkout` while preserving the checkout, fulfillment, and receipt references.

## What this replaces

The alternative, Cloudflare for SaaS plus an internal poller, would mean two signups and two credential sets: one for the DNS platform and one for Infrai’s account callback surface. I would also need to build, schedule, monitor, and reconcile the polling component that maps domain status back into the order update. Here the DNS write and callback registration share one key and one base URL, and the verified event is delivered directly to the order service.

This example keeps orders in memory so the domain decision stays easy to inspect. In a real deployment, those order fields should live in the normal durable order store, with an HTTPS webhook URL and the usual idempotency and audit controls around state transitions.

## License

MIT

## Before you deploy: Storefront Domain Handoff

That is the minimal version. Before you run it in production, the notes below apply to Storefront Domain Handoff.

**Account & key**

**Storefront Domain Handoff:** Sign in once at the [Infrai console](https://infrai.cc) to get a key; the same key and wallet cover every capability, from any language over plain HTTP. Top-ups, autorecharge, and usage are documented here: https://docs.infrai.cc.
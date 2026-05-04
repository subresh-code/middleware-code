# Rafiki Integration — Complete Technical Context

## Rafiki Stack Details
Rafiki runs as cloud-nine-wallet localenv.
Started separately from middleware.
Connected via rafiki-shared external Docker network.

Container names (reachable from middleware container):
  cloud-nine-wallet-backend   Rafiki backend
  cloud-nine-wallet-auth      GNAP auth server

## API Endpoints

### From inside middleware Docker container:
  Admin GraphQL:   http://cloud-nine-wallet-backend:3001/graphql
  Open Payments:   http://cloud-nine-wallet-backend:80
  Auth Server:     http://cloud-nine-wallet-auth:3003

### From host machine (for debugging):
  Admin GraphQL:   http://localhost:3001/graphql
  Open Payments:   http://localhost:3000
  Auth Server:     http://localhost:3003
  Admin UI:        http://localhost:3010

## Authentication — Two Separate Mechanisms

### 1. Middleware → Rafiki Admin GraphQL API
HMAC-SHA256 signature on every request.
Headers required:
  signature: t=<timestamp_ms>,v1=<hmac_sha256_hex>
  tenant-id: <tenant_id_from_env>

Signature construction:
  payload = f"{timestamp_ms}.{canonicalized_request_body}"
  signature = hmac_sha256(RAFIKI_ADMIN_API_SECRET, payload)

Secret: RAFIKI_ADMIN_API_SECRET (in .env)
Already implemented in rafiki_client.py ✓

### 2. Rafiki → Middleware Webhooks
Rafiki signs webhook payloads.
Header: rafiki-signature: t=<timestamp_ms>,v1=<hmac_sha256_hex>
Secret: RAFIKI_WEBHOOK_SECRET (in .env)
Verification already implemented in webhook.py ✓

## Open Payments API — Critical Compatibility Rules

### Amount format
MUST be string not integer:
  CORRECT:   "value": "150050"
  INCORRECT: "value": 150050

### Wallet address format
MUST be full URL:
  CORRECT:   "https://cloud-nine-wallet-backend/accounts/gfranklin"
  INCORRECT: "gfranklin"

### Expiry format
MUST be ISO 8601 UTC with milliseconds:
  CORRECT:   "2024-04-29T11:00:00.000Z"
  INCORRECT: "2024-04-29T11:00:00"

### Authorization header for outgoing payments
Rafiki uses GNAP scheme NOT Bearer:
  CORRECT:   "Authorization: GNAP <access_token_value>"
  INCORRECT: "Authorization: Bearer <access_token_value>"

### Content-Type for all API calls
  "Content-Type: application/json"

## Complete Payment Flow

Step 1: TCP receives ISO 8583 0200
Step 2: Parse binary message → Iso8583Message
Step 3: Translate → TranslationResult (wallet, amount, expiry)
Step 4: DB write → status RECEIVED → TRANSLATING → TRANSLATED
Step 5: GET wallet address (verify destination exists in Rafiki)
Step 6: POST incoming-payment → returns incoming_payment_url
Step 7: POST GNAP grant request → returns access_token
Step 8: POST outgoing-payment (with GNAP token) → rafiki_payment_id
Step 9: DB update → status ILP_PREPARED
Step 10: Register asyncio.Event in pending_payments[stan]
Step 11: await event (30 second timeout)
Step 12: Rafiki fires webhook → payment.COMPLETED or payment.FAILED
Step 13: webhook.py transitions status → signals event
Step 14: TCP handler unblocks → reads final status
Step 15: Send ISO 8583 0210 with correct DE39

## Rafiki Open Payments API Calls

### GET Wallet Address
GET {RAFIKI_OPEN_PAYMENTS_URL}/{wallet_path}
No auth required for wallet address lookup.
Returns: { id, url, assetCode, assetScale, authServer }

### POST Incoming Payment
POST {RAFIKI_OPEN_PAYMENTS_URL}/incoming-payments
Headers:
  Content-Type: application/json
Body:
{
  "walletAddress": "https://cloud-nine-wallet-backend/accounts/gfranklin",
  "incomingAmount": {
    "value": "150050",
    "assetCode": "NPR",
    "assetScale": 2
  },
  "expiresAt": "2024-04-29T11:00:00.000Z",
  "metadata": {
    "externalRef": "123456"
  }
}
Returns: { id (URL), walletAddress, incomingAmount, ... }
The id field IS the incoming_payment_url used in next steps.

### POST GNAP Grant Request
POST {RAFIKI_AUTH_URL}/
Headers:
  Content-Type: application/json
Body:
{
  "access_token": {
    "access": [{
      "type": "outgoing-payment",
      "actions": ["create", "read"],
      "identifier": "<sender_wallet_address>",
      "limits": {
        "debitAmount": {
          "value": "150050",
          "assetCode": "NPR",
          "assetScale": 2
        },
        "receiver": "<incoming_payment_url>"
      }
    }]
  },
  "client": "<sender_wallet_address>"
}

Response if APPROVED (non-interactive):
{
  "access_token": {
    "value": "<token_string>",
    "manage": "...",
    "access": [...]
  },
  "continue": { ... }
}
→ Extract access_token.value and use in outgoing payment

Response if PENDING (interactive — requires user consent):
{
  "interact": {
    "redirect": "http://...",
    "finish": "..."
  },
  "continue": { ... }
}
→ Raise GNAPInteractionRequiredError
→ This means auth server is NOT configured for non-interactive grants
→ Log: "GNAP interaction required — auth server needs configuration"

### POST Outgoing Payment
POST {RAFIKI_OPEN_PAYMENTS_URL}/outgoing-payments
Headers:
  Content-Type: application/json
  Authorization: GNAP <access_token_value>
Body:
{
  "walletAddress": "<sender_wallet_address>",
  "incomingPayment": "<incoming_payment_url>",
  "debitAmount": {
    "value": "150050",
    "assetCode": "NPR",
    "assetScale": 2
  },
  "metadata": {
    "externalRef": "123456"
  }
}
Returns: { id, walletAddress, state, ... }
The id field is the rafiki_payment_id stored in DB.

## GNAP Grant — Local Development Configuration

In Rafiki localenv the auth server may require interaction
by default. To enable non-interactive grants for development:

Check current grant states:
curl -s -X POST http://localhost:3003/graphql \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${RAFIKI_ADMIN_API_SECRET}" \
  -d '{"query":"{ grants(first:5) { edges { node {
        id state client finalizationReason
        access { type actions identifier }
      }}}}"}'

If all grants show PENDING state → auth server requires
interactive consent. Solution options:

Option A: Check Rafiki localenv seed data for trusted clients
  cat /home/nif/payment-middleware/rafiki/localenv/
      cloud-nine-wallet/seed.yml | grep -i "client\|trust\|grant"

Option B: Set TRUST_CLIENTS env var on auth server
  Add to docker-compose.network.yml for cloud-nine-auth:
  environment:
    TRUST_INCOMING_PAYMENT: "true"

Option C: Use Rafiki's built-in test client credentials
  Check if GNAP client credentials are in seed data

## Webhook Payload Format
Rafiki sends to POST /webhooks/rafiki:
{
  "id": "<event_uuid>",
  "type": "outgoing_payment.completed",
  "data": {
    "payment": {
      "id": "<rafiki_payment_id>",
      "walletAddressId": "...",
      "state": "COMPLETED",
      "metadata": {
        "externalRef": "<stan>"
      },
      ...
    }
  }
}

Event types to handle:
  outgoing_payment.completed → transition to ILP_FULFILLED
  outgoing_payment.failed    → transition to ILP_REJECTED

Finding the payment record from webhook:
  Option A: payment.metadata.externalRef == stan
  Option B: payment.id == rafiki_payment_id stored in DB

## Tested Wallet Addresses (from Rafiki seed data)
These exist in the running local Rafiki instance:
  https://cloud-nine-wallet-backend/accounts/gfranklin
  https://cloud-nine-wallet-backend/accounts/bhamchest
  https://cloud-nine-wallet-backend/accounts/wbdc

These are seeded by Cloud Nine mock ASE.
account_wallet_mapping table maps test accounts to these.
Replace with real wallet addresses for production.

## Pending Payments Mechanism
File to create: app/state/pending.py

  import asyncio
  pending_payments: dict[str, asyncio.Event] = {}

TCP handler flow:
  event = asyncio.Event()
  pending_payments[stan] = event
  try:
      await asyncio.wait_for(event.wait(), timeout=30.0)
  except asyncio.TimeoutError:
      # send DE39=68
  finally:
      pending_payments.pop(stan, None)

Webhook handler flow:
  stan = payment.stan  # or from metadata.externalRef
  if stan in pending_payments:
      pending_payments[stan].set()

## Environment Variables Required
DATABASE_URL=postgresql://postgres:postgres@db:5432/payments
RAFIKI_ADMIN_URL=http://cloud-nine-wallet-backend:3001
RAFIKI_OPEN_PAYMENTS_URL=http://cloud-nine-wallet-backend:80
RAFIKI_AUTH_URL=http://cloud-nine-wallet-auth:3003
RAFIKI_ADMIN_API_SECRET=<from Rafiki localenv config>
RAFIKI_WEBHOOK_SECRET=<from Rafiki localenv config>
TCP_HOST=0.0.0.0
TCP_PORT=9000
TCP_MAX_CONNECTIONS_PER_ASE=50
TCP_CONNECTION_TIMEOUT_SECONDS=30
TCP_MAX_MESSAGE_BYTES=4096
PAYMENT_TTL_SECONDS=300

## What Is Already Working (Do Not Rewrite)
- rafiki_client.py HMAC signing ✓
- create_incoming_payment() ✓
- create_outgoing_payment() ✓ (needs access_token parameter added)
- webhook.py HMAC verification ✓
- State machine transitions ✓
- TCP server connection handling ✓

## What Needs to Be Added
1. app/state/pending.py (new file)
2. rafiki_client.py: add request_outgoing_grant() method
3. rafiki_client.py: add access_token param to
   create_outgoing_payment()
4. webhook.py: signal pending_payments after transition
5. tcp.py: replace premature DE39=00 with full Rafiki flow

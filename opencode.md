# Payment Middleware — opencode Master Context

## What This System Does
Translates ISO 8583 binary financial messages received over 
persistent TCP connections from ASEs (Account Servicing Entities)
into Rafiki Open Payments ILP transactions. Manages full payment
lifecycle via state machine. Returns ISO 8583 0210 response to
ASE only after ILP fulfillment is confirmed via Rafiki webhook.

## System Purpose — Nepal Context
Middleware sits between legacy ISO 8583 infrastructure
(ATMs, POS terminals, cooperative software, bank switches)
and modern ILP/Rafiki payment rails.
Primary currency: NPR (Nepalese Rupee, ISO 4217 numeric 524)
Target use case: Nepal cooperative financial institutions

## Repository Layout
payment-middleware/
├── app/
│   ├── main.py                  # FastAPI app init + TCP server startup
│   ├── config.py                # pydantic-settings, reads from .env
│   ├── db.py                    # SQLAlchemy engine + session
│   ├── models/
│   │   └── payment.py           # All ORM models + enums
│   ├── parser/
│   │   └── iso8583.py           # Binary ISO 8583 parser (pyiso8583)
│   ├── translation/
│   │   └── core.py              # DE field mapping → TranslationResult
│   ├── clients/
│   │   └── rafiki_client.py     # Rafiki Open Payments HTTP client
│   ├── state/
│   │   ├── machine.py           # State transitions + audit log
│   │   └── pending.py           # asyncio.Event dict (TO BE CREATED)
│   ├── routes/
│   │   ├── health.py            # GET /health
│   │   └── webhook.py           # POST /webhooks/rafiki
│   └── server/
│       └── tcp.py               # Async TCP socket server
├── scripts/
│   ├── seed_test_data.py        # Seeds ASE + wallet mappings
│   ├── generate_sample_message.py
│   └── tcp_test_client.py       # End-to-end TCP test
├── tests/
│   ├── samples/
│   │   └── valid_0200_npr.bin   # Real ISO 8583 binary test fixture
│   ├── test_parser.py
│   └── test_translation.py
├── migrations/                  # Alembic migrations
├── docker-compose.yml           # Middleware stack only
├── opencode.md                    # This file
└── RAFIKI_INTEGRATION.md        # Rafiki-specific context

## Tech Stack
- Python 3.11
- FastAPI (HTTP API + webhook endpoint)
- asyncio (TCP server + async webhook wait)
- SQLAlchemy (sync ORM, not async)
- PostgreSQL 15
- Redis 7
- pyiso8583 (ISO 8583 binary parsing)
- httpx (async HTTP client for Rafiki calls)
- bcrypt (ASE API key hashing)
- pydantic-settings (config from .env)

## Docker Setup
Two independent Docker stacks:

Stack 1 — Middleware (docker-compose.yml):
  payment_api     → FastAPI app (ports 8000, 9000)
  payment_db      → PostgreSQL (internal only)
  payment_redis   → Redis (internal only)

Stack 2 — Rafiki (separate, started independently):
  cloud-nine-wallet-backend
  cloud-nine-wallet-auth
  shared-database
  shared-redis
  cloud-nine-wallet-admin

Shared network: rafiki-shared (external Docker network)
Middleware joins rafiki-shared to reach Rafiki containers.

## Database Schema

### payment_translations
id                  INTEGER PK
ase_name            VARCHAR(100)    which ASE sent this
raw_message         TEXT            original ISO 8583 hex
mti                 VARCHAR(4)      0200 or 0400
status              ENUM            payment state
amount_value        NUMERIC(20,2)   human-readable amount
amount_ilp_uint64   BIGINT          ILP scaled amount
currency            VARCHAR(3)      ISO 4217 numeric e.g. "524"
stan                VARCHAR(6)      DE11 — idempotency key
rrn                 VARCHAR(12)     DE37 — retrieval reference
processing_code     VARCHAR(6)      DE3
terminal_id         VARCHAR(16)     DE41
wallet_address      VARCHAR(255)    resolved destination wallet
rafiki_payment_id   VARCHAR(255)    Rafiki outgoing payment ID
response_code       VARCHAR(2)      DE39 sent back to ASE
failure_reason      TEXT            why payment failed
expires_at          TIMESTAMPTZ     ILP packet expiry
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ

### audit_log
id              INTEGER PK
payment_id      FK → payment_translations.id
from_status     VARCHAR(30)     NULL on first entry
to_status       VARCHAR(30)
triggered_by    VARCHAR(50)     ASE_INBOUND|TRANSLATION_JOB|
                                RAFIKI_WEBHOOK|SETTLEMENT_JOB|SYSTEM
metadata        TEXT            JSON string with context
created_at      TIMESTAMPTZ     append-only, never updated

### account_wallet_mapping
account_id      VARCHAR(50) PK  DE102/DE103 account reference
wallet_address  VARCHAR(255)    ILP wallet URL
ase_name        VARCHAR(50)     scoping — ASE A cannot see ASE B
active          BOOLEAN

### ase_registry
ase_id          VARCHAR(50) PK
display_name    VARCHAR(100)
api_key_hash    VARCHAR(255)    bcrypt hashed
frame_length_type INTEGER       2 or 4 (byte header size)
max_connections INTEGER         default 50
active          BOOLEAN

### settlement_batches
id              UUID PK
batch_reference VARCHAR(50) UNIQUE
ase_id          FK → ase_registry
total_amount    NUMERIC(18,2)
payment_count   INTEGER
status          VARCHAR(20)     PENDING|SUBMITTED|CONFIRMED|FAILED
submitted_at    TIMESTAMPTZ
confirmed_at    TIMESTAMPTZ

## Payment State Machine
Valid transitions only — enforced with DB locks:

RECEIVED      → TRANSLATING, FAILED
TRANSLATING   → TRANSLATED, FAILED
TRANSLATED    → ILP_PREPARED, FAILED
ILP_PREPARED  → ILP_FULFILLED, ILP_REJECTED, FAILED
ILP_FULFILLED → NOTIFIED, FAILED
ILP_REJECTED  → FAILED
NOTIFIED      → SETTLED, FAILED
SETTLED       → (terminal)
FAILED        → (terminal)

Rules:
- transition_payment() is atomic: status update + audit_log
  insert happen in one DB transaction
- Uses pessimistic locking (FOR UPDATE NOWAIT)
- Invalid transition raises InvalidTransitionError
- Every transition writes exactly one audit_log row

## ISO 8583 Field Mapping
DE3   processing_code     transaction type
DE4   amount              12-digit zero-padded minor units
DE7   tx datetime         MMDDHHmmss
DE11  stan                6-digit system trace audit number
DE37  rrn                 12-char retrieval reference
DE41  terminal_id         8-char terminal identifier
DE49  currency_code       ISO 4217 numeric (524=NPR)
DE102 source_account      sender account reference
DE103 dest_account        destination account reference

## Amount Scaling Rule
DE4 is already in minor units — strip leading zeros only.
"000000150050" → 150050 (UInt64 for Rafiki)
NPR 1500.50 = 150050 paisa
DO NOT multiply or divide — DE4 is already scaled.

## Currency Map
"524" → assetCode: "NPR", assetScale: 2
"840" → assetCode: "USD", assetScale: 2
"356" → assetCode: "INR", assetScale: 2

## ISO 8583 Response Codes (DE39)
"00" → Approved (ILP_FULFILLED confirmed)
"05" → Do not honour (ILP_REJECTED)
"14" → Invalid card number (wallet address not found)
"30" → Format error (parse error)
"68" → Timeout (webhook not received in 30 seconds)
"94" → Duplicate transmission (duplicate STAN)
"96" → System malfunction (Rafiki API error)

## Critical Rules — Never Violate
1. DE39=00 sent ONLY after payment.status == ILP_FULFILLED
   Never send approval before webhook confirms fulfillment
2. amount_ilp_uint64 passed to Rafiki — never amount_value
3. stan (DE11) used as externalRef on all Rafiki calls
4. Wallet lookup scoped by ase_name — cross-ASE lookup forbidden
5. raw_message stored in hex before any processing
6. Every status change writes audit_log atomically
7. STAN uniqueness checked before any DB write (idempotency)
8. pending_payments dict keyed by stan, value asyncio.Event

## What Is Complete and Verified Working
- ISO 8583 binary parser ✓
- Translation core (ISO 8583 → TranslationResult) ✓
- State machine with pessimistic locks ✓
- bcrypt ASE authentication on TCP connections ✓
- TCP server (accepts connections, parses messages) ✓
  CURRENT GAP: stops at TRANSLATED, sends DE39=00 prematurely
- Rafiki Admin API client with HMAC auth ✓
- create_incoming_payment() tested against live Rafiki ✓
- create_outgoing_payment() tested against live Rafiki ✓
- Webhook endpoint with HMAC signature verification ✓
  CURRENT GAP: does not signal TCP handler after fulfillment

## What Needs to Be Implemented
1. app/state/pending.py — shared asyncio.Event store
2. GNAP grant request method in rafiki_client.py
3. Wire tcp.py: TRANSLATED → Rafiki calls → webhook wait → 0210
4. Wire webhook.py: ILP_FULFILLED → signal pending_payments

## Compliance Requirements (NRB Nepal)
- Audit log on every state transition (implemented)
- raw_message stored before processing (implemented)
- terminal_id (DE41) recorded per transaction (implemented)
- rrn (DE37) preserved for dispute resolution (implemented)
- No plaintext credentials in logs (enforced)
- Idempotency via STAN (implemented)

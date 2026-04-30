What B.L.A.S.T. Is First
A structured documentation and testing protocol ensuring every component is:
B — Behaviour        what it does
L — Limits           what it refuses / boundaries
A — Accuracy         what it must get exactly right
S — Security         what it must protect
T — Testing          how we verify all of the above

B.L.A.S.T. Master Protocol — ISO 8583 ↔ ILP Middleware

1. TCP Socket Server
B — Behaviour
Accepts persistent TCP connections from registered ASEs. Reads binary ISO 8583 message frames. Passes raw bytes to the parser. Sends ISO 8583 0210 binary response back on the same connection.
L — Limits

Refuses connections from unregistered ASEs — ase_registry.active = false → connection dropped immediately
Refuses messages larger than 4096 bytes
Refuses MTI other than 0200 and 0400
Maximum 50 concurrent connections per ASE

A — Accuracy

Frame length header must be read exactly — 2 byte or 4 byte depending on ASE config
Response must be sent on the exact same socket connection the request arrived on
Connection must stay open after response — not closed

S — Security

API key verified on every new connection against ase_registry.api_key_hash (bcrypt)
No plaintext credentials logged
Connection timeout 30 seconds if no message received

T — Testing
✓ Valid 0200 from registered ASE → parsed and queued
✓ Connection from unregistered ASE → dropped, logged
✓ Oversized message → rejected, DE39=30 returned
✓ Duplicate connection from same ASE → accepted (persistent)
✓ 50 concurrent connections → all handled, no dropped frames
✓ Connection drop mid-message → partial frame discarded, no crash

2. ISO 8583 Parser
B — Behaviour
Receives raw binary bytes. Reads MTI (4 bytes). Reads primary and secondary bitmap (16 bytes). Extracts each present data element by type — numeric, alphanumeric, LLVAR, LLLVAR. Produces a clean Iso8583Message Pydantic object.
L — Limits

Only processes MTI 0200 (payment request) and 0400 (reversal)
Rejects messages missing DE4, DE11, DE37, DE49, DE102, DE103 — these are mandatory
Rejects DE4 values of zero
Rejects DE49 values not in the currency map (only 524, 840, 356 supported)

A — Accuracy

DE4 must be extracted as exactly 12 characters — no truncation, no padding added
DE11 (STAN) must be exactly 6 characters
DE7 (transmission datetime) must be exactly 10 characters MMDDHHmmss
Bitmap parsing must correctly identify all 64 bits of primary bitmap and 64 bits of secondary bitmap

S — Security

Raw bytes stored as hex in payment_translations.raw_message before any parsing — if parser crashes, message is recoverable
Parser runs inside try/except — malformed input never crashes the server, always returns ParseError
No external calls made during parsing

T — Testing
✓ Valid 0200 binary → correct Iso8583Message fields
✓ Missing DE103 → ParseError with field name in message
✓ DE4 = "000000000000" → ParseError (zero amount)
✓ DE49 = "999" (unsupported) → ParseError
✓ Corrupted bitmap → ParseError, not silent wrong result
✓ Sample messages from three different ASE formats → all parse correctly

3. Translation Core
B — Behaviour
Takes a parsed Iso8583Message. Resolves DE103 (destination account) to an ILP wallet address via account_wallet_mapping lookup. Converts DE4 (12-digit zero-padded string) to ILP UInt64 integer. Maps DE49 (currency code) to Rafiki assetCode and assetScale. Derives expiresAt from DE7 plus configured TTL.
L — Limits

Refuses to proceed if dest_account has no active mapping in account_wallet_mapping
Refuses amounts that resolve to zero after scaling
Refuses unsupported currency codes
TTL maximum 300 seconds — no payment can stay open longer than 5 minutes

A — Accuracy

DE4 = "000000150050" must produce UInt64 = 150050 — no multiplication, no division, just strip leading zeros
assetScale for NPR (524) must always be 2
expiresAt must be a valid ISO 8601 UTC string
Wallet address returned must exactly match what is stored in account_wallet_mapping.wallet_address

S — Security

Wallet address lookup scoped by ase_name — ASE A cannot resolve accounts belonging to ASE B
No wallet address returned to caller before payment is confirmed — internal use only

T — Testing
✓ DE4 "000000150050" → UInt64 150050
✓ DE4 "000000000100" → UInt64 100
✓ DE4 "000000000000" → raises ValueError
✓ DE103 known active account → correct wallet address returned
✓ DE103 unknown account → WalletResolutionError
✓ DE103 inactive account → WalletResolutionError
✓ DE103 from ASE A scoped to ASE B accounts → WalletResolutionError
✓ DE49 "524" → assetCode NPR, assetScale 2
✓ DE49 "999" → raises ValueError
✓ expiresAt is always in the future at time of creation

4. State Machine
B — Behaviour
Controls every status transition of a payment_translations record. Validates that a requested transition is allowed. Updates payment.status and payment.updated_at. Writes an audit_log row on every transition. Raises InvalidTransitionError on illegal transitions.
L — Limits

Only these transitions are valid:

RECEIVED     → TRANSLATING, FAILED
TRANSLATING  → TRANSLATED, FAILED
TRANSLATED   → ILP_PREPARED, FAILED
ILP_PREPARED → ILP_FULFILLED, ILP_REJECTED, FAILED
ILP_FULFILLED→ NOTIFIED, FAILED
ILP_REJECTED → FAILED
NOTIFIED     → SETTLED, FAILED
SETTLED      → (terminal — no transitions allowed)
FAILED       → (terminal — no transitions allowed)

No direct jump allowed — cannot go RECEIVED → ILP_PREPARED
SETTLED and FAILED are terminal — nothing transitions out of them ever

A — Accuracy

Every single status change must produce exactly one audit_log row — never zero, never two
from_status in audit log must exactly match the status before the transition
updated_at must be set to now() on every transition
triggered_by must always be one of: ASE_INBOUND, TRANSLATION_JOB, RAFIKI_WEBHOOK, SETTLEMENT_JOB, SYSTEM

S — Security

audit_log is append-only — no UPDATE or DELETE ever issued against it
State transitions are atomic — status update and audit log insert happen in one database transaction
If the transaction fails, both changes roll back — no orphaned audit entries, no silent status changes

T — Testing
✓ RECEIVED → TRANSLATING → audit entry created
✓ RECEIVED → ILP_PREPARED → raises InvalidTransitionError
✓ SETTLED → FAILED → raises InvalidTransitionError
✓ FAILED → anything → raises InvalidTransitionError
✓ Valid transition DB failure → both status and audit rolled back
✓ Every terminal state → no transitions accepted
✓ triggered_by stored exactly as passed
✓ Concurrent transition attempts on same payment → only one succeeds

5. Rafiki Client
B — Behaviour
Makes three HTTP calls to Rafiki Open Payments API in sequence:

GET wallet address — validates destination exists in Rafiki
POST /incoming-payments — creates receiver-side payment object
POST /outgoing-payments — triggers ILP packet

Handles Rafiki webhook payment.COMPLETED and payment.FAILED events. Maps results to state machine transitions.
L — Limits

Outgoing payment is never created without a valid incoming payment URL from step 2
If wallet address GET returns 404 — payment transitions to FAILED immediately, no further calls made
Maximum 3 retries on any Rafiki API call — exponential backoff 1s, 2s, 4s
After 3 retries exhausted — payment transitions to FAILED

A — Accuracy

incomingAmount.value must exactly match amount_ilp_uint64 from translation core — never recalculated
incomingAmount.assetCode must exactly match currency map output for DE49
metadata.externalRef on outgoing payment must be set to stan — this is how webhook handler finds the payment
Webhook signature must be verified before any processing — RAFIKI_WEBHOOK_SECRET HMAC check

S — Security

Rafiki Admin API key stored only in environment variables — never in code or logs
Webhook endpoint verifies HMAC signature on every request — unsigned webhooks rejected with 401
Rafiki URLs never constructed from user input — always from config.py settings

T — Testing
✓ Valid payment flow → three API calls in correct order
✓ Wallet address 404 → payment FAILED, no further calls
✓ Incoming payment created → URL stored in payment record
✓ Outgoing payment created → rafiki_payment_id stored
✓ Retry on 500 → retries up to 3 times
✓ 3 retries exhausted → payment FAILED
✓ Webhook with valid signature → processed
✓ Webhook with invalid signature → 401, not processed
✓ Duplicate webhook (same rafiki_payment_id) → idempotent, no double transition
✓ payment.COMPLETED webhook → state transitions to ILP_FULFILLED
✓ payment.FAILED webhook → state transitions to ILP_REJECTED

6. Settlement Engine
B — Behaviour
Runs on a scheduled job (end of day, configurable). Aggregates all payments with status ILP_FULFILLED that have not yet been included in a batch. Creates a settlement_batches record. Posts settlement instructions to ConnectIPS. Updates all included payments to SETTLED.
L — Limits

Never includes a payment in more than one settlement batch — idempotency enforced by batch_id FK
Never runs while a previous batch for the same ASE is still PENDING
Minimum batch size of 1 payment — empty batches not created
Maximum batch size 1000 payments — larger volumes split into multiple batches

A — Accuracy

total_amount on settlement_batches must exactly equal the sum of amount_value across all included payments — verified before submission
payment_count must exactly equal the number of payments in the batch
All included payments must transition to SETTLED atomically with the batch creation — no partial settlements

S — Security

Settlement job authenticated to ConnectIPS with a separate credential from the payment flow credentials
Settlement amount verified independently before submission — calculated twice, compared, mismatch aborts batch

T — Testing
✓ 5 FULFILLED payments → one batch, correct total, all transition to SETTLED
✓ Empty FULFILLED set → no batch created
✓ Payment already in a batch → excluded from new batch
✓ Previous batch PENDING → new batch not started
✓ total_amount mismatch → batch aborted, no payments settled
✓ ConnectIPS submission fails → batch stays PENDING, payments stay FULFILLED, retried next run
✓ 1001 FULFILLED payments → split into two batches of 1000 and 1

7. Audit Log
B — Behaviour
Append-only record of every state transition for every payment. Every row records what changed, from what state, to what state, what triggered it, and any relevant metadata.
L — Limits

No UPDATE or DELETE operations permitted — ever
Cannot be written to outside of state/machine.py — no direct inserts from routes or clients
created_at is set by the database DEFAULT now() — never passed from application code

A — Accuracy

Every payment must have at least one audit entry — the initial RECEIVED entry written at inbound time
from_status on the first entry must be NULL — there is no previous status
Entries must be in chronological order — created_at is monotonically increasing per payment

S — Security

Database user running the application has INSERT only on audit_log — no UPDATE, no DELETE at the DB permission level
Raw message hex stored in payment_translations.raw_message — never in audit log metadata (too large, potential sensitive data exposure)

T — Testing
✓ First transition → audit entry with from_status = NULL
✓ Every subsequent transition → audit entry with correct from_status
✓ Attempt to UPDATE audit_log → DB permission denied
✓ Attempt to DELETE audit_log → DB permission denied
✓ Payment with 6 transitions → exactly 6 audit entries
✓ Audit entries in correct chronological order

BLAST Summary Card
ComponentMost Critical Accuracy RuleHardest Security RuleMost Important TestTCP serverFrame length read exactlyAPI key verified per connection50 concurrent connectionsParserDE4 extracted as exactly 12 charsRaw bytes stored before parsingCorrupted bitmap → clean errorTranslation coreDE4 strip zeros only, no mathWallet lookup scoped by ASEASE A cannot resolve ASE B accountsState machineOne audit entry per transition, alwaysTransition + audit in one DB transactionConcurrent transition → only one winsRafiki clientexternalRef = STAN, alwaysWebhook HMAC verified before processingDuplicate webhook → idempotentSettlementtotal_amount verified twiceCalculated independently before submitAmount mismatch → batch abortedAudit logfrom_status NULL on first entryDB user has INSERT only, never UPDATE/DELETE6 transitions → exactly 6 entries
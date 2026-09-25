# ai_store_agent

A learning / portfolio project that teaches **how to bolt a real Agentic AI
layer onto a production-shaped Django REST Framework backend** — as opposed
to building a standalone chatbot.

It is a small e-commerce backend (products, orders, Stripe payments, crypto
payments) plus an internal "support agent" that support/admin staff can
chat with. The agent can *investigate* the system (users, products, orders,
payments) through a controlled set of tools, and can *act* on it (cancel an
order, request a refund) subject to Django permissions and, for refunds,
human approval.

> **Status**: this is a teaching project, not an audited production system.
> Read "Security notes and honest limitations" near the end before deploying
> anything derived from it.

---

## 1. Project purpose

Most "AI agent" tutorials wire an LLM directly to a database or a REST API
with no real authorization boundary. That's fine for a toy, but it's the
opposite of how you'd want to run this in a real company. This project
demonstrates the alternative:

- The LLM **never** touches PostgreSQL, Redis, Stripe, or a blockchain
  directly.
- The LLM can only pick from a fixed, declared set of **tools**.
- Every tool call is checked against **Django permissions** before it runs.
- Every tool call, successful or not, is **recorded** (`AgentToolCall`).
- Sensitive actions (refunds) create a **pending human approval** instead of
  executing immediately — the LLM can request, but only a human can approve
  and trigger execution.
- All money math, stock control and payment state transitions happen in
  **Django services**, independent of whether they were invoked from a
  normal DRF view or from the agent's tool executor.

## 2. Business problem being modeled

A small store sells products online. Customers pay by card (Stripe) or
crypto. Support/finance staff need to answer "why did this fail?" /
"what's the status of this order?" questions quickly, and occasionally need
to cancel an order or refund a payment — but refunds are financially
sensitive, so they always require a second human's sign-off, and the system
should keep an audit trail of who asked for what and who approved it.

## 3. Architecture

### 3.1 Traditional request path

```text
Request
 -> DRF View
 -> Serializer (validates shape)
 -> Service (business rules, state machine, side effects)
 -> Model / ORM
 -> Database
```

### 3.2 Agentic request path

```text
User
 |
 v
Django DRF (AgentChatView)
 |
 v
AgentService
 |
 v
LLM (OpenAI, function/tool calling)
 |
 | "what should I do?"
 |
 +---- final answer  ------------------------> returned to user
 |
 +---- tool call
          |
          v
     Tool Registry            (agent/tools/registry.py — fixed, declared set)
          |
          v
     Permission Check         (Django `user.has_perm(...)`, in the executor)
          |
          v
     Tool Handler              (agent/tools/*.py — plain Python functions)
          |
          v
     Django Service            (orders/services.py, payments/services.py, ...)
          |
   +------+------+------+
   |      |      |      |
   v      v      v      v
  DB   Stripe  Web3  (Celery for background work)
          |
          v
     Tool Result
          |
          v
         LLM
          |
          v
   Next tool call OR final answer
```

The **security boundary is Django, not the LLM**. The LLM decides *which*
tool to call and with *what arguments* — but the tool executor
independently re-checks permissions, the arguments against a declared
JSON-schema, and routes execution through the exact same service functions
a normal DRF view would use. There is no `eval()`, no `exec()`, no dynamic
code generation.

## 4. Folder structure

```text
ai_store_agent/
├── manage.py
├── config/                # settings, urls, celery app, wsgi/asgi
├── accounts/               # custom User model, JWT auth endpoints
├── products/                # product catalog
├── orders/                   # orders, order items, stock reservation
├── payments/                  # Stripe + crypto payment services, webhooks, refunds, audit log
├── agent/                      # the agentic layer
│   ├── models.py                 # AgentConversation/Message/ToolCall/ActionApproval
│   ├── permissions.py             # DRF permissions for the agent's own endpoints
│   ├── services/
│   │   ├── agent_service.py         # the actual agent loop
│   │   ├── llm_service.py            # OpenAI wrapper (only file that imports `openai`)
│   │   ├── executor.py                # tool lookup + permission check + execution + audit
│   │   ├── planner.py                  # turns LLM tool calls into executable steps
│   │   └── context_service.py           # builds the bounded message history sent to the LLM
│   ├── tools/
│   │   ├── registry.py                   # ToolDefinition + ToolRegistry (the allow-list)
│   │   ├── user_tools.py                  # get_user
│   │   ├── product_tools.py                # list_products, get_product
│   │   ├── order_tools.py                   # get_order, get_user_orders
│   │   ├── transaction_tools.py               # get_payment, get_order_payments, get_failed_payments
│   │   ├── payment_tools.py                    # get_crypto_payment_status, verify_crypto_transaction
│   │   └── action_tools.py                      # request_refund, cancel_order, send_customer_email
│   └── prompts/support_agent.py                   # the system prompt
├── common/                  # shared exceptions, constants, utils, logging, validators, seed_demo command
├── requirements.txt / requirements-dev.txt
├── Dockerfile / docker-compose.yml
├── .env.example
└── pytest.ini
```

## 5. Django apps

| App        | Responsibility |
|------------|----------------|
| `accounts` | Custom email-based `User` model, registration, JWT login/refresh/logout |
| `products` | Product catalog, admin-only writes, public reads |
| `orders`   | Orders/OrderItems, server-side pricing, atomic stock reservation, cancellation |
| `payments` | Stripe PaymentIntents + webhooks, non-custodial crypto verification, refunds, audit log |
| `agent`    | Conversations, tool registry, tool executor, agent loop, human-approval workflow |
| `common`   | Cross-cutting exceptions, constants, logging middleware, validators, `seed_demo` command |

## 6. Database design

- **User** (`accounts.User`): email-based auth, no username field.
- **Product** (`products.Product`): `price`/`stock_quantity`, `Decimal` money, slug auto-generated.
- **Order** / **OrderItem** (`orders`): `OrderItem.unit_price` snapshots the
  price *at purchase time* — historical order totals never depend on the
  live `Product.price`. Order status is one of `PENDING_PAYMENT`,
  `PAYMENT_PROCESSING`, `PAID`, `FAILED`, `CANCELLED`, `REFUNDED`.
- **PaymentTransaction** (`payments`): one row per payment attempt, with an
  explicit state machine (`INITIATED -> PROCESSING -> COMPLETED -> REFUNDED`,
  with `FAILED`/`CANCELLED` branches), a unique `idempotency_key`, and a
  `metadata` JSON field.
- **StripeWebhookEvent**: `event_id` has a **unique constraint** — this is
  what makes webhook processing idempotent against Stripe's at-least-once
  delivery retries.
- **RefundRecord**: separate from `PaymentTransaction.status` so there's a
  durable, append-only record of every refund attempt (including manual
  crypto refunds), each with its own `idempotency_key`.
- **AuditLog**: actor / action / resource_type / resource_id / metadata /
  ip_address — written only by Django services (refund, approval execution),
  never by the LLM.
- **AgentConversation / AgentMessage / AgentToolCall / AgentActionApproval**:
  the durable transcript of every agent interaction, every tool call (with
  its arguments, result, and status), and every request/approve/reject of a
  sensitive action.
- **AgentPermissionMarker**: an unmanaged model that exists purely to
  register real Django permissions like `agent.can_refund_payment`, so tool
  authorization is ordinary, auditable, admin-manageable Django permission
  data rather than a bespoke parallel system.

## 7. Authentication

JWT via `djangorestframework-simplejwt`. Email + password login; access
tokens are short-lived (30 min), refresh tokens rotate and are blacklisted
on rotation/logout.

```text
POST /api/auth/register/
POST /api/auth/login/            -> {"access": "...", "refresh": "..."}
POST /api/auth/token/refresh/
GET  /api/auth/me/
POST /api/auth/logout/           -> blacklists the given refresh token
```

## 8. Product flow

Public reads (`GET /api/products/`, `GET /api/products/{id}/`), staff-only
writes. Pagination, search (`?search=`) and filtering (`?is_active=`,
`?currency=`) are enabled via `django-filter` + DRF's `SearchFilter`.

## 9. Order flow

```text
POST /api/orders/  {"items": [{"product_id": 1, "quantity": 2}]}
   |
   v
CreateOrderSerializer validates SHAPE only (ids, positive quantities)
   |
   v
orders.services.create_order():
   - SELECT ... FOR UPDATE locks each Product row
   - checks is_active + stock_quantity >= quantity
   - snapshots unit_price from the live Product.price
   - computes subtotal/total SERVER-SIDE (client-supplied amounts are never trusted)
   - creates Order + OrderItem rows inside one atomic transaction
```

`POST /api/orders/{id}/cancel/` is only allowed while the order is still
`PENDING_PAYMENT` / `PAYMENT_PROCESSING`, and releases the reserved stock
back to the product.

## 10. Stripe flow

```text
POST /api/payments/stripe/create/  {"order_id": 123}
   |
   v
verify the caller owns the order
   |
   v
amount = order.total_amount   (NEVER trust a client-supplied amount)
   |
   v
PaymentTransaction created (status=PROCESSING) with a unique idempotency_key
   |
   v
StripeService.create_payment_intent(amount, currency, idempotency_key=...)
   |
   v
response: {"payment": {...}, "client_secret": "..."}
```

The frontend uses `client_secret` with Stripe.js/Elements to actually
collect card details and confirm the PaymentIntent — none of that ever
touches this backend directly.

## 11. Stripe webhook flow

```text
POST /api/payments/stripe/webhook/         (no JWT auth — Stripe-signature verified)
   |
   v
StripeService.construct_webhook_event()     verifies signature via STRIPE_WEBHOOK_SECRET
   |
   v
StripeWebhookEvent.objects.create(event_id=...)   <- unique constraint on event_id
   |                                                   IntegrityError on retry -> 200 OK, no-op (idempotent)
   v
dispatch by event["type"]:
   payment_intent.succeeded      -> payments.services.complete_payment()  -> Order PAID
   payment_intent.payment_failed -> payments.services.fail_payment()      -> Order FAILED
```

`complete_payment()` is itself idempotent: if the payment is already
`COMPLETED` it's a safe no-op, so even if two webhook deliveries both slip
past the `StripeWebhookEvent` uniqueness check in some edge case, the order
is never double-processed.

## 12. Crypto payment flow

**This project never stores or uses a private key.** It is a strictly
**non-custodial verification** architecture: the backend tells the client
where to send funds, and independently checks the chain afterwards.

```text
POST /api/payments/crypto/create/  {"order_id": 123}
   -> {"receiving_address": "...", "chain_id": ..., "amount": "...", "order_id": ...}

(user sends crypto from their own wallet to receiving_address)

POST /api/payments/crypto/verify/  {"payment_id": 1, "tx_hash": "0x..."}
   |
   v
CryptoPaymentService.verify_transaction():
   - looks up tx_hash via Web3 RPC (CRYPTO_RPC_URL)
   - checks: transaction exists / correct chain_id / recipient == CRYPTO_RECEIVING_ADDRESS
             / status == success / value >= expected amount / confirmations >= CRYPTO_MIN_CONFIRMATIONS
   - raises InvalidCryptoTransaction on any mismatch
   |
   v
payments.services.complete_payment()  -> Order PAID (idempotent)
```

The provider itself is abstracted (`CryptoProvider` / `Web3Provider` /
`TestnetProvider`) so a different chain (or a mocked provider for tests)
can be swapped in without touching business logic.

## 13. Agent architecture (see also section 3.2)

- **AgentService** (`agent/services/agent_service.py`) owns the loop:
  build context -> call LLM -> if tool call(s), execute + feed results back
  -> repeat -> until a final answer or `AGENT_MAX_ITERATIONS` is hit.
- **LLMService** (`agent/services/llm_service.py`) is the only file that
  imports the `openai` SDK. It turns `(messages, tools)` into a
  `LLMResponse(content, tool_calls)`.
- **ToolRegistry** (`agent/tools/registry.py`) is a fixed, explicit
  allow-list of `ToolDefinition`s (name, JSON schema, handler function,
  required Django permission, read-only flag, confirmation flag).
- **Executor** (`agent/services/executor.py`) is the actual security
  boundary: looks the tool up, checks `user.has_perm(...)`, checks required
  arguments are present, calls the plain Python handler function, and
  records an `AgentToolCall` row regardless of outcome.

## 14. Tool calling

Tools are declared once, in one place, and turned into OpenAI's function
schema automatically:

```python
registry.register(
    ToolDefinition(
        name="get_order",
        description="Get full details of an order ... by its order_number.",
        parameters={"type": "object", "properties": {"order_number": {"type": "string"}}, "required": ["order_number"]},
        handler=get_order,
        required_permission="agent.can_read_order",
        read_only=True,
        requires_confirmation=False,
    )
)
```

`registry.as_openai_tools()` serializes every registered tool into the
`tools=[...]` parameter passed to `chat.completions.create(...)`.

## 15. Agent loop (step by step)

1. `AgentChatView` rate-limits the user (Redis-backed, configurable), then
   calls `AgentService.handle_message`.
2. If no `conversation_id` was given, a new `AgentConversation` is created.
3. `context_service.build_messages()` returns the system prompt + the last
   `MAX_HISTORY_MESSAGES` (20) messages from Postgres — not the whole
   history forever.
4. The loop calls `LLMService.get_completion(messages, tools)`.
5. If the model returns tool call(s): each is validated + executed via
   `executor.execute_tool()`, the `AgentToolCall` audit row is written, and
   the tool result (success or structured error) is appended back into the
   message list as a `role="tool"` message, then the loop continues.
6. If the model returns plain content with no tool calls: that's the final
   answer, and the loop stops.
7. `AGENT_MAX_ITERATIONS` (default 8, from `.env`) prevents infinite loops;
   if hit, a clear "I hit the iteration limit" message is returned instead of
   silently guessing.

## 16. Redis

Used for:

- **Rate limiting** `POST /api/agent/chat/` (`AGENT_RATE_LIMIT_PER_MINUTE`,
  default 30/user/minute) via Django's cache framework (`django.core.cache`)
  pointed at Redis.
- Backing Django's `CACHES["default"]` generally (available for any other
  application caching need).
- Celery broker + result backend (separate Redis DB indices).

## 17. Celery

`config/celery.py` wires up the Celery app from Django settings.
Implemented tasks:

- `payments.tasks.verify_crypto_transaction_task` — background on-chain
  verification (fire-and-forget from a client that doesn't want to block on
  an RPC round-trip), with retry-with-backoff on transient failures.
- `agent.tasks.send_customer_email_task` — the `send_customer_email` agent
  tool enqueues this rather than blocking the HTTP request on SMTP.
- `agent.tasks.analyze_large_transaction_task` — example "flag for review"
  background job over a payment.

## 18. Human approval (refunds)

```text
User: "Refund ORD-1001."
   |
   v
agent tool call: request_refund(order_number="ORD-1001", reason="...")
   |
   v
executor checks agent.can_refund_payment, then calls the handler
   |
   v
handler creates AgentActionApproval(status=PENDING) — NOTHING is refunded yet
   |
   v
agent's reply MUST say "awaiting approval", never "refund completed"
   |
   v
(a human with can_refund_payment calls)
POST /api/agent/approvals/{id}/approve/
   |
   v
payments.services.refund_payment() actually runs (Stripe refund API call,
state machine transition, RefundRecord, AuditLog)
   |
   v
approval.status = EXECUTED (or FAILED, with approval.error set)
```

`POST /api/agent/approvals/{id}/reject/` marks it `REJECTED` instead, with
an optional `note`. Both approve and reject are staff-only
(`CanApproveAgentActions`), and approve is idempotent: calling it twice on
an already-`EXECUTED` approval just returns the existing record rather than
refunding twice.

## 19. Security

- JWT auth everywhere except the Stripe webhook (Stripe-signature verified
  instead) and public product reads.
- Object-level ownership checks (`IsOrderOwnerOrStaff`, order/payment
  ownership checks in views and services).
- Staff-only writes on products; staff-only refund/approval endpoints.
- Every secret (Stripe keys, OpenAI key, DB password, crypto RPC URL) comes
  from environment variables, never hardcoded, never returned in any API
  response.
- Tool-level authorization is enforced independently of whatever the LLM
  "intended" — see section 3.2.
- Rate limiting on the agent chat endpoint.
- Consistent, stack-trace-free error envelope: `{"error": {"code": "...", "message": "..."}}`.
- Request logging middleware logs request id / user id / method / path /
  status / duration — and explicitly never logs bodies, passwords, or keys.

## 20. Idempotency

Idempotency matters here because **retries are a fact of life** with
external systems: Stripe redelivers webhooks, a flaky network can cause a
client to double-submit a "verify my crypto payment" request, and a human
approver might double-click "Approve". Without idempotency:

- A retried Stripe webhook could refund or "complete" a payment twice.
- A duplicate crypto verification call could double-credit an order.
- A double-clicked refund approval could refund a customer twice.

This project achieves idempotency via:

- A **unique constraint** on `StripeWebhookEvent.event_id` (duplicate
  webhook delivery -> `IntegrityError` -> treated as a no-op, 200 OK).
- `complete_payment()` short-circuiting if the payment is already
  `COMPLETED`.
- `refund_payment()` taking an `idempotency_key` and returning the existing
  `RefundRecord` if one already exists for that key.
- `ApproveActionView` checking `approval.status == EXECUTED` and returning
  the existing result instead of re-running the refund.
- Stripe API calls themselves passing an `idempotency_key` to Stripe.

## 21. Testing

41 tests, all mocking external services (no real Stripe/OpenAI/blockchain
calls in the suite):

```bash
# locally with sqlite (fast, no Postgres/Redis needed)
export USE_SQLITE_FOR_TESTS=True SECRET_KEY=test STRIPE_SECRET_KEY=sk_test_x \
       STRIPE_WEBHOOK_SECRET=whsec_x OPENAI_API_KEY=sk-test \
       CRYPTO_RECEIVING_ADDRESS=0x0000000000000000000000000000000000000000
python manage.py test

# inside Docker (uses the real Postgres service)
docker compose exec web python manage.py test
```

Coverage includes: registration/login/JWT, product CRUD + permissions,
order creation/stock races/ownership/cancellation, Stripe PaymentIntent
creation + webhook success/failure/duplicate/invalid-signature, crypto
verification (valid / wrong recipient / wrong chain / insufficient amount /
failed tx / duplicate verification), and the full agent test matrix (simple
answer, single tool call, multiple tool calls, unknown tool, invalid
arguments, tool failure, permission denied, max iterations) plus the
approval workflow (create/approve/reject/duplicate-execution/unauthorized).

## 22. Docker setup

```bash
cp .env.example .env    # then fill in real Stripe/OpenAI/crypto values as needed
docker compose up --build

# in another terminal:
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py createsuperuser   # optional, seed_demo already makes an admin
```

Services: `web` (gunicorn), `postgres`, `redis`, `celery_worker`,
`celery_beat`. The `web` service itself runs `migrate` on container start
before launching gunicorn.

## 23. API documentation

All endpoints are namespaced under `/api/`. Authenticated endpoints expect
`Authorization: Bearer <access_token>`.

### Accounts

```text
POST /api/auth/register/        Body: {"email","password","first_name","last_name"}    -> 201 User
POST /api/auth/login/           Body: {"email","password"}                              -> 200 {"access","refresh"}
POST /api/auth/token/refresh/   Body: {"refresh"}                                        -> 200 {"access"}
GET  /api/auth/me/              Auth required                                             -> 200 User
POST /api/auth/logout/          Body: {"refresh"}, Auth required                           -> 205
```

```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","password":"StrongPassword123!","first_name":"Jane","last_name":"Doe"}'

curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","password":"StrongPassword123!"}'
```

### Products

```text
GET    /api/products/            public, paginated, ?search=, ?is_active=, ?currency=, ?ordering=
GET    /api/products/{id}/       public
POST   /api/products/            staff only
PUT    /api/products/{id}/       staff only
PATCH  /api/products/{id}/       staff only
DELETE /api/products/{id}/       staff only
```

```bash
curl http://localhost:8000/api/products/?search=widget

curl -X POST http://localhost:8000/api/products/ \
  -H "Authorization: Bearer <STAFF_TOKEN>" -H "Content-Type: application/json" \
  -d '{"name":"New Widget","price":"29.99","stock_quantity":50}'
```

### Orders

```text
POST /api/orders/                Auth required. Body: {"items":[{"product_id":1,"quantity":2}]}
GET  /api/orders/                 own orders (staff: all)
GET  /api/orders/{id}/             owner or staff
POST /api/orders/{id}/cancel/       owner or staff
```

```bash
curl -X POST http://localhost:8000/api/orders/ \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"items":[{"product_id":1,"quantity":2}]}'
```

Error example (insufficient stock):

```json
{"error": {"code": "INSUFFICIENT_STOCK", "message": "Only 5 units of 'Gadget' are in stock."}}
```

### Payments

```text
GET  /api/payments/                       own history (staff: all)
POST /api/payments/stripe/create/          Body: {"order_id": 1}     -> {"payment", "client_secret"}
POST /api/payments/stripe/webhook/          Stripe-signature verified, no JWT
POST /api/payments/crypto/create/           Body: {"order_id": 1}     -> {"receiving_address","chain_id","amount",...}
POST /api/payments/crypto/verify/            Body: {"payment_id": 1, "tx_hash": "0x..."}
POST /api/payments/{id}/refund/               staff / agent.can_refund_payment only. Body: {"reason": "..."}
```

```bash
curl -X POST http://localhost:8000/api/payments/stripe/create/ \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"order_id": 1}'

curl -X POST http://localhost:8000/api/payments/crypto/verify/ \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"payment_id": 3, "tx_hash": "0xabc123..."}'
```

### Agent

```text
POST /api/agent/chat/                        support/admin (staff) only. Body: {"message","conversation_id"?}
GET  /api/agent/conversations/{id}/           inspect full transcript + tool calls
GET  /api/agent/approvals/?status=PENDING     list approvals
POST /api/agent/approvals/{id}/approve/        staff only
POST /api/agent/approvals/{id}/reject/          staff only. Body: {"note": "..."}
```

```bash
curl -X POST http://localhost:8000/api/agent/chat/ \
  -H "Authorization: Bearer <SUPPORT_TOKEN>" -H "Content-Type: application/json" \
  -d '{"message": "Why did order ORD-1001 fail?"}'
```

## 24. Agent flow walkthrough (concrete example)

```text
User request:  "Why did ORD-1001 fail?"
 -> DRF AgentChatView (rate limit check, staff-only)
 -> AgentService.handle_message()
 -> LLM sees system prompt + tool schemas + the question
 -> LLM decides: call get_order(order_number="ORD-1001")
 -> Tool Registry finds "get_order"
 -> Executor checks user.has_perm("agent.can_read_order")
 -> orders.get_order() handler queries the Order model
 -> Tool Result: {"status": "FAILED", "total_amount": "49.50", ...}
 -> Result appended back into the LLM's message list
 -> LLM decides: call get_order_payments(order_number="ORD-1001")
 -> ... same pipeline ...
 -> Tool Result: {"payments": [{"status": "FAILED", "failure_reason": "Your card was declined.", ...}]}
 -> LLM produces final answer:
    "Order ORD-1001 failed because the Stripe payment was declined
     (reason: 'Your card was declined.'). The order status is FAILED."
```

## 25. Payment flow walkthrough

```text
Stripe:  Order -> POST /payments/stripe/create/ -> Stripe PaymentIntent
                -> (frontend confirms with Stripe.js) -> Stripe webhook
                -> payment_intent.succeeded -> complete_payment() -> Order PAID

Crypto:  Order -> POST /payments/crypto/create/ -> {receiving_address, chain_id, amount}
                -> (user sends funds from their own wallet)
                -> POST /payments/crypto/verify/ {tx_hash}
                -> Web3 RPC lookup + checks -> complete_payment() -> Order PAID
```

## 26. Example agent conversations

**1. Simple lookup**
> "What is the status of order ORD-1001?"
Tools called: `get_order`. Agent answers directly from the tool result.

**2. Root-cause investigation**
> "Why did ORD-1001 fail?"
Tools called: `get_order`, then `get_order_payments` (and, if needed,
`get_payment` for a specific transaction id). Agent reasons over the
combined results.

**3. Customer history**
> "Show me the last 5 orders of customer 10."
Tools called: `get_user` (to confirm the user exists / get their name),
then `get_user_orders(user_id=10, limit=5)`.

**4. Refund with human approval**
> "Refund ORD-1001."
Tool called: `request_refund(order_number="ORD-1001", ...)`. This does
**not** refund anything — it creates a `PENDING` `AgentActionApproval`. The
agent's reply: *"A refund request for ORD-1001 has been created and is
awaiting approval. It has not been processed yet."* Only after
`POST /api/agent/approvals/{id}/approve/` does the refund actually execute.

**5. Crypto troubleshooting**
> "Did the crypto payment for order ORD-1004 go through?"
Tools called: `get_order`, `get_order_payments`, and potentially
`verify_crypto_transaction` if the user supplies a transaction hash to
recheck — which re-runs the real on-chain check rather than trusting the
stored `FAILED` status blindly.

## 27. How to extend the system

### Add a new product
Use the admin site, `POST /api/products/` as staff, or Django admin/shell —
no code changes required.

### Add a new payment provider
1. Add a new value to `PAYMENT_METHOD_CHOICES` in `common/constants.py`.
2. Create a `<provider>_service.py` in `payments/`, following the same
   shape as `stripe_service.py` (a thin class wrapping the provider's SDK,
   never imported anywhere except from `payments/services.py`).
3. Add create/verify views + URLs in `payments/views.py` / `payments/urls.py`.
4. Extend `payments/services.py` (`refund_payment`, etc.) to branch on the
   new `payment_method` where provider-specific behaviour is needed.
5. Add tests mocking the new provider's SDK — never call the real API in
   tests.

### Add a new agent tool (worked example: `get_customer_spending_summary`)

1. **Write the handler** (in an existing or new `agent/tools/*.py` file):

   ```python
   def get_customer_spending_summary(*, user_id: int) -> dict:
       from django.db.models import Sum
       from payments.models import PaymentTransaction

       total = PaymentTransaction.objects.filter(
           user_id=user_id, status="COMPLETED"
       ).aggregate(total=Sum("amount"))["total"] or 0
       return {"user_id": user_id, "total_completed_spend": str(total)}
   ```

2. **Declare the ToolDefinition** and register it:

   ```python
   registry.register(
       ToolDefinition(
           name="get_customer_spending_summary",
           description="Get a customer's total completed spend.",
           parameters={
               "type": "object",
               "properties": {"user_id": {"type": "integer"}},
               "required": ["user_id"],
           },
           handler=get_customer_spending_summary,
           required_permission="agent.can_read_payment",  # reuse or add a new permission
           read_only=True,
       )
   )
   ```

3. **Add a permission** (if reusing an existing one isn't appropriate) to
   `AgentPermissionMarker.Meta.permissions` in `agent/models.py`, then
   `makemigrations` + `migrate`.
4. **Grant the permission** to the relevant staff group/user (admin site or
   `seed_demo`).
5. **Write a test** in `agent/tests/` mocking the LLM to call this tool and
   asserting the result.
6. That's it — because `registry.as_openai_tools()` serializes the whole
   registry automatically, the agent starts offering this tool to the LLM
   the moment it's registered. No changes to `agent_service.py`,
   `executor.py`, or the system prompt are needed.

### Add a new agent permission
Add a tuple to `AgentPermissionMarker.Meta.permissions` in `agent/models.py`,
run `python manage.py makemigrations agent && python manage.py migrate`,
then reference it as a tool's `required_permission` and grant it via the
admin site (`Users -> <user> -> User permissions`) or a management command.

### Add a new background task
Add a `@shared_task` function to the relevant app's `tasks.py` (see
`payments/tasks.py`, `agent/tasks.py`), then call `.delay(...)` from wherever
needs it. No Celery config changes are required — `config/celery.py`
autodiscovers tasks across all installed apps.

## 28. Demo credentials (seed_demo)

Run `python manage.py seed_demo` (or `docker compose exec web python manage.py seed_demo`).
**These are demo-only — never reuse them anywhere real.**

| Email | Password | Notes |
|---|---|---|
| admin@example.com | Admin12345! | Django superuser |
| support@example.com | Support12345! | read-only agent tools |
| senior_support@example.com | SeniorSupport12345! | + cancel_order, send_customer_email |
| finance_admin@example.com | FinanceAdmin12345! | + request_refund (still needs a second approver) |
| customer@example.com | Customer12345! | regular customer, owns the seeded demo orders |

Seeded orders: `ORD-DEMO001` (Stripe success), `ORD-DEMO002` (Stripe
failure), `ORD-DEMO003` (crypto success), `ORD-DEMO004` (crypto failure).

## 29. Security notes and honest limitations

This is a learning project. Before treating any of this as production-ready:

- Crypto amount-to-wei conversion in `CryptoPaymentService.amount_to_wei`
  is deliberately simplified (assumes 18 decimals, one currency) — a real
  system needs proper decimal/token handling per asset.
- The agent's persisted "tool" messages are a simplified human-readable
  transcript, not a byte-for-byte replay of OpenAI's tool-calling protocol;
  fine for this project's UI/audit purposes, but a production system
  replaying multi-turn tool conversations verbatim would want to persist
  the raw OpenAI message objects too.
- Rate limiting is a simple fixed-window counter in Redis — a sliding
  window or token bucket would be more precise under bursty traffic.
- No email provider is wired up for `send_customer_email` — it logs and
  returns a queued task result so the flow is demonstrable.
- Refund permission plus human approval is enforced for Stripe *and*
  crypto, but crypto refunds are explicitly manual/off-chain — there is
  intentionally no automated on-chain refund path.

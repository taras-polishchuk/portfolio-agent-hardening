# portfolio-agent-hardening

A production n8n AI workflow hardened against 11 documented threat vectors, with 54 automated regression tests covering the architecture invariants that hold across versions.

## Problem

A public-facing AI assistant is a high-value attack surface. Recruiter chat widgets get probed daily with prompt injection, identity hijack attempts, off-topic redirects, and credential extraction. Building an LLM app is easy. Building one that survives real-world adversarial traffic is not.

This repository is the production-hardened n8n workflow behind my own portfolio AI assistant, with all internal identifiers (workflow IDs, webhook UUIDs, credentials, n8n encryption keys, salary numbers, private infrastructure hostnames) redacted and replaced with stable placeholders.

## Motivation

When I started, the chat widget had:
- A naked system prompt with no role binding
- A post-LLM guard that only logged to Discord
- No input length cap
- No session validation
- A general-purpose LLM that answered coding questions

After 14 internal hardening iterations (v1..v14), the workflow now has 11 documented threat-vector defenses, three independent prompt-injection layers, a graceful LLM error fallback that does not leak stack traces, and a structured system message that locks the model into a narrow role. This public repo ships the 8 publicly releasable workflow versions (v2..v9) and a 54-test pytest suite covering architectural invariants that hold across every shipped version, plus the structural / redaction invariants that prove the public artifact is consistent.

## Architecture

Three independent layers of defense (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full diagram):

```
            ┌─────────────────────────────────────────────┐
   visitor  │  Chat Trigger (n8n)                         │
   ────────▶│     │                                       │
            │     ▼                                       │
            │  Pre-LLM Guard (Code node)                  │
            │   - sessionId validation                    │
            │   - input length cap                        │
            │   - off-topic denylist                      │
            │   - prompt-injection pattern match          │
            │     │                                       │
            │     ▼                                       │
            │  AI Agent (with armored system prompt)      │
            │     │                                       │
            │     ▼                                       │
            │  Post-LLM Guard (Code node)                 │
            │   - identity-claim override                 │
            │   - instruction-leak detection              │
            │   - URL whitelist (portfolio + github)      │
            │   - output length cap                       │
            │     │                                       │
            │     ▼                                       │
            │  Discord notify + Respond to Webhook        │
            └─────────────────────────────────────────────┘
```

Each layer can independently stop an attack. The pre-LLM guard saves the LLM cost when it blocks. The post-LLM guard catches anything that slips past the system prompt. The system prompt binds the model to a narrow role so it does not want to do the wrong thing.

## Features

- 11-node n8n workflow (v9 ships in this repo; v2..v9 evolution visible in `workflows/`)
- 3 layers of prompt-injection defense (pre-LLM regex, system message armor, post-LLM validation)
- 11 documented threat vectors with named defenses (see [docs/THREAT-VECTORS.md](docs/THREAT-VECTORS.md))
- 54 regression tests covering architecture, system message, pre/post-LLM guards, KB redaction
- Sanitized JSON for v2..v9 with placeholders for every internal identifier
- PII redacted from the knowledge base (salary, hourly rate, internal hostnames)

## Installation

This repo ships sanitized workflow JSON and tests only — not the runtime. To run the tests:

```bash
# 1. Clone the repo
git clone https://github.com/taras-polishchuk/portfolio-agent-hardening
cd portfolio-agent-hardening

# 2. (optional) Create a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 3. Install test dependencies
pip install pytest

# 4. Run the test suite
pytest tests/ -v
```

Expected output:

```
============================== 54 passed in 0.10s =============================
```

## QuickStart

To import a sanitized workflow into your own n8n instance:

1. Open n8n → Workflows → Import from file
2. Pick `workflows/portfolio-agent.hardened.v9.sanitized.json`
3. Replace every placeholder with your real values:
   - `<redacted-workflow-id>` → leave blank for new workflow
   - `<redacted-webhook-id>` → leave blank; n8n generates a new one
   - `<redacted-credential-id>` / `<redacted-credential-name>` → set up new LLM credential in n8n
   - `<redacted-bridge-url>` → your notification bridge URL (or remove the Discord notify block)
   - `<redacted-compensation — see private notes>` → your own salary disclosure policy
4. Configure the LLM credential (OpenAI, Anthropic, or any OpenAI-compatible endpoint)
5. Activate the workflow

Note: the system prompt and knowledge base are kept intentionally generic (referencing "Taras" and his projects). Replace them with your own persona before activating.

## TechStack

- **Workflow engine:** n8n 2.x with `@n8n/n8n-nodes-langchain` (Chat Trigger, AI Agent, Chat Model nodes)
- **LLM providers:** Pluggable — default MiniMax, swappable to Anthropic Claude, OpenAI GPT-4, or any OpenAI-compatible endpoint
- **Code nodes:** JavaScript (n8n Code node sandbox, no child_process)
- **Tests:** pytest 9.x, pure stdlib for assertions
- **Sanitization:** Python 3 script (`redact_workflows.py` not included — see [docs/RELEASE-PROCESS.md](docs/RELEASE-PROCESS.md) for the operator-side script outline)

## Design Decisions

**Why three independent layers?** Each layer fails differently. The pre-LLM guard fails closed (no LLM cost). The system message fails soft (LLM might comply, post-LLM catches it). The post-LLM guard fails open on the LLM but re-validates everything. Any one of them can stop a known attack; together they cover novel ones.

**Why regex pre-LLM guard instead of an LLM-as-judge?** Cost. A regex guard is free per request; a guard LLM adds 200-500ms latency and per-token cost on every chat. Recruiter chat traffic is spiky and adversarial; you want the cheap filter first.

**Why explicit system prompt rules instead of letting the LLM figure it out?** Production reliability. A 2-page free-form prompt is unpredictable; a structured prompt with 8 numbered rules, KB-only constraint, and identity binding is auditable and testable. The regression tests assert the structure stays the same.

**Why is the public v9 and not the latest v14?** v9 is the last version whose code is fully under 200 lines per Code node, with no proprietary client or backend coupling. v10+ introduced an LLM error fallback with infrastructure-specific retry logic and a few internal-API calls that would not be useful in a public sample. The 12 hardening tests that cover v10+ fixes are in the private monorepo (see [docs/HARDENING-HISTORY.md](docs/HARDENING-HISTORY.md) for the audit trail).

**Why redact the knowledge base, not the test cases?** The KB is the "what the assistant says" payload. Real numbers (compensation, personal contact) are private negotiation data, not security secrets, but exposing them in a public repo is still inappropriate. The test cases assert the redaction happened, so any future PR that leaks the numbers back in will fail the test suite.

## Trade-offs

| Decision | Pro | Con |
|---|---|---|
| Plain regex pre-LLM guard | Free, fast, deterministic | Brittle against Unicode evasion (NFKC fix landed in v10+, see HARDENING-HISTORY.md) |
| Hard-coded system prompt | Auditable, version-controlled | 200+ tokens per request; cannot A/B test variants without redeploying the workflow |
| KB-only responses | No hallucination, no off-topic drift | "I don't have that information" is the most common answer until the KB grows |
| Chat Trigger webhook | Public by default, no auth | Need upstream rate limiting + session validation; a flood of requests hits the LLM cost |
| Sanitized export (placeholders) | Safe to publish, no internal IDs leak | A fresh n8n import needs manual credential setup before it can run |

## Roadmap

What is in the public repo now (v9):
- 8 hardened versions (v2..v9)
- 54 regression tests
- 11 documented threat vectors
- 3 layers of defense

What landed AFTER v9 (in the private monorepo, see HARDENING-HISTORY.md):
- LLM Error Fallback node (graceful degradation when LLM provider fails)
- NFKC normalization + control-char stripping in pre-LLM guard
- Stable pattern IDs in telemetry (instead of regex source in logs)
- Discord notify AFTER post-validation (no raw LLM leak)
- Discord Notify Refusal wired into chain (no orphan nodes)
- Single canonical identity model in system prompt (no contradictions)
- "rejects" not "strips" wording in KB (factual accuracy)
- URL parsing via `new URL()` instead of regex prefix
- Tightened off-topic denylist (no `/translate/`, `/essay/`, `/article/` false positives)
- Infrastructure disclosure reduction in KB
- Node count consistency between workflow and KB

If you are building a production AI assistant, the LLM Error Fallback and Discord-notify-after-validation fixes alone are worth replicating — they are the two real-world bugs that the audit caught.

## Limitations

- This is a sanitized reference, not a turnkey deployment. You need your own n8n instance, LLM credential, and (optionally) a notification bridge.
- The v9 workflow uses a Chat Trigger webhook with no built-in rate limit. Add upstream rate limiting (Cloudflare, nginx) before exposing publicly.
- The system prompt is hard-coded in the workflow JSON. Editing it requires n8n re-deploy.
- The KB is a single text block in `workflows/qa-knowledge-base.sanitized.txt`. For larger knowledge bases, swap in a vector store (Qdrant, pgvector) and a retriever node.

## Test count: 54

The 54 tests in this public repo cover everything that holds across the
publicly releasable v2..v9 versions. Running them is a one-liner:

```bash
pytest -q
```

Expected output:

```
54 passed in 0.10s
```

## License

MIT — see [LICENSE](LICENSE).

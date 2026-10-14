# Architecture

## High-level Flow

```
                         ┌────────────────────────────────────────────────┐
                         │                  Visitor                       │
                         └─────────────────────┬──────────────────────────┘
                                               │ chat message
                                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           n8n Workflow (v9)                                  │
│                                                                              │
│  ┌────────────────────┐                                                      │
│  │ Chat Trigger       │ webhook (n8n-generated UUID)                        │
│  │ @n8n/.../chatTrgr  │ POST { chatInput, sessionId }                       │
│  └────────┬───────────┘                                                      │
│           │                                                                  │
│           ▼                                                                  │
│  ┌────────────────────┐                                                      │
│  │ Pre-LLM Guard      │ JavaScript Code node                                 │
│  │                    │ - sessionId regex  ^[a-zA-Z0-9_-]{6,128}$            │
│  │                    │ - chatInput.length ≤ 500                            │
│  │                    │ - chatInput.length > 0                              │
│  │                    │ - off-topic denylist (regex)                         │
│  │                    │ - injection pattern denylist (regex)                 │
│  │                    │                                                      │
│  │ outputs:           │                                                      │
│  │   if blocked: {    │                                                      │
│  │     blocked: true, │                                                      │
│  │     reason,        │                                                      │
│  │     response       │                                                      │
│  │   }                │                                                      │
│  │   else: {          │                                                      │
│  │     preChecked:    │                                                      │
│  │       true, ...    │                                                      │
│  │   }                │                                                      │
│  └────┬───────────────┘                                                      │
│       │                                                                      │
│       ▼                                                                      │
│  ┌────────────────────┐        ┌────────────────────┐                       │
│  │ Check Blocked      │───────▶│ Refusal Response   │                       │
│  │ (IF node)          │ blocked│ (Code node)        │                       │
│  └────┬───────────────┘        │ - returns canned   │                       │
│       │ not blocked            │   refusal message  │                       │
│       │                        └─────────┬──────────┘                       │
│       │                                  │                                  │
│       ▼                                  ▼                                  │
│  ┌────────────────────┐        ┌────────────────────┐                        │
│  │ AI Agent           │        │ Discord Notify     │                        │
│  │ @n8n/.../agent     │        │ Refusal            │                        │
│  │ + MiniMax Chat     │        │ (HTTP Request)     │                        │
│  │   Model            │        └─────────┬──────────┘                        │
│  │ + armored system   │                  │                                   │
│  │   prompt (8 rules  │                  ▼                                   │
│  │   + KB)            │        ┌────────────────────┐                        │
│  └────────┬───────────┘        │ Respond Refusal    │                        │
│           │                    │ (Respond to Webhook)│                        │
│           ▼                    └────────────────────┘                        │
│  ┌────────────────────┐                                                      │
│  │ Post-LLM Guard     │ JavaScript Code node                                 │
│  │ = Notify Discord & │ - identity-claim override (regex)                   │
│  │   Respond          │ - instruction-leak check (regex)                    │
│  │                    │ - URL whitelist (regex: taras-polishchuk only)       │
│  │                    │ - output length cap (≤ 800 chars)                   │
│  │                    │ - Discord notify (best-effort, after validation)   │
│  │                    │ - returns { output: <safe_reply> }                  │
│  └────────┬───────────┘                                                      │
│           │                                                                  │
│           ▼                                                                  │
│  ┌────────────────────┐                                                      │
│  │ Discord Notify Q   │ HTTP Request                                        │
│  │ (HTTP Request)     │ POST to local bridge (Discord webhook relay)        │
│  └────────┬───────────┘                                                      │
│           │                                                                  │
│           ▼                                                                  │
│  ┌────────────────────┐                                                      │
│  │ Respond Q          │ Respond to Webhook                                  │
│  │ (Respond node)     │ returns { output: <reply> } as JSON                 │
│  └────────────────────┘                                                      │
└──────────────────────────────────────────────────────────────────────────────┘
                                               │
                                               ▼
                         ┌────────────────────────────────────────────────┐
                         │              Visitor (browser)                  │
                         └────────────────────────────────────────────────┘
```

## Node Inventory (v9)

11 nodes total. The names match the regression tests in `tests/test_v9_hardening.py::test_required_nodes_present_v9`.

| # | Name | Type | Role |
|---|------|------|------|
| 1 | When chat message received | `@n8n/.../chatTrigger` | Webhook entrypoint |
| 2 | Pre-LLM Guard | `n8n-nodes-base.code` | Input validation (session, length, off-topic, injection) |
| 3 | Check Blocked | `n8n-nodes-base.if` | Branches on `preChecked: true` |
| 4 | AI Agent | `@n8n/.../agent` | LLM reasoning with armored system prompt |
| 5 | MiniMax Chat Model | `@n8n/.../lmChatMinimax` | Underlying LLM provider |
| 6 | Refusal Response | `n8n-nodes-base.code` | Canned refusal when pre-LLM guard blocked |
| 7 | Notify Discord & Respond | `n8n-nodes-base.code` | Post-LLM guard (identity, leak, URL, length) |
| 8 | Respond Q | `n8n-nodes-base.respondToWebhook` | Returns Q-path reply to visitor |
| 9 | Respond Refusal | `n8n-nodes-base.respondToWebhook` | Returns refusal-path reply to visitor |
| 10 | Discord Notify Q | `n8n-nodes-base.httpRequest` | Posts successful Q to Discord |
| 11 | Discord Notify Refusal | `n8n-nodes-base.httpRequest` | Posts blocked Q to Discord |

## Defense Layers

Three independent layers, each capable of stopping a known attack on its own:

### Layer 1: Pre-LLM Guard (cheap, fails closed)

- **What:** JavaScript Code node, runs before the LLM
- **Cost:** ~1ms per request, zero tokens
- **Behavior:** Returns `{ blocked: true, reason, response }` if the input fails any check; the workflow routes to `Refusal Response` and never calls the LLM
- **Checks:** sessionId regex, input length, off-topic denylist, prompt-injection denylist

### Layer 2: System Prompt Armor (binds the model)

- **What:** Structured text passed to the AI Agent as `options.systemMessage`
- **Cost:** ~400 tokens per request (counted as input)
- **Behavior:** Locks the LLM into a narrow role with 8 explicit rules + KB-only constraint
- **Strengths:** Identity binding, refusal language, KB-only answers, no-instruction-leak, no-meta-commentary
- **Weaknesses:** LLMs are probabilistic; the model might still try to comply with a clever injection

### Layer 3: Post-LLM Guard (catches what slipped through)

- **What:** JavaScript Code node, runs after the LLM
- **Cost:** ~1ms per request, zero tokens
- **Behavior:** Re-validates the LLM output; replaces unsafe replies with a safe canned message
- **Checks:** identity-claim override, instruction-leak patterns, URL whitelist, output length cap

## Why this composition

- **Pre-LLM is cheap and fast.** Most attacks never reach the LLM cost meter.
- **System prompt is the binding.** When the LLM is uncertain, the rules tell it what to refuse.
- **Post-LLM is the last word.** Even if the system prompt is bypassed, the response is re-validated.

Each layer can fail differently:
- Pre-LLM fails closed (no LLM cost)
- System prompt fails soft (LLM might comply; post-LLM catches it)
- Post-LLM fails open on the LLM but re-validates everything

Together, they cover known attacks and most novel ones.

## Workflow Settings

- `saveDataSuccessExecutions`: not "all" (default: pruned after 7 days) — privacy + cost
- `saveDataErrorExecutions`: not "all" (default: kept for debugging) — observability without bloat
- `executionOrder`: `v1` (topological)
- `callerPolicy`: `workflowsFromSameOwner` (no cross-workflow triggers)

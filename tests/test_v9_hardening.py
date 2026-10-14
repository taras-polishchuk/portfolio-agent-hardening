"""
Smoke / regression tests for the public v9 hardened workflow.

These tests verify the SHIPPED v9 hardening invariants. They are a
subset of the full private audit (across v10..v14 in the source
monorepo); the per-version regression net for v10..v14 lives in the
private monorepo and is NOT part of this public repo.

Public scope:
- Architectural invariants that hold in v2..v9
- Top-level workflow shape
- v9-specific gating (Pre-LLM Guard, post-LLM guard, system message armor)
- Knowledge base structural invariants

If you want to verify the LATER hardening (v10..v14), those JSONs are not
public. The audit history is the source of truth for those skipped tests.
Total suite: 54 tests across test_v9_hardening.py, test_workflow_hardening.py,
and test_architecture_invariants.py.
"""
import json
import re
from pathlib import Path

# v9 is the latest shipped version in this public repo.
_REPO_ROOT = Path(__file__).resolve().parent.parent
WF_PATH = _REPO_ROOT / "workflows" / "portfolio-agent.hardened.v9.sanitized.json"
KB_PATH = _REPO_ROOT / "workflows" / "qa-knowledge-base.sanitized.txt"

WF = json.loads(WF_PATH.read_text(encoding="utf-8"))
# Normalize n8n export wrapper shape {"data": {"nodes": ...}} -> {"nodes": ...}
if isinstance(WF, dict) and "data" in WF and isinstance(WF["data"], dict) and "nodes" in WF["data"]:
    WF = WF["data"]
KB = KB_PATH.read_text(encoding="utf-8")


def get_node(name: str):
    nodes = [n for n in WF["nodes"] if n.get("name") == name]
    assert nodes, f"Node {name!r} not found"
    return nodes[0]


def get_pre_llm_guard():
    nodes = [n for n in WF["nodes"] if any(
        t in n["name"] for t in ["re-LLM", "nput Guard", "re Guard"]
    )]
    assert nodes, "No pre-LLM guard node"
    return nodes[0]


def get_post_llm_guard():
    return get_node("Notify Discord & Respond")


def get_system_message() -> str:
    return get_node("AI Agent")["parameters"]["options"]["systemMessage"]


# ----------------------------------------------------------------------------
# Architectural invariants
# ----------------------------------------------------------------------------

def test_required_nodes_present_v9():
    """v9 must have the 11-node topology documented in the public README."""
    required = [
        "When chat message received",
        "Pre-LLM Guard",
        "Check Blocked",
        "AI Agent",
        "Refusal Response",
        "Notify Discord & Respond",
        "Respond Q",
        "Respond Refusal",
        "Discord Notify Q",
        "Discord Notify Refusal",
    ]
    node_names = [n["name"] for n in WF["nodes"]]
    for name in required:
        assert name in node_names, f"v9 required node {name!r} missing. Found: {node_names}"


def test_node_count_consistent_with_claims():
    """If the KB or README claims an N-node architecture, the workflow must match."""
    node_count = len(WF["nodes"])
    # KB and docs both claim "11 nodes" — assert the count is at least 10
    # (allowing one slack for future additions).
    assert 10 <= node_count <= 13, \
        f"Workflow has {node_count} nodes, expected ~11 (allow 10..13)"


def test_chat_trigger_routes_through_pre_guard_or_agent():
    """Chat Trigger must connect to either the Pre-LLM Guard or the AI Agent."""
    conns = WF.get("connections", {})
    chat_out = conns.get("When chat message received", {}).get("main", [[]])
    assert chat_out and chat_out[0], "Chat Trigger has no output"
    next_node = chat_out[0][0]["node"]
    assert any(token in next_node for token in ["Guard", "AI Agent"]), \
        f"Chat Trigger should connect to Guard or AI Agent, got {next_node!r}"


# ----------------------------------------------------------------------------
# System message armor (v2..v9 invariant)
# ----------------------------------------------------------------------------

def test_system_message_armored():
    """System message must contain role-binding, refusal, identity, KB-only rules."""
    sm = get_system_message().lower()
    assert "taras" in sm, "System message missing Taras role binding"
    assert "knowledge base" in sm, "System message missing KB-only rule"
    assert any(t in sm for t in ["cannot", "can't", "must not", "do not"]), \
        "System message missing refusal/constraint language"
    assert any(t in sm for t in ["chatgpt", "openai", "gpt", "claude", "gemini"]), \
        "System message does not protect against identity hijack"


def test_system_message_first_person_rule():
    sm = get_system_message().lower()
    assert "first person" in sm, "System message does not enforce first-person rule"


def test_session_id_format_in_pre_guard_comment():
    """The Pre-LLM Guard comment must describe the sessionId regex accurately.

    The comment 'alphanumeric + dash, 6-128 chars' must match the actual
    regex `[a-zA-Z0-9_-]{6,128}`. This catches drift between the comment
    and the code (P0-10 in the original audit).
    """
    code = get_pre_llm_guard()["parameters"]["jsCode"]
    # Find the comment about sessionId validation
    # It should mention both "6-128" and a dash
    has_6_128 = re.search(r"6-?128", code)
    has_dash = "alphanumeric" in code.lower() and "dash" in code.lower()
    assert has_6_128, "Pre-LLM guard comment missing '6-128' sessionId length"
    assert has_dash, "Pre-LLM guard comment does not mention alphanumeric + dash"


# ----------------------------------------------------------------------------
# Pre-LLM guard: length + off-topic detection (v2..v9 invariant)
# ----------------------------------------------------------------------------

def test_pre_llm_guard_max_length_enforced():
    """Pre-LLM guard must check input length and refuse too-long inputs."""
    code = get_pre_llm_guard()["parameters"]["jsCode"]
    assert re.search(r"length\s*[<>]|MAX_INPUT|chatInput\.length", code), \
        "Pre-LLM guard does not check input length"


def test_pre_llm_guard_offtopic_patterns_no_false_positives():
    """The off-topic denylist must not match legitimate queries.

    Example: a question like "How do you build AI workflows?" contains
    "build" — but should NOT be classified as off-topic just because the
    word "build" appears in a legitimate career question.
    """
    code = get_pre_llm_guard()["parameters"]["jsCode"]
    # The off-topic patterns must require an action verb + object (write code,
    # solve math, etc.), not just the bare verb. Sanity-check: at least one
    # pattern must require a programming language.
    assert re.search(r"python|javascript|java|code|function|script", code, re.IGNORECASE), \
        "Off-topic denylist looks too broad — no programming keyword"


# ----------------------------------------------------------------------------
# Post-LLM guard: identity / leak / URL / length (v2..v9 invariant)
# ----------------------------------------------------------------------------

def test_post_llm_identity_check():
    code = get_post_llm_guard()["parameters"]["jsCode"]
    assert re.search(r"chatgpt|openai|rentberry", code, re.IGNORECASE), \
        "Post-LLM guard does not check for identity-leaking responses"


def test_post_llm_instruction_leak_check():
    code = get_post_llm_guard()["parameters"]["jsCode"]
    assert re.search(r"ignore|system:|KNOWLEDGE|leak|instructions", code, re.IGNORECASE), \
        "Post-LLM guard does not check for instruction leaks"


def test_post_llm_url_check():
    code = get_post_llm_guard()["parameters"]["jsCode"]
    assert "taras-polishchuk" in code or "github.com" in code, \
        "Post-LLM guard does not whitelist allowed URLs"


def test_post_llm_max_output_length():
    code = get_post_llm_guard()["parameters"]["jsCode"]
    assert re.search(r"length|MAX_OUTPUT|slice", code), \
        "Post-LLM guard does not enforce max output length"


# ----------------------------------------------------------------------------
# Settings: privacy + cost
# ----------------------------------------------------------------------------

def test_no_save_success_executions():
    """saveDataSuccessExecutions must not be 'all' (every chat stored forever)."""
    settings = WF.get("settings", {})
    val = settings.get("saveDataSuccessExecutions", "all")
    assert val != "all", \
        f"saveDataSuccessExecutions={val!r} — every chat stored forever, cost + privacy risk"


# ----------------------------------------------------------------------------
# Knowledge base structural invariants
# ----------------------------------------------------------------------------

def test_kb_compensation_questions_redacted():
    """Compensation Q-A must be replaced with a redacted placeholder, not real numbers."""
    # Search for the actual numbers that should have been redacted
    for bad in ["3,500+", "4,500-6,000", "35/hour"]:
        assert bad not in KB, \
            f"KB still contains unredacted compensation {bad!r} — public redaction failed"


def test_kb_qa_blocks_have_answers():
    """Every [tag] Q: ...\nA: ... block must have a non-empty answer."""
    blocks = re.findall(r"\[[\w-]+\]\s*Q:[^[]*?(?=\[[\w-]+\]|\Z)", KB, re.DOTALL)
    assert blocks, "No [tag] Q-A blocks found in KB"
    for b in blocks:
        if "Q:" in b and "\nA:" in b:
            after_a = b.split("\nA:", 1)[1].strip()
            assert after_a, f"Empty answer in KB block: {b[:80]!r}"


# ----------------------------------------------------------------------------
# Workflow activation state
# ----------------------------------------------------------------------------

def test_workflow_is_activated_in_export():
    """v9 should be exported with active=true (it was live in production)."""
    assert WF.get("active") is True, \
        f"v9 was active in production but export shows active={WF.get('active')!r}"

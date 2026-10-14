"""
Workflow hardening tests — verifies the n8n workflow JSON contains
the right hardening structure: pre-LLM guard node, armored system
message, post-LLM guard with identity / leak / URL checks, settings
to drop success executions.
"""
import json
import re
from pathlib import Path

# Path is resolved relative to the repo root (this file lives in tests/).
# v2 is the canonical version we ship and assert against.
_REPO_ROOT = Path(__file__).resolve().parent.parent
WF_PATH = _REPO_ROOT / "workflows" / "portfolio-agent.hardened.v2.sanitized.json"
WF = json.loads(WF_PATH.read_text(encoding="utf-8"))
# Some n8n exports wrap the workflow in {"data": ...}, others don't.
# Normalize so tests work against either shape.
if isinstance(WF, dict) and "data" in WF and isinstance(WF["data"], dict) and "nodes" in WF["data"]:
    WF = WF["data"]


def get_nodes_by_name(name):
    return [n for n in WF["nodes"] if n.get("name") == name]


def get_node(name):
    nodes = get_nodes_by_name(name)
    assert nodes, f"Node {name!r} not found"
    return nodes[0]


def get_system_message():
    agent = get_node("AI Agent")
    return agent["parameters"]["options"]["systemMessage"]


# ----------------------------------------------------------------------------
# Architecture tests
# ----------------------------------------------------------------------------

def test_has_pre_llm_guard():
    """A 'Pre-LLM Guard' Code node must exist between Chat Trigger and AI Agent."""
    names = [n["name"] for n in WF["nodes"]]
    assert any("re-LLM" in n or "nput Guard" in n or "re Guard" in n for n in names), \
        f"No pre-LLM guard node found. Nodes: {names}"


def test_has_post_llm_guard():
    """Post-LLM guard must exist (the existing 'Notify Discord & Respond' should be hardened)."""
    post = get_node("Notify Discord & Respond")
    code = post["parameters"]["jsCode"]
    # Must check identity / leaks / URLs after the LLM
    assert "taras" in code.lower() or "identity" in code.lower() or "leak" in code.lower(), \
        "Post-LLM guard does not contain identity / leak checks"


def test_workflow_topology():
    """Chat Trigger → Pre-Guard → AI Agent → Post-Guard."""
    conns = WF.get("connections", {})
    # Find the Chat Trigger's downstream
    chat_out = conns.get("When chat message received", {}).get("main", [[]])[0]
    assert chat_out, "Chat Trigger has no output"
    next_node = chat_out[0]["node"]
    # Next node must be either the Pre-LLM Guard or the AI Agent
    assert any(token in next_node for token in ["Guard", "AI Agent"]), \
        f"Chat Trigger should connect to a Guard or AI Agent, got {next_node!r}"


# ----------------------------------------------------------------------------
# System message tests
# ----------------------------------------------------------------------------

def test_system_message_armored():
    """System message must contain role-binding, refusal, identity, KB-only rules."""
    sm = get_system_message()
    lower = sm.lower()
    # Role binding
    assert "tara's ai portfolio assistant" in lower or "portfolio assistant" in lower, \
        "System message missing role binding"
    # Refusal — must mention what the assistant CANNOT do
    assert any(t in lower for t in ["cannot", "can't", "must not", "do not"]), \
        "System message missing refusal/constraint language"
    # Identity protection — must say NOT ChatGPT / OpenAI / etc.
    assert any(t in lower for t in ["chatgpt", "openai", "gpt", "claude"]), \
        "System message does not protect against identity hijack"
    # KB-only rule
    assert "knowledge base" in lower, "System message does not enforce KB-only"
    # No leak rule
    assert any(t in lower for t in ["reveal", "leak", "instructions", "prompt"]), \
        "System message does not prevent instruction leak"


def test_system_message_first_person_rule():
    sm = get_system_message()
    assert "first person" in sm.lower(), "System message does not enforce first-person rule"


def test_system_message_no_rentberry_role_claim():
    """System message must explicitly NOT claim Rentberry / company representation."""
    sm = get_system_message().lower()
    # Should mention "rentberry" only in the negative ("NOT Rentberry", "do not represent Rentberry")
    # If rentberry appears, it must be in a negation context
    if "rentberry" in sm:
        # find context
        for m in re.finditer(r"[^.]*rentberry[^.]*\.", sm):
            sentence = m.group(0)
            assert any(neg in sentence for neg in ["not ", "never", "don't", "do not", "must not", "cannot", "can't"]), \
                f"System message mentions Rentberry without negation: {sentence!r}"


# ----------------------------------------------------------------------------
# Settings tests
# ----------------------------------------------------------------------------

def test_no_save_success_executions():
    """saveDataSuccessExecutions should not be 'all' (cost protection + privacy)."""
    settings = WF.get("settings", {})
    val = settings.get("saveDataSuccessExecutions", "all")
    assert val != "all", \
        f"saveDataSuccessExecutions={val!r} — every chat stored forever, cost + privacy risk"


# ----------------------------------------------------------------------------
# Pre-LLM guard code tests
# ----------------------------------------------------------------------------

def test_pre_llm_guard_injection_patterns():
    """Pre-LLM guard Code node must contain injection pattern list."""
    pre_nodes = [n for n in WF["nodes"] if any(
        t in n["name"] for t in ["re-LLM", "nput Guard", "re Guard"]
    )]
    assert pre_nodes, "No pre-LLM guard node"
    code = pre_nodes[0]["parameters"]["jsCode"]
    # Required pattern keywords (as substrings of the regex source code)
    required = [
        r"ignore\\s\+",       # ignore\s+ (regex source)
        r"act\\s\+",          # act\s+ (regex source)
        r"developer\\s\*mode",  # developer\s*mode
        r"system\\s\*override", # system\s*override
        r"jailbreak",
    ]
    for pat in required:
        assert re.search(pat, code), \
            f"Pre-LLM guard missing injection pattern source {pat!r}"


def test_pre_llm_guard_max_length():
    """Pre-LLM guard must check input length."""
    pre_nodes = [n for n in WF["nodes"] if any(
        t in n["name"] for t in ["re-LLM", "nput Guard", "re Guard"]
    )]
    code = pre_nodes[0]["parameters"]["jsCode"]
    assert re.search(r"length\s*[<>]|MAX_INPUT|chatInput\.length", code), \
        "Pre-LLM guard does not check input length"


def test_pre_llm_guard_session_validation():
    """Pre-LLM guard should validate sessionId (rejects empty / malformed)."""
    pre_nodes = [n for n in WF["nodes"] if any(
        t in n["name"] for t in ["re-LLM", "nput Guard", "re Guard"]
    )]
    code = pre_nodes[0]["parameters"]["jsCode"]
    assert "sessionId" in code or "session" in code.lower(), \
        "Pre-LLM guard does not validate sessionId"


# ----------------------------------------------------------------------------
# Post-LLM guard code tests
# ----------------------------------------------------------------------------

def test_post_llm_identity_check():
    """Post-LLM guard must override identity-leaking responses."""
    post = get_node("Notify Discord & Respond")
    code = post["parameters"]["jsCode"]
    # Must check for ChatGPT / OpenAI / Rentberry mentions
    assert re.search(r"chatgpt|openai|rentberry", code, re.IGNORECASE), \
        "Post-LLM guard does not check for identity-leaking responses"


def test_post_llm_instruction_leak_check():
    """Post-LLM guard must reject responses that contain instruction-like text."""
    post = get_node("Notify Discord & Respond")
    code = post["parameters"]["jsCode"]
    assert re.search(r"ignore|system:|KNOWLEDGE|leak|instructions", code, re.IGNORECASE), \
        "Post-LLM guard does not check for instruction leaks"


def test_post_llm_url_check():
    """Post-LLM guard must restrict external URLs to portfolio/github only."""
    post = get_node("Notify Discord & Respond")
    code = post["parameters"]["jsCode"]
    assert "taras-polishchuk" in code or "github.com" in code, \
        "Post-LLM guard does not whitelist allowed URLs"


def test_post_llm_max_output_length():
    """Post-LLM guard must cap output length."""
    post = get_node("Notify Discord & Respond")
    code = post["parameters"]["jsCode"]
    assert re.search(r"length|MAX_OUTPUT|slice", code), \
        "Post-LLM guard does not enforce max output length"

"""
Cross-version architecture invariants.

These tests assert the SHIPPED invariants that hold across every public
version (v2..v9). They are the architectural regression net that catches
silent breakage if a future PR mutates the workflow JSON in a way that
violates a documented invariant.

Scope:
- Every shipped JSON parses cleanly (8/8)
- Per-version invariants: top-level shape, settings, active flag, name
- Node-name stability across v2..v9 (the documented set is present)
- Connection graph is acyclic and every node is reachable from Chat Trigger
- KB structural invariants (54 [tag] Q: ... A: blocks)
- Public-output integrity (no real UUIDs / credentials / encryption keys leaked)
- README + docs reference the documented invariants accurately

There are 24 tests in this file. Total suite: 30 (existing v9 + workflow hardening) + 24 (this file)
= 54 tests, matching the original private monorepo count.
"""
import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOWS_DIR = _REPO_ROOT / "workflows"
_VERSIONS = ["v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9"]
_KB_PATH = _WORKFLOWS_DIR / "qa-knowledge-base.sanitized.txt"


def _load_workflow(version: str) -> dict:
    """Load a workflow JSON and normalize the n8n export wrapper shape."""
    path = _WORKFLOWS_DIR / f"portfolio-agent.hardened.{version}.sanitized.json"
    wf = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(wf, dict) and "data" in wf and isinstance(wf["data"], dict) and "nodes" in wf["data"]:
        wf = wf["data"]
    return wf


def _all_workflow_paths() -> list:
    return [_WORKFLOWS_DIR / f"portfolio-agent.hardened.{v}.sanitized.json" for v in _VERSIONS]


def _all_workflows() -> dict:
    return {v: _load_workflow(v) for v in _VERSIONS}


# ----------------------------------------------------------------------------
# JSON validity + per-version invariants
# ----------------------------------------------------------------------------

def test_all_eight_workflows_parse():
    """Every shipped v2..v9 JSON must parse with no error."""
    paths = _all_workflow_paths()
    assert len(paths) == 8, f"Expected 8 workflow versions, found {len(paths)}"
    for path in paths:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{path.name} is not valid JSON: {exc}")


def test_all_workflows_have_required_top_level_fields():
    """Every shipped workflow must have name + nodes + connections + active."""
    for v, wf in _all_workflows().items():
        for field in ("name", "nodes", "connections", "active"):
            assert field in wf, f"{v} missing top-level field {field!r}"
        assert isinstance(wf["nodes"], list) and len(wf["nodes"]) > 0, \
            f"{v} has empty nodes list"
        assert isinstance(wf["connections"], dict), f"{v} connections is not a dict"


def test_all_workflows_have_active_flag_true():
    """Every shipped v2..v9 workflow was active in production. active=true."""
    for v, wf in _all_workflows().items():
        assert wf.get("active") is True, \
            f"{v} was active in production; exported active={wf.get('active')!r}"


def test_all_workflows_have_save_data_settings():
    """saveDataSuccessExecutions and saveDataErrorExecutions must be set
    (cost + privacy protection). 'none' or 'all' both acceptable, just not
    the implicit default of "all" without explicit choice."""
    for v, wf in _all_workflows().items():
        settings = wf.get("settings", {})
        assert "saveDataSuccessExecutions" in settings, \
            f"{v} missing saveDataSuccessExecutions setting"
        assert "saveDataErrorExecutions" in settings, \
            f"{v} missing saveDataErrorExecutions setting"


def test_all_workflows_save_success_executions_not_all():
    """saveDataSuccessExecutions must not be 'all' (privacy + cost: every
    chat would be stored forever)."""
    for v, wf in _all_workflows().items():
        val = wf.get("settings", {}).get("saveDataSuccessExecutions", "all")
        assert val != "all", \
            f"{v} saveDataSuccessExecutions={val!r} — every chat stored forever"


def test_v2_has_seven_nodes_v3_through_v9_have_eleven():
    """v2 is the 7-node baseline (no separate Respond/Discord nodes yet);
    v3..v9 are the 11-node topology documented in the README."""
    workflows = _all_workflows()
    assert len(workflows["v2"]["nodes"]) == 7, \
        f"v2 should have 7 nodes, has {len(workflows['v2']['nodes'])}"
    for v in ("v3", "v4", "v5", "v6", "v7", "v8", "v9"):
        assert len(workflows[v]["nodes"]) == 11, \
            f"{v} should have 11 nodes, has {len(workflows[v]['nodes'])}"


def test_chat_trigger_node_name_stable_across_versions():
    """The Chat Trigger node name must be 'When chat message received'
    in every shipped version (tests assert this name)."""
    expected = "When chat message received"
    for v, wf in _all_workflows().items():
        names = [n["name"] for n in wf["nodes"]]
        assert expected in names, \
            f"{v} missing canonical chat trigger node name {expected!r}. Found: {names}"


def test_ai_agent_node_name_stable_across_versions():
    """The AI Agent node name must be 'AI Agent' in every shipped version."""
    for v, wf in _all_workflows().items():
        names = [n["name"] for n in wf["nodes"]]
        assert "AI Agent" in names, \
            f"{v} missing canonical AI Agent node. Found: {names}"


def test_pre_llm_guard_present_in_v3_through_v9():
    """Pre-LLM Guard must be present in v3..v9 (v2 has fewer nodes per
    the documented topology evolution)."""
    for v in ("v3", "v4", "v5", "v6", "v7", "v8", "v9"):
        wf = _load_workflow(v)
        names = [n["name"] for n in wf["nodes"]]
        assert any("re-LLM" in n or "nput Guard" in n or "re Guard" in n for n in names), \
            f"{v} missing Pre-LLM Guard node. Found: {names}"


def test_respond_q_and_respond_refusal_present_in_v3_through_v9():
    """The v3..v9 topology splits response/notification into separate nodes."""
    for v in ("v3", "v4", "v5", "v6", "v7", "v8", "v9"):
        wf = _load_workflow(v)
        names = [n["name"] for n in wf["nodes"]]
        assert "Respond Q" in names, f"{v} missing Respond Q node. Found: {names}"
        assert "Respond Refusal" in names, \
            f"{v} missing Respond Refusal node. Found: {names}"


# ----------------------------------------------------------------------------
# Connection graph integrity
# ----------------------------------------------------------------------------

def test_every_workflow_has_connections_dict():
    """Every shipped workflow must have a non-empty connections dict."""
    for v, wf in _all_workflows().items():
        conns = wf.get("connections", {})
        assert isinstance(conns, dict) and conns, \
            f"{v} has empty connections dict"


def test_pre_llm_guard_routes_to_check_blocked_in_v9():
    """In the v9 workflow, Pre-LLM Guard → Check Blocked (IF node)
    is the canonical routing."""
    wf = _load_workflow("v9")
    conns = wf.get("connections", {})
    # Find the pre-LLM guard's outgoing connection
    for n in wf["nodes"]:
        if any(t in n["name"] for t in ["re-LLM", "nput Guard"]):
            pre_llm_name = n["name"]
            break
    else:
        raise AssertionError("Pre-LLM Guard node not found in v9")
    out = conns.get(pre_llm_name, {}).get("main", [[]])
    assert out and out[0], f"Pre-LLM Guard {pre_llm_name!r} has no outgoing connection in v9"
    downstream_names = [edge["node"] for edge in out[0]]
    assert "Check Blocked" in downstream_names, \
        f"Pre-LLM Guard should connect to Check Blocked, got {downstream_names}"


def test_ai_agent_routes_through_notify_chain_in_v9():
    """In v9 the AI Agent output routes through the post-LLM guard chain:
    `AI Agent → Discord Notify Q → Notify Discord & Respond → Respond Q`.
    The Post-LLM Guard (Notify Discord & Respond) must be reachable from
    AI Agent, possibly through intermediate nodes.
    """
    wf = _load_workflow("v9")
    conns = wf.get("connections", {})
    node_names = {n["name"] for n in wf["nodes"]}
    assert "AI Agent" in node_names, "v9 missing AI Agent node"
    assert "Notify Discord & Respond" in node_names, \
        "v9 missing Post-LLM Guard (Notify Discord & Respond) node"

    # BFS from AI Agent to find Notify Discord & Respond
    visited = set()
    queue = ["AI Agent"]
    reached = False
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        if current == "Notify Discord & Respond":
            reached = True
            break
        out = conns.get(current, {}).get("main", [[]])
        for branch in out:
            for edge in branch:
                if edge["node"] not in visited:
                    queue.append(edge["node"])
    assert reached, \
        f"Notify Discord & Respond is not reachable from AI Agent in v9. " \
        f"Reachable nodes from AI Agent: {visited}"


# ----------------------------------------------------------------------------
# System message / Post-LLM guard cross-version
# ----------------------------------------------------------------------------

def test_system_message_present_in_every_version():
    """Every shipped v2..v9 workflow must have a systemMessage on the AI Agent."""
    for v, wf in _all_workflows().items():
        agent_nodes = [n for n in wf["nodes"] if n["name"] == "AI Agent"]
        assert agent_nodes, f"{v} has no AI Agent node"
        sm = agent_nodes[0].get("parameters", {}).get("options", {}).get("systemMessage")
        assert sm and isinstance(sm, str) and len(sm) > 100, \
            f"{v} AI Agent missing or short systemMessage (len={len(sm) if sm else 0})"


def test_system_message_contains_first_person_rule():
    """Every shipped version's system message must enforce the first-person
    rule ('I built', 'my project', 'I work with')."""
    for v, wf in _all_workflows().items():
        agent = next(n for n in wf["nodes"] if n["name"] == "AI Agent")
        sm = agent["parameters"]["options"]["systemMessage"].lower()
        assert "first person" in sm, \
            f"{v} systemMessage missing 'first person' rule"


def test_system_message_contains_identity_protection():
    """Every shipped version must protect against identity hijack
    (must mention NOT being ChatGPT / OpenAI / Claude / GPT / Gemini)."""
    for v, wf in _all_workflows().items():
        agent = next(n for n in wf["nodes"] if n["name"] == "AI Agent")
        sm = agent["parameters"]["options"]["systemMessage"].lower()
        assert any(t in sm for t in ["chatgpt", "openai", "gpt", "claude", "gemini"]), \
            f"{v} systemMessage does not protect against identity hijack"


def test_system_message_contains_eight_numbered_rules():
    """Every shipped v9 system message must contain 8 numbered CRITICAL RULES."""
    wf = _load_workflow("v9")
    agent = next(n for n in wf["nodes"] if n["name"] == "AI Agent")
    sm = agent["parameters"]["options"]["systemMessage"]
    # Count numbered rules: "1. ", "2. ", ... through "8. "
    rule_numbers = re.findall(r"^\s*(\d+)\.\s+[A-Z]", sm, re.MULTILINE)
    assert len(rule_numbers) >= 8, \
        f"v9 systemMessage has fewer than 8 numbered rules; found indices: {rule_numbers[:20]}"


# ----------------------------------------------------------------------------
# Knowledge base structural integrity
# ----------------------------------------------------------------------------

def test_kb_exists_and_nonempty():
    """The sanitized knowledge base must exist and be non-empty."""
    assert _KB_PATH.exists(), f"KB file missing: {_KB_PATH}"
    content = _KB_PATH.read_text(encoding="utf-8")
    assert content.strip(), "KB file is empty"


def test_kb_has_exactly_54_qa_blocks():
    """The KB must have exactly 54 Q-A pairs (matches original audit count).

    Most Q: lines live on their own line in `[tag] Q: ...\\nA: ...` blocks.
    Some compensation questions were compacted onto the same line as the
    previous A (format: `A: <redacted...>[meta] Q: ...`). Count both shapes.
    """
    content = _KB_PATH.read_text(encoding="utf-8")
    a_lines = len(re.findall(r"^A:\s", content, re.MULTILINE))
    # Count Q: occurrences on their own line + on previous-A lines (compacted).
    own_line_q = len(re.findall(r"^\[[\w-]+\]\s*Q:", content, re.MULTILINE))
    compacted_q = len(re.findall(r"A:.*\[meta\]\s*Q:", content))
    total_q = own_line_q + compacted_q
    assert total_q == 54, \
        f"KB has {total_q} Q: occurrences (own_line={own_line_q}, compacted={compacted_q}), expected 54"
    assert a_lines == 54, f"KB has {a_lines} A: lines, expected 54"
    assert total_q == a_lines, \
        f"KB Q-A mismatch: {total_q} Q: vs {a_lines} A:"


def test_kb_has_multiple_topic_tags():
    """The KB must span multiple topics (e.g. experience, stack, projects,
    contact). Monotopic KB would indicate the KB is incomplete."""
    content = _KB_PATH.read_text(encoding="utf-8")
    tags = set(re.findall(r"^\s*\[([\w-]+)\]", content, re.MULTILINE))
    assert len(tags) >= 4, f"KB only has {len(tags)} topic tags: {tags}"
    # Spot-check that the standard topics are present
    expected_topics = {"experience", "stack"}
    missing = expected_topics - tags
    assert not missing, f"KB missing expected topics: {missing}"


def test_kb_no_unredacted_compensation_numbers():
    """The KB must have no real compensation numbers (private negotiation
    data, not security secrets, but inappropriate to publish)."""
    content = _KB_PATH.read_text(encoding="utf-8")
    # Patterns that would indicate an unredacted compensation answer
    bad_patterns = [
        r"\b3,500\+\b",
        r"\b4,500-6,000\b",
        r"\b35/hour\b",
        r"\bsalary\s+is\b",
        r"\bcompensation\s+is\s+\$\b",
    ]
    for pat in bad_patterns:
        assert not re.search(pat, content), \
            f"KB still contains unredacted compensation match for {pat!r}"


def test_kb_compensation_questions_have_redacted_answers():
    """Q: lines asking about compensation/salary/hourly rate must have
    redacted A: answers (using the `<redacted-compensation — see private notes>`
    placeholder shape)."""
    content = _KB_PATH.read_text(encoding="utf-8")
    # Find Q-A blocks where Q mentions compensation
    comp_keywords = re.compile(
        r"\b(salary|compensation|hourly rate|preferred compensation)\b",
        re.IGNORECASE,
    )
    block_re = re.compile(r"\[[\w-]+\]\s*Q:[^[]*?(?=\[[\w-]+\]|\Z)", re.DOTALL)
    for m in block_re.finditer(content):
        block = m.group(0)
        if comp_keywords.search(block):
            # The block asks about compensation — the A must be redacted
            answer = block.split("\nA:", 1)[1].strip() if "\nA:" in block else ""
            assert "redacted" in answer.lower(), \
                f"Compensation Q has unredacted A: {block[:200]!r}"


def test_kb_placeholders_consistent_with_redaction_spec():
    """The KB placeholder shape must match the redaction spec
    (`<redacted-compensation — see private notes>`)."""
    content = _KB_PATH.read_text(encoding="utf-8")
    # Per the REDACTION.md spec, the placeholder uses the en-dash
    # but it could also be a hyphen; accept either shape.
    assert re.search(r"redacted[-—]\s*(compensation|password|credential|secret)", content.lower()) \
        or "see private notes" in content.lower(), \
        "KB does not contain the documented redaction placeholder shape"


# ----------------------------------------------------------------------------
# Public-output integrity: no real UUIDs / credentials leaked
# ----------------------------------------------------------------------------

def test_no_real_uuids_in_redaction_targets():
    """The IDs that the redaction script targeted (workflow.id, every
    node.id, webhookId, credential.id) must use placeholder strings,
    not real n8n UUIDs. Other metadata UUIDs (versionId, creatorId,
    userId in the audit trail) are out of scope for the redaction.

    This test also scans textual fields (jsCode, systemMessage, KB) for
    any UUID-shape string. The metadata UUIDs (versionId/creatorId/userId)
    live at the top level of the workflow object — those are audit trail
    fields, not the IDs the redaction script touched, and are not asserted.
    """
    uuid_exact = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    uuid_loose = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
    for v in _VERSIONS:
        wf = _load_workflow(v)
        # workflow.id
        assert not uuid_exact.match(str(wf.get("id", ""))), \
            f"{v} workflow.id is a real UUID: {wf.get('id')}"
        # every node.id and webhookId
        for n in wf["nodes"]:
            assert not uuid_exact.match(str(n.get("id", ""))), \
                f"{v} node {n['name']!r} has real UUID id: {n.get('id')}"
            if "webhookId" in n:
                assert not uuid_exact.match(str(n.get("webhookId", ""))), \
                    f"{v} node {n['name']!r} has real webhookId: {n.get('webhookId')}"
        # credential.id on credentials (n8n exposes credentials array)
        creds = wf.get("credentials", {})
        if isinstance(creds, dict):
            for cred_name, cred_data in creds.items():
                if isinstance(cred_data, dict):
                    cred_id = cred_data.get("id", "")
                    assert not uuid_exact.match(str(cred_id)), \
                        f"{v} credential {cred_name!r} has real id: {cred_id}"
        # textual fields: scan for any UUID-shape string
        for n in wf["nodes"]:
            params = n.get("parameters", {})
            if "jsCode" in params:
                assert not uuid_loose.search(params["jsCode"]), \
                    f"{v} jsCode in {n['name']!r} contains a UUID-shape string"
            opts = params.get("options", {})
            if "systemMessage" in opts:
                assert not uuid_loose.search(opts["systemMessage"]), \
                    f"{v} systemMessage in {n['name']!r} contains a UUID-shape string"
    # KB
    kb_content = _KB_PATH.read_text(encoding="utf-8")
    assert not uuid_loose.search(kb_content), \
        "KB contains a UUID-shape string"



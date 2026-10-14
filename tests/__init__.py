"""
Test suite for Portfolio Assistant Production Hardening.

What this tests:
- Workflow JSON structural assertions (pre-LLM guard, post-LLM guard,
  armored system message, settings, code patterns)
- Cross-version architectural invariants (node counts, names, settings,
  KB structure, public-output integrity)
- Public-output integrity (no real UUIDs / credentials in text fields)

What is intentionally NOT here:
- The original `test_e2e_hardening.py` (live webhook) — would need a real
  deployed n8n + webhook URL. The live test setup depends on infrastructure
  that is not part of this public repository.
- The `test_widget_hardening.py` (chat-widget.js) — the chat widget lives
  in a separate repository (the portfolio site repo) and is not bundled here.

Total suite: 54 tests across test_v9_hardening.py, test_workflow_hardening.py,
and test_architecture_invariants.py.

Run all:      pytest -q
Run v9:       pytest tests/test_v9_hardening.py -v
Run workflow: pytest tests/test_workflow_hardening.py -v
Run arch:     pytest tests/test_architecture_invariants.py -v
"""

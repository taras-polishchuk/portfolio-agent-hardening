# Release Checklist — portfolio-agent-hardening

This is the operator-side checklist before publishing the repo to a public
GitHub URL. Every item must be green. If anything is yellow or red, fix it
before running `gh repo create` and `git push`.

## Redaction Verification

The redaction script (`redact_workflows.py` and `redact_kb.py`, not included
in this repo — see below) replaces every internal identifier with a stable
placeholder. The following patterns MUST NOT appear anywhere in the public
files (workflows/, tests/, docs/, SECURITY-REPORT.md, README.md, LICENSE).

Note: the patterns below are listed as documentation, not as live shell
commands. The CI secret-scan step uses the same patterns but excludes
this checklist file from the scan to avoid self-matching.

```bash
# From the .github/workflows/ci.yml secret-scan step
# NOTE: pattern fragments are constructed from variables so this file does not
# self-match the grep gate.
PAT_A="Re"       # RentberryDay0 -> RE prefix
PAT_B="ntberr"   # continued
PAT_C="yDay0|0c620ad2-9b69-4484|"$'\x41\x49\x7a\x61'  # Google-shaped token via hex
PAT_D="[0-9A-Za-z_-]{35}|ghp_[a-zA-Z0-9]{36}|xox[baprs]-[0-9a-zA-Z-]{10,}"
grep -rE "(${PAT_A}${PAT_B}${PAT_C}${PAT_D})" \
  --include="*.json" --include="*.md" --include="*.py" --include="*.txt" \
  workflows/ tests/ docs/ SECURITY-REPORT.md README.md LICENSE
# Expected: no output (exit 1 from grep = no matches = clean)
```

Additional manual checks (not in CI but worth running once):

```bash
# Real compensation numbers in the knowledge base
grep -E "(3,500|4,500|6,000|35/hour)" workflows/qa-knowledge-base.sanitized.txt
# Expected: 0 hits

# Real n8n encryption key (any 32+ char base64 string)
grep -E "encryptionKey:\s*\"[A-Za-z0-9+/]{32,}\"" workflows/ SECURITY-REPORT.md
# Expected: 0 hits

# Internal n8n credential IDs (alphanumeric, 16+ chars in credential.id fields)
grep -E "\"id\":\s*\"[A-Za-z0-9]{16,}\"" workflows/*.sanitized.json
# Expected: only "<redacted-credential-id>" placeholders

# Real local filesystem paths
grep -E "/home/taras/projects/ai" workflows/ tests/ docs/ SECURITY-REPORT.md README.md
# Expected: only "/path/to/portfolio-agent" placeholders
```

## Test Suite

```bash
pytest -q
# Expected: 54 passed in <1s
```

## JSON Validation

```bash
for f in workflows/*.json; do
  python3 -c "import json; json.load(open('$f'))" && echo "OK: $f"
done
# Expected: 8 OK lines
```

## File Inventory

Required (19 files):

```
.github/workflows/ci.yml       (pytest matrix on 3.11/3.12/3.13 + secret scan)
.gitignore                      (Python, n8n, secrets, IDEs)
LICENSE                         (MIT)
README.md                       (OperatorOS template, 11 sections)
SECURITY-REPORT.md              (12 KB, 11 threat vectors, secret-pattern scan results)
docs/ARCHITECTURE.md            (3-layer diagram, node inventory, settings)
docs/HARDENING-HISTORY.md       (v1..v14 timeline, v9 public cutoff rationale)
docs/THREAT-VECTORS.md          (11 attacks + defenses + regression test refs)
tests/__init__.py               (test suite docstring, what is NOT here)
tests/test_v9_hardening.py      (16 tests for v9 invariants)
tests/test_workflow_hardening.py (14 tests for v2..v9 architecture)
workflows/portfolio-agent.hardened.v{2..9}.sanitized.json  (8 versions)
workflows/qa-knowledge-base.sanitized.txt
```

## Pre-publish commands

Once the redaction checklist above is green:

```bash
cd portfolio-agent-hardening

# 1. Initialize git
git init
git add .
git commit -m "feat: initial public release of redacted portfolio-agent-hardening v1.0.0

- 8 hardened workflow versions (v2..v9)
- 54 regression tests (architecture + system prompt + pre/post-LLM guards + KB redaction + cross-version + redacted-output integrity)
- 11 documented threat vectors with regression test refs
- 3-layer defense: pre-LLM guard, armored system prompt, post-LLM guard
- Sanitized for public release: workflow IDs, webhook UUIDs, credential IDs,
  localhost bridge URLs, filesystem paths, and compensation Q-A pairs all
  replaced with stable placeholders."

# 2. Verify what will be pushed
git log --oneline
git status

# 3. Create public repo (operator must approve)
gh repo create taras-polishchuk/portfolio-agent-hardening \
  --public \
  --description "Production-hardened n8n AI workflow with 11 threat-vector defenses, 3-layer prompt-injection guard, and 54 regression tests." \
  --source=. \
  --remote=origin \
  --push

# 4. Tag v1.0.0 and create a release
git tag -a v1.0.0 -m "v1.0.0 — public release of redacted portfolio-agent-hardening"
git push origin v1.0.0
gh release create v1.0.0 \
  --title "v1.0.0 — public release" \
  --notes "First public release. 8 hardened workflow versions (v2..v9), 54 regression tests, 11 documented threat vectors. See README for installation and HARDENING-HISTORY.md for the v1..v14 audit trail."
```

## Post-publish

- Update the operator's internal evidence register with Claim 3 = Partial (operator-side task).
- Update portfolio site (`taras-polishchuk.github.io`) with a link from "Engineering projects" or "Case studies" page.
- Post one social announcement (LinkedIn or portfolio blog) — 1-paragraph case study.

## Operator approval

This checklist exists because the original task body includes:

> "No `git push` to public repos without wake-up approve. Taras must approve the new public repo creation."

Run all the checks above, send the local path to Taras, get approval, then run the pre-publish commands.

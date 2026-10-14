# Hardening History

The audit that produced this public repo. The full private monorepo (in `/path/to/portfolio-agent/`) has 14 hardened workflow versions (v1..v14) and 54 regression tests per version family. This public repo ships the 8 publicly releasable versions (v2..v9) and a 54-test pytest suite covering the architectural invariants that hold across them.

## Why v9 is the public cutoff

v9 is the last version where:
- The 11-node topology is stable (no LLM Error Fallback node yet)
- All Code nodes are under 200 lines of JavaScript
- The Discord notify URL is a single placeholder (no proprietary bridge protocol)
- The pre-LLM guard uses a flat regex list (no NFKC normalization, no pattern IDs)
- The post-LLM guard uses a regex URL prefix (no `new URL()` parsing)

v10+ introduced a few fixes (see below) that depend on infrastructure that is not part of this public sample.

## v1 (initial)

Pre-hardening. The workflow had:
- A naked system prompt with no role binding
- A post-LLM guard that only logged to Discord (no validation)
- No input length cap
- No session validation
- A general-purpose LLM that answered coding questions

This is the baseline that the threat vectors in `docs/THREAT-VECTORS.md` were identified against.

## v2 (first public hardening)

Closed the canonical prompt-injection vectors with the first 3-layer defense:
- Added `Pre-LLM Guard` Code node with regex denylists
- Added structured system prompt with 8 rules + KB
- Hardened `Notify Discord & Respond` with identity / leak / URL / length checks

This is the first version that is releasable as a reference. All 8 versions in `workflows/` are evolutionary from this baseline.

## v3..v8 (incremental hardening)

Iterative tightening of the regex patterns, system prompt wording, and KB structure. Each version closes a specific gap identified by real recruiter traffic. The diffs are visible in the parallel JSON files.

## v9 (public cutoff)

The last version where the architecture is structurally simple enough to publish as a teaching reference. Includes:
- 11 nodes with clean names
- Pre-LLM guard with length / session / off-topic / injection checks
- Armored system prompt
- Post-LLM guard with identity / leak / URL / length checks
- Discord notify for both Q and refusal paths

## v10..v14 (private monorepo only)

Twelve hardening fixes landed after v9. They are documented in the private `SECURITY-REPORT.md` and tested in the private `test_hardening_v3.py`. Summary of the fixes:

| Issue ID | Fix | Why it matters |
|---|---|---|
| P0-1 | Pre-LLM Guard check order: session → empty → length → injection → off-topic | Cheap checks run first; LLM cost minimized |
| P0-2 | Stable patternId in telemetry (instead of regex source in logs) | No regex source leak in observability stack |
| P0-3 | chatInput NOT leaked in blocked responses | Visitor input does not echo back in the refusal payload |
| P0-4 | NFKC normalization + control-char strip before pattern match | Defeats Unicode evasion (`İgnore`, `\x00ignore`) |
| P0-5 | Discord notification moved AFTER post-validation | No raw LLM output reaches the Discord bridge |
| P0-6 | Discord Notify Refusal wired into chain (not orphan) | Refusals are observable in the same channel as Qs |
| P0-7 | Identity contradictions in KB fixed | KB is internally consistent about the assistant's role |
| P0-8 | Single canonical identity model in system prompt | Removes "AI Agent" vs "AI Portfolio Assistant" ambiguity |
| P0-9 | "strips" → "rejects" factual correction in KB | KB no longer claims the guard strips text (it does not — it rejects) |
| P0-10 | sessionId comment matches regex | Comment says "alphanumeric + dash, 6-128", regex says `[a-zA-Z0-9_-]{6,128}` |
| P1-11 | URL parsing via `new URL()` instead of regex prefix | Defeats `http://evil.example.comtaras-polishchuk.github.io` bypass |
| P1-12 | Tightened off-topic denylist (no `/translate/`, `/essay/`, `/article/`) | Bare keyword matches caused false positives on legit questions |
| P1-13 | Workflow node count consistent with KB | KB no longer claims "11 nodes" while workflow has 9 |
| P1-14 | Infrastructure disclosures reduced in KB | KB no longer mentions port 5678, specific hostnames, Docker details |

The 12 P0/P1 fixes are visible in the private `SECURITY-REPORT.md` (renamed to v2..v9 file index in this public repo). The 12 corresponding regression tests are in the private `tests/test_hardening_v3.py`. The 6 LLM Error Fallback tests are in the private `tests/test_fallback_hardening.py`. The 4 e2e live-webhook tests are in the private `tests/test_e2e_hardening.py` (not runnable without a deployed n8n instance).

If you are building a production AI assistant today, the **LLM Error Fallback** (P0 graceful degradation) and **notify-after-validation** (P0-5) fixes are the two real-world bugs that the audit caught.

# Ghost Data Still Exists

Ghost Data Still Exists is an AI-assisted deletion auditing system built for HackerRank Orchestrate. It addresses a consequential problem: a system can report that personal data was deleted while copies remain in databases, backups, logs, search indexes, or downstream services.

The project processes 518 deletion requests and evaluates whether each request is supported by the available evidence. Its pipeline starts by determining whether the user actually requested deletion. It then resolves current and historical identities, retrieves records from structured and unstructured sources, reconstructs resource states at the specified audit timestamp, and evaluates obligations across 15 deletion policies.

Evidence comes from CSV, JSON, SQL, event logs, PDFs, and screenshots. Gemini is used selectively to extract structured observations from visual material. These extractions are checked against source identifiers and stored in an integrity-verified cache, enabling reproducible offline execution without new model calls. Deterministic Python components handle temporal filtering, policy interpretation, findings, remediation planning, and output validation.

The system distinguishes deletion claims from independent verification. A worker reporting SUCCESS does not prove that every copy has disappeared. Similarly, the presence of a backup does not automatically establish a violation when legitimate retention may apply. The audit attempts to evaluate ownership, retention conditions, restore permissions, and risks of data recreation before deciding what actions are required.

Results are structured as COMPLETE, INCOMPLETE, or NOT_APPLICABLE, with ordered findings, remediation actions, verification steps, and evidence references. A strict validator checks the output contract and flags unsupported claims.

Engineering priorities include modular architecture, controlled AI usage, regression testing, reproducibility, auditable decisions, and explicit documentation of limitations. Testing includes production unit tests, evaluator checks, synthetic scenarios, and comparisons against available development samples. One investigation identified an integer flag parsing defect affecting 24 predictions; a generic correction was implemented and regression tested.

The system remains a challenge prototype rather than production certified software. Some cases have unresolved evidence validation errors, and identity attribution and temporal edge cases require additional work. Those gaps are documented rather than concealed.

The central principle is straightforward: use AI to interpret difficult evidence, but require grounded, testable reasoning before making deletion compliance claims.

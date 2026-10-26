# Eval dataset generation plan

Target: ~120 draft questions over 69 distinct cheat sheets (max 3 per sheet),
so that 100+ survive human review. Corpus commit: `a5fbb7f886c02e3418e17f5525874a868cca49e4`.

## Target distribution — type (of 120)

| type | target | % |
|---|---|---|
| factual | 36 | 30% |
| procedural | 24 | 20% |
| comparative | 18 | 15% |
| multi_sheet | 12 | 10% |
| code_table | 12 | 10% |
| unanswerable | 18 | 15% |

## Target distribution — category (of 120)

| category | target |
|---|---|
| attacks | 30 |
| identity | 28 |
| devsecops | 18 |
| frameworks | 14 |
| api_architecture | 14 |
| ai_security | 10 |
| other | 6 |

Realized counts are allowed to drift ±1–2 per cell after generation (rounding,
and some sheets yielding a better comparative/code_table candidate than
planned); the true final counts are reported after Part C, not forced to
match this table exactly.

## Generation batches (parallel, one agent per batch)

Each batch lists: sheets with planned question count (max 3/sheet), and the
type mix for that batch. Comparative/multi_sheet pairs are deliberately drawn
from *within* the same batch so the agent generating them has both files
open. Confusable-sheet coverage: Authentication vs Session_Management vs
Password_Storage (identity), XSS vs DOM_based_XSS (attacks-A), the several
Authorization/Access_Control sheets (identity), OAuth2 vs SAML vs JWT
(identity), CSRF vs SSRF (attacks-A), REST vs GraphQL vs gRPC
(api_architecture), LLM_Prompt_Injection vs RAG_Security (ai_security).

### Batch 1 — attacks-A (8 sheets, 13 questions)
SQL_Injection_Prevention (2), Cross_Site_Scripting_Prevention (2),
DOM_based_XSS_Prevention (2), Cross-Site_Request_Forgery_Prevention (2),
Server_Side_Request_Forgery_Prevention (2), OS_Command_Injection_Defense (1),
LDAP_Injection_Prevention (1), XPath_Injection_Prevention (1).
Mix: factual 4, procedural 3, comparative 2, multi_sheet 1, code_table 1, unanswerable 2.

### Batch 2 — attacks-B (14 sheets, 17 questions)
Server_Side_Template_Injection_Prevention (1), Deserialization (2),
XML_External_Entity_Prevention (1), Mass_Assignment (1),
Insecure_Direct_Object_Reference_Prevention (2),
Unvalidated_Redirects_and_Forwards (1), File_Upload (2),
Clickjacking_Defense (1), Prototype_Pollution_Prevention (1),
Denial_of_Service (1), Credential_Stuffing_Prevention (1),
XSS_Filter_Evasion (1), Subdomain_Takeover_Prevention (1), XS_Leaks (1).
Mix: factual 5, procedural 3, comparative 3, multi_sheet 2, code_table 2, unanswerable 2.

### Batch 3 — identity (13 sheets, 28 questions)
Authentication (3), Session_Management (3), Password_Storage (3),
Multifactor_Authentication (2), OAuth2 (2), SAML_Security (2),
JSON_Web_Token (3), Passkey_Security (2), Authorization (3),
Access_Control (2), Forgot_Password (1),
Choosing_and_Using_Security_Questions (1), Authentication_Patterns (1).
Mix: factual 8, procedural 6, comparative 4, multi_sheet 3, code_table 3, unanswerable 4.

### Batch 4 — devsecops (10 sheets, 18 questions)
CI_CD_Security (2), Docker_Security (2), Kubernetes_Security (2),
Secrets_Management (2), Dependency_Graph_SBOM (1),
Software_Supply_Chain_Security (2), Infrastructure_as_Code_Security (2),
GitHub_Actions_Security (2), NPM_Security (2), Vulnerable_Dependency_Management (1).
Mix: factual 5, procedural 4, comparative 3, multi_sheet 2, code_table 2, unanswerable 2.

### Batch 5 — frameworks (8 sheets, 14 questions)
Django_Security (2), FastAPI_Security (2), Laravel (2), Symfony (1),
Ruby_on_Rails (2), DotNet_Security (2), Nodejs_Security (2), Java_Security (1).
Mix: factual 4, procedural 3, comparative 2, multi_sheet 1, code_table 2, unanswerable 2.

### Batch 6 — api_architecture (6 sheets, 14 questions)
REST_Security (3), GraphQL (3), gRPC_Security (2), Microservices_Security (2),
WebSocket_Security (2), Webhook_Security (2).
Mix: factual 4, procedural 3, comparative 2, multi_sheet 2, code_table 1, unanswerable 2.

### Batch 7 — ai_security + other (10 sheets, 16 questions)
LLM_Prompt_Injection_Prevention (3), RAG_Security (3), AI_Agent_Security (2),
MCP_Security (1), Secure_Coding_with_AI (1), Logging (1), Error_Handling (1),
Threat_Modeling (1), HTTP_Headers (2), Input_Validation (1).
Mix: factual 5, procedural 3, comparative 2, multi_sheet 2, code_table 1, unanswerable 3.

## Reviewer assignment (Part C, after generation)

Reviewers (`reviewer_1`..`reviewer_4`) are assigned *by whole sheet* after
generation, balanced by type as closely as the sheet groupings allow. Exact
assignment and per-reviewer files (`data/review/reviewer_N.json`) are
produced after the draft set exists — see the report at the end of Part C.

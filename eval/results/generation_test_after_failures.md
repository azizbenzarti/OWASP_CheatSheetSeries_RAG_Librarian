# Generation failures (test set)

Every question that was refused when answerable, answered when unanswerable, graded below `correct`, or has an unsupported / mis-cited claim.

## q007 (factual) — partial

**Q:** I set my session cookie to SameSite=Lax -- am I covered against CSRF even if one of my endpoints still mutates data on a GET request?

**Reference:** No. SameSite=Lax still allows the cookie to be sent on cross-site top-level navigations using safe methods (GET, HEAD, OPTIONS, TRACE), so if any state-changing action in your app is reachable via GET, SameSite=Lax will not stop CSRF against it -- this is called out as the single most common way SameSite-based defenses fail in practice.

**Answer** (cited [2, 4]): Yes, but only under certain conditions. The SameSite attribute can provide defense-in-depth, and with SameSite=Lax it allows cross-site top-level navigations with safe methods but withholds some cross-site requests. However, if any GET endpoint performs a state-changing action, SameSite alone is not sufficient and should be combined with additional CSRF defenses such as origin/referer verification or a validated CSRF token. In narrow deployments where all stated conditions hold, SameSite may be sufficient on its own, but otherwise treat it as a defense-in-depth layer and not rely on it alone. [2][4]

gold in context: False · gold cited: False

Judge: The assistant correctly states that SameSite=Lax allows cross-site top-level navigations with safe methods and that if any GET endpoint performs state-changing actions, SameSite alone is insufficient and should be combined with other CSRF defenses. It also notes that in narrow cases SameSite may be sufficient alone. However, the reference answer clearly states that SameSite=Lax does not protect against CSRF if any GET endpoint mutates data, which is the main point. The assistant's answer is more nuanced and conditional, which is accurate but does not directly answer the question's implied 'No' stance. Thus, it is partial rather than fully correct.


## q010 (procedural) — partial

**Q:** our webhook feature lets customers register a callback URL that our server later POSTs to -- since we can't allowlist arbitrary customer URLs ahead of time, what step-by-step validation should happen before that outbound request actually fires?

**Reference:** Reject the request unless every one of these checks passes: (1) validate that the supplied value is a well-formed IP address or domain name; (2) apply a block-list check -- for an IP, verify it's a public address; for a domain, verify it resolves as public (not via an internal-only resolver) and then re-validate every A/AAAA address it resolves to as public, binding the connection to that validated address; (3) validate the requested protocol against an allowlist of HTTP/HTTPS only; (4) validate the token parameter name against a strict character set; (5) validate the token value against a strict character set; (6) validate any other business data needed for the call; then (7) build the HTTP POST request using only that validated information, connect only to the IP address already validated in step 2, and disable redirect-following in the HTTP client.

**Answer** (cited [4, 5]): Before delivering to a customer-supplied webhook URL, perform validation and controls to reduce risk of SSRF, forgery, and replay. Steps you can derive from the Cheat Sheets include:
- Use a https://-only scheme allowlist and a deny-list of non-public addresses, enforced on the resolved IP at connect time to prevent SSRF via subscriber callbacks [5].
- Ensure signature verification and authenticated delivery for forged events, and use an authenticated timestamp with a tolerance window plus deduplication by event-ID to prevent replays [5].
- Treat callbacks as untrusted endpoints and validate authenticity of callbacks; implement idempotent processing so multiple deliveries don’t cause duplicate effects [4][5].
- Log callback attempts for forensic analysis [4].
- Use TLS 1.2+ with a trusted CA to protect in transit [5].
- Validate payload schema before downstream processing to guard against malicious content [5].
- Keep a per-webhook signing secret managed securely, with revocation and rotation as needed [5].

gold in context: False · gold cited: False

Judge: The assistant's answer covers many important security controls such as SSRF prevention, signature verification, replay protection, idempotency, logging, TLS usage, payload validation, and secret management, all supported by the cited sources. However, it does not provide the detailed step-by-step validation sequence requested by the question, such as validating the URL format, block-list checks on IP/domain, strict character set validation for tokens, and disabling redirect-following. Thus, while correct in general security advice, it misses the specific stepwise validation process outlined in the reference answer.


## q012 (unanswerable) — correct

**Q:** if I switch our LDAP connection over to LDAPS (LDAP over SSL/TLS), does that stop LDAP injection attacks on its own, or do I still need to escape/bind input separately?

**Reference:** I don't know -- this corpus does not cover LDAPS or LDAP-over-TLS/SSL at all, so I can't confirm what effect it has on LDAP injection.

**Answer** (cited [1, 2, 3, 4, 5]): Escaping input and using proper encoding remains necessary even when using LDAPS. The LDAP Injection Cheat Sheet emphasizes escaping all variables using the right LDAP encoding function and using frameworks that automatically protect from LDAP Injection, which are defensive measures independent of transport security [1]. It also discusses parameterized or safely constructed queries as a primary defense, illustrating secure construction practices beyond transport, including safe frameworks and encoded inputs [2][3][4][5]. Therefore, switching to LDAPS does not by itself stop LDAP injection attacks; you still need to escape/bind input appropriately and prefer parameterized or framework-assisted query construction as part of defense in depth [1][2][3][4][5].

gold in context: None · gold cited: None

Judge: The assistant correctly states that LDAPS does not prevent LDAP injection attacks on its own and that escaping and proper input handling remain necessary. This aligns with the reference answer's implication that transport security does not address injection vulnerabilities. The assistant's answer is supported by the cited sources and covers the key point that input sanitization and parameterization are still required regardless of using LDAPS.


## q020 (procedural) — correct

**Q:** Before we ship this feature, how should we actually test that object-level access control is enforced everywhere, instead of just eyeballing the code?

**Reference:** Create two test user accounts (User A and User B), create objects owned by each one (documents, support tickets, invoices, etc.), then authenticate as User A and try to access User B's objects by modifying the object references in requests. Verify access is denied regardless of whether the identifier is predictable or hard to guess.

**Answer** (cited [1, 2, 3, 4, 5]): Test that object-level access control is enforced everywhere by performing systematic, verifiable checks across all operations and object types, not by eyeballing the code. Key guidance from the sources:
- Use verification that object-level authorization is consistently enforced by testing with multiple users and objects, attempting each operation (read, create, update, delete, export, admin actions) and confirming access is denied when unauthorized [1].
- Apply automated tests to ensure security features and access controls are enforced [2].
- Run swap tests for BOLA: create objects with two accounts, replay requests under the other session, cover reads and writes, and verify ownership checks are present next to unchecked operations; test across object types and include nested routes [3].
- Ensure server-side enforcement and centralized authorization checks in the code review hygiene, and verify post-authentication checks and proper authorization after authentication [4].
- Use integration tests that profile verifications by POV/role, with limited code duplication to validate the authorization matrix and actual access behavior [5].

gold in context: True · gold cited: True

Judge: The assistant's answer fully aligns with the reference answer by emphasizing testing with multiple users and objects, attempting access to others' objects, and verifying denial of unauthorized access. It also expands with additional relevant details from the sources about automated tests, swap tests, server-side enforcement, and integration tests, all consistent with the reference guidance.

- unsupported: Test that object-level access control is enforced everywhere by performing systematic, verifiable checks across all operations and object types, not by eyeballing the code.

## q030 (unanswerable) — partial

**Q:** If an attacker performs a BGP hijack to reroute traffic meant for our servers through their own network, what mitigations does this corpus suggest at the application or infrastructure level?

**Reference:** I don't know

**Answer** (cited [2, 4, 5]): The corpus suggests mitigating at the infrastructure level by using DDoS filtering/mitigation services and ensuring you have coverage for your availability requirements, and by filtering invalid sender addresses at the edge to mitigate spoofing and bypass of block lists due to ISP routing changes. It also emphasizes deploying network policies to control traffic between pods/clusters to limit lateral movement once traffic reaches your environment. Specifically: consider a DDoS filtering service and verify provider mitigation capacity/coverage [2]; filter invalid sender addresses at the edge routers to guard against spoofing/theft of traffic [5]; and use network segmentation with Kubernetes NetworkPolicy to constrain traffic inside the cluster [4].

gold in context: None · gold cited: None

Judge: The assistant answer provides relevant infrastructure-level mitigations such as DDoS filtering, filtering invalid sender addresses, and network segmentation with Kubernetes NetworkPolicy, all supported by the sources. However, the reference answer states 'I don't know,' indicating no mitigation suggestions. Thus, the assistant's answer is more informative but does not align with the reference answer's lack of knowledge, resulting in a partial correctness grade.


## q041 (factual) — incorrect

**Q:** What's the baseline transport protection I need for SAML messages flowing between my IdP and SP?

**Reference:** At minimum, use TLS 1.2, the most common solution cited for protecting SAML message confidentiality and integrity at the transport layer; this helps counter eavesdropping, theft of authentication information/bearer tokens, message deletion/modification, and man-in-the-middle attacks.

**Answer** (refused: no_valid_citations): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: False · gold cited: None

Judge: refused (no_valid_citations)


## q050 (comparative) — incorrect

**Q:** I keep seeing both an 'Authorization' and an 'Access Control' cheat sheet in OWASP's series -- are these two different topics I need to read separately, or is one just an old version of the other?

**Reference:** The Access Control Cheat Sheet is marked deprecated and tells readers to use the Authorization Cheat Sheet instead. They are not two separately maintained sets of guidance for this purpose.

**Answer** (cited [1, 4, 5]): Both topics are distinct areas in OWASP’s guidance, not a simple version change. The Authorization Cheat Sheet discusses how to implement and test authorization logic across the app’s business context and lifecycle, including regression testing and ensuring checks are server-side. The Access Control content is referenced as part of broader guidance and is positioned alongside authorization topics but is not described as a replacement or old version of the authorization material in the provided sources. See the Authorization Cheat Sheet for authorization-specific guidance and the mention of related guidance (e.g., Access Control Cheat Sheet) as complementary material [1][4][5].

gold in context: False · gold cited: False

Judge: The assistant's answer incorrectly states that the Authorization and Access Control cheat sheets are distinct and not a version change, while the reference answer clearly states that the Access Control Cheat Sheet is deprecated and readers are directed to use the Authorization Cheat Sheet instead. The sources provided do not explicitly say the Access Control Cheat Sheet is deprecated, but the reference answer's key point about deprecation and replacement is missing and contradicted by the assistant's claim of distinctness. Therefore, the assistant's answer is incorrect relative to the reference answer.


## q057 (unanswerable) — correct

**Q:** What FIDO2 authenticator certification level do I need in order to meet NIST AAL3 for a government-facing login?

**Reference:** I don't know.

**Answer** (cited [1, 2, 4]): The sources do not specify a specific FIDO2 authenticator certification level required to meet NIST AAL3. They discuss protection of synced vs device-bound credentials and general MFA recommendations, including high-assurance options and attestation considerations, but do not state a certification level for AAL3. Therefore, this part is not covered by the provided sources. [1][2][4]

gold in context: None · gold cited: None

Judge: The assistant correctly states that the sources do not specify a FIDO2 authenticator certification level for NIST AAL3, aligning with the reference answer's admission of not knowing. The assistant also accurately summarizes relevant related information from the sources without contradicting the reference.


## q058 (unanswerable) — correct

**Q:** What TTL and eviction policy should I configure on Redis if I'm using it as my server-side session store?

**Reference:** I don't know.

**Answer** (cited [1, 5]): TTL and eviction policy guidance for Redis as a server-side session store are not explicitly specified in the provided sources. The materials discuss session token storage and general session management practices, but do not prescribe specific Redis TTL values, eviction policies, or related configuration details. Therefore, this question cannot be fully answered from the given sources. [1][5]

gold in context: None · gold cited: None

Judge: The assistant correctly states that the provided sources do not specify TTL or eviction policy recommendations for Redis as a session store, matching the reference answer's admission of not knowing. The assistant does not contradict or add unsupported details, thus the answer is correct.


## q062 (comparative) — partial

**Q:** Docker Secrets seem like a solid way to handle sensitive data in containers — can I rely on the same approach once those containers are running under Kubernetes instead of plain Docker?

**Reference:** The Docker sheet says not to assume the same approach applies to Kubernetes. It describes Docker Swarm Secrets as distributed over mutual TLS and stored in an encrypted Raft log, while warning that Kubernetes Secrets are stored without encryption by default. The Kubernetes sheet makes the at-rest distinction explicit: configure a non-`identity` encryption provider first for Secrets, then rewrite existing Secrets to encrypt previously stored data. The Docker sheet also suggests third-party tools.

**Answer** (cited [1]): Docker Secrets provide a secure way to manage sensitive data in Docker environments, and the Docker Secrets approach is not recommended for Kubernetes, where secrets are stored in plaintext by default. In Kubernetes, consider using additional security measures such as etcd encryption, or third-party tools. Refer to Secrets Management and Kubernetes Security Cheat Sheets for more information [1].

gold in context: True · gold cited: True

Judge: The assistant correctly states that Docker Secrets are secure in Docker and that Kubernetes stores secrets in plaintext by default, recommending additional security measures like etcd encryption or third-party tools. However, it misses the explicit explanation from the reference answer about Docker Swarm Secrets being distributed over mutual TLS and stored encrypted in Raft logs, and the Kubernetes sheet's explicit recommendation to configure a non-identity encryption provider and rewrite existing secrets to encrypt stored data. The assistant also does not mention the Docker sheet's suggestion of third-party tools beyond a brief mention. Thus, the answer is accurate but incomplete compared to the reference.


## q070 (procedural) — incorrect

**Q:** Before any infrastructure actually gets deployed, what security steps should be built into the early 'write and share the IaC code' stage of the workflow?

**Reference:** Use IDE security plugins (e.g. TFLint, Checkov) for early detection; build threat modeling into the dev cycle early; manage secrets properly instead of in plaintext files or committed to Git; keep IaC under version control with infrastructure changes checked in alongside the feature code they support (not separately); and apply least-privilege access policies that define exactly who is authorized to create, update, run, or delete the IaC scripts and inventory, and limit their permissions to only what's necessary.

**Answer** (refused: no_valid_citations): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (no_valid_citations)


## q079 (comparative) — incorrect

**Q:** Django hands you a ready-made `django.contrib.auth` app for login/logout/password stuff, but FastAPI doesn't really have an equivalent. If I use FastAPI's `OAuth2PasswordBearer` helper, does it actually check that the token is legit, the way Django's auth app handles things for me?

**Reference:** No. OAuth2PasswordBearer only checks the authorization scheme and pulls the bearer token out of the Authorization header — it does not validate the token or verify its signature. You still have to write your own authentication dependency that verifies the token and rejects invalid credentials before it returns a user. Django's django.contrib.auth, by contrast, already ships views/forms for login, logout, and password changes out of the box.

**Answer** (refused: model_declined): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (model_declined)


## q094 (factual) — partial

**Q:** If my GraphQL API is only ever called by our own internal services, is it still fine to leave introspection and GraphiQL turned on in production?

**Reference:** No -- disable introspection queries and GraphiQL (and similar schema-exploration tools) system-wide in any production or publicly accessible environment, regardless of whether the intended consumers are internal only.

**Answer** (cited [2, 3]): No. The sources advise disabling or restricting introspection and GraphiQL, with guidance that you should disable them based on needs and consider not enabling them for non-authenticated users. Specifically, Introspection + GraphiQL should be disabled in production unless there is a justified internal/internal-use case, and even then access should be controlled: disable introspection for unauthorized users and consider filtering access. See: disable introspection and GraphiQL, and separate guidance about restricting exposure and access control for internal use [2][3].

gold in context: False · gold cited: False

Judge: The assistant correctly states that introspection and GraphiQL should be disabled or restricted in production and that access control is important even for internal use. However, the reference answer is more definitive, stating that introspection and GraphiQL should be disabled system-wide in any production or publicly accessible environment regardless of internal use. The assistant's answer leaves room for enabling them if justified internally, which is not aligned with the reference's clear recommendation to disable them in production regardless.


## q097 (factual) — partial

**Q:** If I spin up a grpc-go server without touching any message-size settings, am I already protected from oversized messages, and is that protection enough on its own?

**Reference:** Yes, grpc-go's server-side MaxRecvMsgSize already defaults to 4 MiB with no extra configuration. But that alone isn't enough: a stream can still carry many individually valid messages, so a per-message size limit doesn't bound the total data or processing work for the whole stream.

**Answer** (cited [1]): The sources emphasize configuring message size limits and monitoring for resource exhaustion, including explicit examples of setting MaxRecvMsgSize/MaxSendMsgSize to 4 MiB and noting that a per-message limit does not bound total data or work for the stream. Since the question asks about starting a server without touching message-size settings and whether protection exists by default: the sources do not state that any default protection against oversized messages exists, nor that protection is sufficient without explicit limits. They only describe implementing and enforcing limits as a best practice. Therefore, the answer to whether you are protected by default is not provided by the sources; you would need to set explicit per-message limits and consider additional rate limiting and timeouts as described. The relevant points are: set message size limits to bound per-message data [1], and note that a per-message limit does not bound total stream data [1]. Protection from oversized messages by default is not specified in the sources. [1]

gold in context: True · gold cited: True

Judge: The assistant correctly notes that the sources emphasize setting message size limits and that a per-message limit does not bound total stream data, which aligns with the reference answer. However, the assistant incorrectly states that the sources do not specify any default protection against oversized messages, while source [1] explicitly states that grpc-go's MaxRecvMsgSize defaults to 4 MiB. Thus, the assistant misses the key point that there is a default limit, though it also correctly notes that this alone is insufficient protection. Therefore, the answer is partially correct but misses the explicit mention of the default limit.


## q102 (unanswerable) — correct

**Q:** How do I set up end-to-end encryption on WebSocket messages so that even if my own server infrastructure gets compromised, an attacker can't read the message content?

**Reference:** I don't know

**Answer** (cited [2]): The provided sources do not describe end-to-end encryption for WebSocket messages. They mention transport-level security (TLS) and client-side encryption considerations in a general sense, but do not provide guidance or steps for implementing end-to-end encryption of WebSocket payloads or managing keys to ensure that content remains unreadable even if server infrastructure is compromised. Therefore, this part is not covered by the sources. Source references: [2] for TLS and general client-side encryption cautions, but nothing about end-to-end WebSocket message encryption; none of the sources describe an end-to-end encryption setup for WebSockets.

gold in context: None · gold cited: None

Judge: The assistant correctly states that the sources do not provide information on setting up end-to-end encryption for WebSocket messages, which aligns with the reference answer's admission of not knowing. The assistant also accurately notes that TLS and client-side encryption are mentioned generally but without specific guidance on end-to-end encryption, which is consistent with the sources.

- unsupported: The provided sources do not describe end-to-end encryption for WebSocket messages.

## q103 (multi_sheet) — partial

**Q:** Once a partner's webhook delivery is verified at our edge, it fans out into work across several of our internal microservices -- what should change about how we log that event as it moves from the webhook endpoint into those services?

**Reference:** At the webhook endpoint itself, log only metadata -- timestamp, source IP, HTTP method, response status, event ID, event type, and processing latency -- and never the full request body, signing secrets, or the Authorization/signature header values. As the event then flows through your internal microservices, generate a correlation ID that uniquely identifies the whole call chain and have every service include that same correlation ID in its own log messages, so you can group and trace the event's path across services.

**Answer** (cited [5]): Log and persist processed event IDs after delivery verification and skip repeats, ensuring idempotency across downstream services. Treat duplicates as already-processed and return 200 for authenticated duplicates that have durably queued or processed, so side effects are not repeated. Do not assume in-order delivery; fetch current state if needed and design downstream effects to be idempotent. These practices help coordinate logging as the event fans out to internal microservices [5].

gold in context: False · gold cited: False

Judge: The assistant's answer correctly emphasizes idempotency, duplicate detection, and handling of event ordering as the event moves through microservices, which aligns with the source [5]. However, it does not address the key point from the reference answer about logging only metadata at the webhook endpoint and generating a correlation ID for tracing the event across services. Thus, it misses the main logging guidance about metadata and correlation IDs, making the answer only partially correct.


## q104 (unanswerable) — correct

**Q:** Is there a recommended encryption algorithm, like AES-256, for encrypting received webhook payloads at rest once they're stored in our database?

**Reference:** I don't know

**Answer** (cited [2, 5]): Use AES-256 with GCM or ChaCha20-Poly1305 as encryption types to provide encryption and confidentiality for stored data, per Secrets Management Cheat Sheet and general guidance on strong encryption for data in transit or at rest. Specifically, the Secrets Management Cheat Sheet recommends selecting an algorithm that provides encryption and confidentiality at the same time, such as AES-256 using GCM, or ChaCha20-Poly1305 [2]. Additionally, the Web Service Security Cheat Sheet states that data meant to be confidential must be encrypted using a strong encryption cipher with an adequate key length for data at rest [5].

gold in context: None · gold cited: None

Judge: The assistant's answer correctly identifies AES-256 with GCM or ChaCha20-Poly1305 as recommended encryption algorithms for data at rest, citing the Secrets Management Cheat Sheet and Web Service Security Cheat Sheet. This aligns with the reference answer's lack of specific recommendation but provides a correct and supported recommendation from the sources.


## q112 (multi_sheet) — incorrect

**Q:** Our CI review-bot agent reads PR titles, bodies, and diffs, and we want an audit log of what it did - what should actually go into that log entry, and what has to stay out of it?

**Reference:** Log the CI agent's action metadata - correlation identifiers, authorization decisions, and outcomes - and watch for unexpected file modifications, network calls, or secret-access patterns. But exclude secrets and sensitive prompt, tool-argument, and response content from the log, following the Logging cheat sheet's exclusion rules, which specifically call out things like access tokens, authentication passwords, and sensitive personal data as items that must be removed, masked, hashed, or encrypted rather than written directly into log entries.

**Answer** (refused: no_valid_citations): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (no_valid_citations)



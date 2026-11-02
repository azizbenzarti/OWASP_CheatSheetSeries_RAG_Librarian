# Generation failures (test set)

Every question that was refused when answerable, answered when unanswerable, graded below `correct`, or has an unsupported / mis-cited claim.

## q002 (procedural) — incorrect

**Q:** We have a login page and a sign-up page hitting the same users table -- what's the recommended way to split up database account privileges so that a compromise of one page can't be used to write data through the other?

**Reference:** Give each application (or each distinct function) its own dedicated database user account rather than sharing one owner/admin account. Grant only the access that function needs: for example, a login page should get read-only access to the username/password fields (no insert, update, or delete), while the sign-up page gets insert privilege on that table -- a separation that can only be enforced if the two pages connect as different DB users.

**Answer** (refused: no_valid_citations): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (no_valid_citations)


## q010 (procedural) — partial

**Q:** our webhook feature lets customers register a callback URL that our server later POSTs to -- since we can't allowlist arbitrary customer URLs ahead of time, what step-by-step validation should happen before that outbound request actually fires?

**Reference:** Reject the request unless every one of these checks passes: (1) validate that the supplied value is a well-formed IP address or domain name; (2) apply a block-list check -- for an IP, verify it's a public address; for a domain, verify it resolves as public (not via an internal-only resolver) and then re-validate every A/AAAA address it resolves to as public, binding the connection to that validated address; (3) validate the requested protocol against an allowlist of HTTP/HTTPS only; (4) validate the token parameter name against a strict character set; (5) validate the token value against a strict character set; (6) validate any other business data needed for the call; then (7) build the HTTP POST request using only that validated information, connect only to the IP address already validated in step 2, and disable redirect-following in the HTTP client.

**Answer** (cited [4, 5]): Before delivering to a customer-registered callback URL, implement verifications to ensure the delivery is legitimate and safe:
- Use signature verification and a signing secret to authenticate callbacks and verify events on every delivery [5].
- Preserve threat-model controls: require an authenticated timestamp with a tolerance window and authenticate the event ID to deduplicate [5].
- Ensure the callback URL uses a secure scheme and enforce policies to prevent connecting to non-public or untrusted addresses (allowlist https:// and deny-list non-public ranges; verify resolved IP at connect time) [5].
- Apply idempotent processing and deduplicate events to prevent duplicate fulfillment from replays [5].
- Treat the callback as server-to-server communication and validate the authenticity of the callback (e.g., verify signatures) before acting on the event data [4][5].
- Consider transport security (TLS) with a trusted CA for the connection [5].
- Log callback attempts for forensic analysis [4].

gold in context: False · gold cited: False

Judge: The assistant's answer covers important security measures such as signature verification, timestamp and event ID authentication, secure scheme enforcement, idempotency, and logging, all supported by the sources. However, it does not explicitly address the step-by-step validation of the callback URL itself as detailed in the reference answer, such as validating the URL format, checking for public IP/domain, binding connections to validated IPs, and disabling redirect-following. Therefore, it partially addresses the question but misses key URL validation steps required before firing the outbound request.


## q012 (unanswerable) — correct

**Q:** if I switch our LDAP connection over to LDAPS (LDAP over SSL/TLS), does that stop LDAP injection attacks on its own, or do I still need to escape/bind input separately?

**Reference:** I don't know -- this corpus does not cover LDAPS or LDAP-over-TLS/SSL at all, so I can't confirm what effect it has on LDAP injection.

**Answer** (cited [1, 2, 3, 4, 5]): LDAPS encryption primarily protects the transport layer and does not automatically prevent LDAP injection. The LDAP Injection Cheat Sheet emphasizes escaping input (or using frameworks that do automatic escaping) as a primary defense, and provides examples of escaping and parameterized queries to prevent injection. Therefore, even when using LDAPS, you still need to escape/bind input appropriately or use a framework that handles escaping [1][3][2][4][5].

gold in context: None · gold cited: None

Judge: The assistant correctly states that LDAPS only protects the transport layer and does not prevent LDAP injection by itself, matching the reference's implication that escaping or binding input is still necessary. The assistant's answer aligns well with the reference answer's key point that LDAPS does not eliminate the need for input escaping or binding to prevent LDAP injection.


## q030 (unanswerable) — partial

**Q:** If an attacker performs a BGP hijack to reroute traffic meant for our servers through their own network, what mitigations does this corpus suggest at the application or infrastructure level?

**Reference:** I don't know

**Answer** (cited [2, 5]): The corpus suggests using DDoS filtering services with provider mitigation capacity and coverage, and ensuring compliance with data privacy laws for traffic routed through external networks as mitigations at the infrastructure level. It also recommends filtering invalid sender addresses at edge routers to guard against IP-spoofing used in routing attacks. There is no explicit mention of BGP hijack-specific mitigations beyond these points. See [2][5] and [5].

gold in context: None · gold cited: None

Judge: The assistant correctly identifies infrastructure-level mitigations such as DDoS filtering services, compliance with data privacy laws, and filtering invalid sender addresses at edge routers, which are relevant to network attacks. However, the reference answer states 'I don't know,' indicating no specific mitigations are suggested for BGP hijacks. The assistant adds information not explicitly linked to BGP hijacks and notes no explicit mention of BGP hijack-specific mitigations, which is accurate but the overall answer goes beyond the reference's uncertainty. Thus, the answer is partially correct but does not fully align with the reference's admission of no known mitigations.

- unsupported: There is no explicit mention of BGP hijack-specific mitigations beyond these points.

## q036 (factual) — incorrect

**Q:** What's the lowest-memory Argon2id setting OWASP still considers acceptable if I'm tight on RAM?

**Reference:** The lowest-memory configuration listed is m=7168 (7 MiB), t=5, p=1. All five listed configurations (46/19/12/9/7 MiB paired with t=1 through t=5 respectively) provide an equivalent level of defense -- the only trade-off is between CPU time and RAM usage.

**Answer** (cited [4]): Use Argon2id with a minimum configuration of 19 MiB of memory, an iteration count of 2, and 1 degree of parallelism [4].

gold in context: False · gold cited: False

Judge: The assistant's answer states the minimum Argon2id memory setting as 19 MiB with t=2 and p=1, but the reference answer and source [1] indicate the lowest-memory acceptable setting is 7 MiB (m=7168), t=5, p=1, with all configurations from 7 MiB to 46 MiB providing equivalent defense. Thus, the assistant's answer is incorrect as it does not reflect the lowest-memory setting considered acceptable by OWASP.


## q041 (factual) — incorrect

**Q:** What's the baseline transport protection I need for SAML messages flowing between my IdP and SP?

**Reference:** At minimum, use TLS 1.2, the most common solution cited for protecting SAML message confidentiality and integrity at the transport layer; this helps counter eavesdropping, theft of authentication information/bearer tokens, message deletion/modification, and man-in-the-middle attacks.

**Answer** (refused: declined_in_text): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: False · gold cited: None

Judge: refused (declined_in_text)


## q044 (multi_sheet) — partial

**Q:** If I decide to use a JWT as my session token, what do I actually need to nail down about expiration so I don't end up with sessions I can't kill early?

**Reference:** Plan session invalidation separately from expiration. The JWT sheet gives a denylist of revoked sessions/tokens as one solution, while noting that it makes sessions no longer completely stateless. The Session Management sheet requires an idle timeout and an absolute timeout regardless of activity, with expiration enforced server-side. At the absolute limit, invalidate the session and require re-authentication. JWT-based sessions still need those expiration and invalidation controls.

**Answer** (cited [1, 2, 3]): If you use JWTs for session tokens, you should validate and enforce expiration considerations to support revocation and avoid unkillable sessions. Key points from the sources: set an expiration time (exp) and ensure current time is before the token’s end of validity; consider not-before (nbf) if your profile requires it; when explicit session termination occurs, use a denylist (jti) to invalidate the JWT until expiration; implement a denylist on the API to invalidate JWTs after logout or idle timeout; manage token revocation and freshness via a denylist and, where applicable, a nonce approach for replay protection; also consider using Token Status List or short expirations and sender-constrained tokens to mitigate token reuse. In short: require exp (and possibly nbf), implement a denylist (with jti) for explicit invalidation, and use shorter expiration or additional protections to limit the window of unauthorised use. [2][3][1]

gold in context: True · gold cited: True

Judge: The assistant correctly emphasizes the need for expiration enforcement, denylist usage for revocation, and mentions exp, nbf, and jti claims, aligning with the reference's key points about session invalidation and expiration controls. However, it misses the explicit mention of idle timeout and absolute timeout enforced server-side, which are crucial for session management to avoid unkillable sessions as stated in the reference answer. The assistant also does not explicitly mention the need for absolute timeout and re-authentication after expiration, which are important details in the reference.


## q050 (comparative) — incorrect

**Q:** I keep seeing both an 'Authorization' and an 'Access Control' cheat sheet in OWASP's series -- are these two different topics I need to read separately, or is one just an old version of the other?

**Reference:** The Access Control Cheat Sheet is marked deprecated and tells readers to use the Authorization Cheat Sheet instead. They are not two separately maintained sets of guidance for this purpose.

**Answer** (cited [1, 4, 5]): The sources show separate cheat sheets for Authorization and for Access Control, treated as distinct topics to read about: Authorization Cheat Sheet and Authorization Regression Testing Cheat Sheet are presented as their own guides, and there is a reference to general Access Control guidance (Access Control Cheat Sheet) as well. This indicates they are separate materials to read, not a single old version of the other. Specifically, the Authorization Cheat Sheet is described as addressing authorization logic and its implementation, while the Access Control guidance is mentioned as a related, broader topic to see (e.g., in the Business Logic Security Cheat Sheet references). The sources do not state that one supersedes the other or that one is an old version of the other. They are positioned as related but distinct cheat sheets. [1][4][5]

gold in context: False · gold cited: False

Judge: The assistant's answer claims that Authorization and Access Control cheat sheets are separate and distinct, with no indication that one supersedes or replaces the other. However, the reference answer clearly states that the Access Control Cheat Sheet is deprecated and directs readers to use the Authorization Cheat Sheet instead. The assistant's answer contradicts this key point, making it incorrect despite correctly describing the content of the sources.


## q058 (unanswerable) — correct

**Q:** What TTL and eviction policy should I configure on Redis if I'm using it as my server-side session store?

**Reference:** I don't know.

**Answer** (cited [1, 2, 4]): The sources mention general principles but do not specify exact TTL values or eviction policies for Redis as a server-side session store. They state to restrict access to the session store, encrypt backups, follow logging protections, and renew session IDs after privilege changes, and in the Multi-Tenant guidance they discuss choosing TTL and invalidation behavior from freshness and authorization risk, including that immutable, versioned global entries may not require expiry. However, no concrete TTL duration or eviction policy (e.g., LRU, TTL-based eviction specifics) is provided. Therefore, this exact question is not answerable from the given sources. [1][2][4]

gold in context: None · gold cited: None

Judge: The assistant correctly states that the sources do not provide specific TTL or eviction policy recommendations for Redis as a session store, which aligns with the reference answer's admission of not knowing. The assistant also accurately summarizes relevant related guidance from the sources without contradicting the reference.


## q070 (procedural) — partial

**Q:** Before any infrastructure actually gets deployed, what security steps should be built into the early 'write and share the IaC code' stage of the workflow?

**Reference:** Use IDE security plugins (e.g. TFLint, Checkov) for early detection; build threat modeling into the dev cycle early; manage secrets properly instead of in plaintext files or committed to Git; keep IaC under version control with infrastructure changes checked in alongside the feature code they support (not separately); and apply least-privilege access policies that define exactly who is authorized to create, update, run, or delete the IaC scripts and inventory, and limit their permissions to only what's necessary.

**Answer** (cited [2, 3, 4, 5]): From the IaC Security Cheatsheet, in the Develop and Distribute stage and related sections, include: static analysis of IaC to identify risks and misconfigurations; open source dependency check to analyze dependencies; container image scan to detect issues in images; CI/CD pipeline integration with consolidated reporting to ensure security checks are available during code changes; artifact signing to protect integrity and provenance of artifacts. Also emphasize threat modeling and managing secrets during development, and applying the principle of least privilege to access policies for IaC scripts. Tagging and inventory-related practices help with observability and avoiding ghost resources. Dynamic analysis and highlighting the importance of secure sharing/distribution in the write/share IaC code stage are also noted. See: Develop and Distribute concepts and Security best practices sections. [2][4][3][5]

gold in context: True · gold cited: True

Judge: The assistant's answer covers many relevant security steps such as static analysis, dependency checks, container image scanning, CI/CD integration, artifact signing, threat modeling, secrets management, least privilege, tagging, inventory, and dynamic analysis, all supported by the cited sources. However, it misses some key points from the reference answer, such as the use of IDE security plugins specifically named (e.g., TFLint, Checkov), the explicit recommendation to keep IaC under version control alongside feature code, and the explicit mention of avoiding plaintext secrets or committing secrets to Git. These omissions mean the answer is only partially correct compared to the reference.


## q079 (comparative) — incorrect

**Q:** Django hands you a ready-made `django.contrib.auth` app for login/logout/password stuff, but FastAPI doesn't really have an equivalent. If I use FastAPI's `OAuth2PasswordBearer` helper, does it actually check that the token is legit, the way Django's auth app handles things for me?

**Reference:** No. OAuth2PasswordBearer only checks the authorization scheme and pulls the bearer token out of the Authorization header — it does not validate the token or verify its signature. You still have to write your own authentication dependency that verifies the token and rejects invalid credentials before it returns a user. Django's django.contrib.auth, by contrast, already ships views/forms for login, logout, and password changes out of the box.

**Answer** (refused: model_declined): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (model_declined)


## q094 (factual) — incorrect

**Q:** If my GraphQL API is only ever called by our own internal services, is it still fine to leave introspection and GraphiQL turned on in production?

**Reference:** No -- disable introspection queries and GraphiQL (and similar schema-exploration tools) system-wide in any production or publicly accessible environment, regardless of whether the intended consumers are internal only.

**Answer** (cited [1, 2, 3, 5]): Yes, it is fine to leave introspection and GraphiQL on in production if your GraphQL API is only consumed by internal services, but you should consider security implications and options described in the sources. The sources advise disabling or restricting introspection and GraphiQL based on needs and note that internal APIs might still benefit from a filter to restrict access or disable introspection for non-approved consumers; they also highlight that even with introspection disabled, fields can be guessed and that you should consider disabling the feature that hints similar field names. Therefore, for internal-only usage, you can disable introspection/system-wide or implement access controls, but you should evaluate the specific guidance from the cheat sheet on secure configurations and access control for internal APIs. [1][2][3][5]

gold in context: False · gold cited: False

Judge: The assistant's answer incorrectly states that it is fine to leave introspection and GraphiQL enabled in production for internal-only APIs, which contradicts the reference answer that clearly states introspection and GraphiQL should be disabled system-wide in any production or publicly accessible environment regardless of internal or external use. The assistant does mention security considerations and options to restrict access, but it fails to convey the key point that introspection and GraphiQL should be disabled in production environments even if only internal services consume the API.

- unsupported: It is fine to leave introspection and GraphiQL on in production if your GraphQL API is only consumed by internal services.
- mis-cited: It is fine to leave introspection and GraphiQL on in production if your GraphQL API is only consumed by internal services.

## q097 (factual) — partial

**Q:** If I spin up a grpc-go server without touching any message-size settings, am I already protected from oversized messages, and is that protection enough on its own?

**Reference:** Yes, grpc-go's server-side MaxRecvMsgSize already defaults to 4 MiB with no extra configuration. But that alone isn't enough: a stream can still carry many individually valid messages, so a per-message size limit doesn't bound the total data or processing work for the whole stream.

**Answer** (cited [1, 2, 3, 4, 5]): No. The guidance shows setting per-message size limits is recommended to bound message sizes (MaxRecvMsgSize and MaxSendMsgSize), implying that without explicit limits, protection from oversized messages is not ensured by default [1]. It also notes that a stream can carry many individually valid messages, so a per-message limit is needed to bound total data or processing work for the stream [1]. Therefore, relying on defaults alone is not enough protection; you should configure appropriate message size limits in addition to other protections described (timeouts, TLS, authentication, and rate limiting) as applicable [1][2][3][4][5].

gold in context: True · gold cited: True

Judge: The assistant correctly states that a stream can carry many valid messages and that per-message limits are recommended, which aligns with the reference. However, it incorrectly claims that protection from oversized messages is not ensured by default, while the reference states grpc-go defaults MaxRecvMsgSize to 4 MiB. The assistant also adds extra recommendations about other protections, which are not part of the reference answer's focus on message size limits. Thus, the answer is partially correct but misses the key point that grpc-go already defaults to a 4 MiB limit.

- unsupported: Without explicit limits, protection from oversized messages is not ensured by default.
- mis-cited: Without explicit limits, protection from oversized messages is not ensured by default.

## q098 (multi_sheet) — partial

**Q:** My backend services talk to each other over gRPC internally, and the same system also receives webhooks from an external partner. What do I actually need to lock down on each side of that setup?

**Reference:** For service-to-service gRPC, the cited guidance recommends mTLS so the client and server verify each other's certificates. For inbound partner webhooks, verify an HMAC-SHA256 signature on every delivery to protect against forged events. These address authentication at the connection and delivery levels, respectively; the exact partner integration may have additional requirements.

**Answer** (cited [3, 4, 5]): Lock down gRPC internal service communication and external webhook handling using the controls described in the cheat sheets:
- For gRPC internal service communication: implement secure service discovery with mTLS and centralized security policies, e.g., use Istio or Linkerd for automatic mTLS and secure service discovery, and configure mutual TLS between services as part of service discovery security. This is recommended for gRPC service discovery and reflection scenarios. [3]
- For external webhooks: ensure replay/duplication/abuse controls and SSRF protections. Implement idempotent downstream processing, return 200 for authenticated duplicates, and verify event delivery sequences and IDs. Validate destinations, restrict destinations to https, and perform DNS/IP validation and host resolution checks to prevent SSRF. Isolate webhook delivery workers behind a network segment with restricted egress, and disable redirects or validate them. [4][5]

gold in context: False · gold cited: False

Judge: The assistant correctly identifies the need for mTLS in gRPC internal communication and replay/duplication and SSRF protections for external webhooks, supported by the cited sources. However, it misses the key point from the reference answer about verifying an HMAC-SHA256 signature on every webhook delivery to protect against forged events, which is a crucial authentication measure for inbound partner webhooks. The assistant focuses more on service discovery security and SSRF prevention but does not mention signature verification, making the answer only partially correct.


## q103 (multi_sheet) — partial

**Q:** Once a partner's webhook delivery is verified at our edge, it fans out into work across several of our internal microservices -- what should change about how we log that event as it moves from the webhook endpoint into those services?

**Reference:** At the webhook endpoint itself, log only metadata -- timestamp, source IP, HTTP method, response status, event ID, event type, and processing latency -- and never the full request body, signing secrets, or the Authorization/signature header values. As the event then flows through your internal microservices, generate a correlation ID that uniquely identifies the whole call chain and have every service include that same correlation ID in its own log messages, so you can group and trace the event's path across services.

**Answer** (cited [5]): Log idempotently and persist processed event IDs to skip repeats, ensuring downstream side effects are idempotent by default; do not repeat side effects for authenticated duplicates that have already been durably queued or processed [5]. Also fetch current state if there’s any potential for out-of-order delivery and avoid assuming in-order delivery, relying on publisher’s guarantees [5].

gold in context: False · gold cited: False

Judge: The assistant's answer correctly emphasizes idempotent logging and handling of duplicate events with persistence of event IDs and idempotent side effects, as well as fetching current state to handle out-of-order delivery, which aligns with the source [5]. However, it misses the key point from the reference answer about logging only metadata at the webhook endpoint and generating a correlation ID for tracing the event across internal microservices. Thus, it partially addresses the question but omits the main logging guidance about metadata and correlation IDs.


## q104 (unanswerable) — partial

**Q:** Is there a recommended encryption algorithm, like AES-256, for encrypting received webhook payloads at rest once they're stored in our database?

**Reference:** I don't know

**Answer** (cited [2, 5]): Yes. Use a strong encryption cipher with adequate key length to deter brute-forcing for data at rest, i.e., a strong encryption cipher such as AES-256 (when encrypting data at rest) [5]. Also, prefer encryption that provides confidentiality at rest, such as AES-256 with an appropriate mode like GCM, as recommended for encryption types to use [2].

gold in context: None · gold cited: None

Judge: The assistant correctly recommends AES-256 with an appropriate mode like GCM for encrypting data at rest, which aligns with the sources. However, the reference answer states 'I don't know,' so the assistant's answer goes beyond the reference by providing a recommendation. Since the reference answer does not provide any recommendation, the assistant's answer is more informative but does not contradict the reference. Therefore, the answer is partially correct relative to the reference.


## q108 (factual) — incorrect

**Q:** Roughly how much retrieved context - number of chunks and token budget - is a sane security-conscious default to stuff into the LLM's prompt per RAG query?

**Reference:** A reasonable default in the RAG sheet is 3–5 retrieved chunks totaling about 2,000–4,000 tokens. The guidance says to limit both the number and total size of retrieved chunks to prevent context-window flooding.

**Answer** (refused: no_valid_citations): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (no_valid_citations)


## q114 (procedural) — incorrect

**Q:** I've never led a threat modeling session before - what's the actual sequence of questions or steps I should walk the team through, start to finish?

**Reference:** Use the four questions in order: (1) What are we working on? (2) What can go wrong? (3) What are we going to do about it? (4) Did we do a good enough job? The cheat sheet presents them as the foundation for the threat-modeling phases.

**Answer** (refused: no_valid_citations): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (no_valid_citations)


## q115 (factual) — partial

**Q:** Do I still need to set X-Frame-Options if I already have a Content-Security-Policy with frame-ancestors configured?

**Reference:** Not really, for modern browsers - CSP's frame-ancestors directive obsoletes X-Frame-Options for browsers that support it. X-Frame-Options is also only meaningful when the response has something to interact with, like links or buttons; it provides no security benefit on a redirect or a pure JSON API response.

**Answer** (cited [3, 4, 5]): Yes. CSP frame-ancestors obsoletes X-Frame-Options for supporting browsers, but X-Frame-Options can still be relevant in some contexts. Use CSP frame-ancestors if possible, and note that X-Frame-Options header is still described as a defense option, with its own usage guidance. [4][3][5]

gold in context: True · gold cited: True

Judge: The assistant correctly states that CSP frame-ancestors obsoletes X-Frame-Options for supporting browsers and recommends using CSP frame-ancestors if possible, which aligns with the reference. However, it incorrectly answers "Yes" to whether X-Frame-Options is still needed, implying it is still necessary, whereas the reference answer says it is not really needed for modern browsers. The assistant also claims X-Frame-Options can still be relevant in some contexts but provides no citation or source support for this, making that claim unsupported. Overall, the assistant's answer partially matches the reference but is somewhat misleading about the necessity of X-Frame-Options when CSP frame-ancestors is configured.

- unsupported: X-Frame-Options can still be relevant in some contexts


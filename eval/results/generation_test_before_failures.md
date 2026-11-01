# Generation failures (test set)

Every question that was refused when answerable, answered when unanswerable, graded below `correct`, or has an unsupported / mis-cited claim.

## q010 (procedural) — partial

**Q:** our webhook feature lets customers register a callback URL that our server later POSTs to -- since we can't allowlist arbitrary customer URLs ahead of time, what step-by-step validation should happen before that outbound request actually fires?

**Reference:** Reject the request unless every one of these checks passes: (1) validate that the supplied value is a well-formed IP address or domain name; (2) apply a block-list check -- for an IP, verify it's a public address; for a domain, verify it resolves as public (not via an internal-only resolver) and then re-validate every A/AAAA address it resolves to as public, binding the connection to that validated address; (3) validate the requested protocol against an allowlist of HTTP/HTTPS only; (4) validate the token parameter name against a strict character set; (5) validate the token value against a strict character set; (6) validate any other business data needed for the call; then (7) build the HTTP POST request using only that validated information, connect only to the IP address already validated in step 2, and disable redirect-following in the HTTP client.

**Answer** (cited [4, 5]): To validate the outbound request before it fires, implement the following steps: 1. Verify the authenticity of callbacks using HMAC signatures [4]. 2. Use an `https://`-only scheme allowlist for URLs to ensure secure connections [5]. 3. Maintain a deny-list of non-public address ranges and enforce this during the connection initiation [5]. 4. Log all callback attempts for forensic analysis [4]. Only after these validations should the outbound request be executed.

gold in context: False · gold cited: False

Judge: The assistant's answer correctly includes verifying authenticity with HMAC signatures, enforcing HTTPS-only URLs, denying non-public IP ranges, and logging callbacks, all supported by the sources. However, it omits several key validation steps from the reference answer, such as validating the format of the IP/domain, re-validating resolved IPs as public, validating token parameters and business data, and disabling redirect-following. Thus, it only partially covers the comprehensive step-by-step validation required before firing the outbound request.


## q012 (unanswerable) — correct

**Q:** if I switch our LDAP connection over to LDAPS (LDAP over SSL/TLS), does that stop LDAP injection attacks on its own, or do I still need to escape/bind input separately?

**Reference:** I don't know -- this corpus does not cover LDAPS or LDAP-over-TLS/SSL at all, so I can't confirm what effect it has on LDAP injection.

**Answer** (cited [1, 5]): Switching to LDAPS (LDAP over SSL/TLS) does not stop LDAP injection attacks on its own; you still need to escape untrusted data that is added to any LDAP query separately [1][5].

gold in context: None · gold cited: None

Judge: The assistant correctly states that switching to LDAPS does not prevent LDAP injection attacks by itself and that escaping untrusted input is still necessary. This aligns with the reference answer's implication that LDAPS does not address injection prevention and the sources emphasize escaping input as the primary defense against LDAP injection.


## q015 (comparative) — partial

**Q:** Deserialization bugs and XXE both come from parsing data an attacker controls. Is one of them capped at information disclosure while the other can get an attacker to full RCE?

**Reference:** No. The deserialization sheet lists denial of service, access-control attacks, and remote code execution as possible consequences. The XXE sheet lists local-file exposure, SSRF, and resource exhaustion. Those passages describe different documented effects; they do not establish an absolute ceiling on what every XXE exploit can achieve.

**Answer** (cited [2, 3, 4]): Deserialization vulnerabilities can lead to arbitrary remote code execution (RCE) if there are classes available that can change behavior during or after deserialization [2][3]. In contrast, XML External Entity (XXE) injection primarily exposes local files or can cause denial of service (DoS) [4]. Thus, deserialization vulnerabilities can result in full RCE, while XXE is generally capped at information disclosure or denial of service.

gold in context: True · gold cited: True

Judge: The assistant correctly states that deserialization can lead to remote code execution and that XXE can cause information disclosure and denial of service, which aligns with the reference. However, the reference clarifies that XXE effects do not establish an absolute ceiling on what every XXE exploit can achieve, implying that XXE is not strictly capped at information disclosure. The assistant's answer implies a strict cap on XXE, which is an oversimplification and not fully supported by the sources or the reference answer.


## q036 (factual) — partial

**Q:** What's the lowest-memory Argon2id setting OWASP still considers acceptable if I'm tight on RAM?

**Reference:** The lowest-memory configuration listed is m=7168 (7 MiB), t=5, p=1. All five listed configurations (46/19/12/9/7 MiB paired with t=1 through t=5 respectively) provide an equivalent level of defense -- the only trade-off is between CPU time and RAM usage.

**Answer** (cited [1, 3]): The lowest-memory Argon2id setting that OWASP considers acceptable is 12 MiB of memory, with a time cost of 3 and a degree of parallelism of 1 [1][3].

gold in context: False · gold cited: False

Judge: The assistant correctly identifies one of the acceptable Argon2id configurations (12 MiB, t=3, p=1) and notes that OWASP considers it acceptable. However, the reference answer states the lowest-memory configuration is 7 MiB (m=7168), t=5, p=1, which the assistant omits. The assistant's answer misses the lowest memory setting and thus only partially matches the reference answer.


## q039 (factual) — partial

**Q:** Why do people keep saying I need PKCE even for my backend web app, not just mobile apps?

**Reference:** Because current OAuth 2.0 best practice requires PKCE with the Authorization Code Grant for all client types -- not just native/mobile apps -- including single-page apps and other clients. The Implicit Grant is deprecated, and PKCE is what protects the Authorization Code Grant against authorization code interception regardless of client type.

**Answer** (cited [1]): PKCE is used to mitigate the threat of authorization code interception attacks, which is a concern not limited to mobile apps, as it secures the authorization code exchange process for public clients as well. Even backend web apps can be susceptible to similar vulnerabilities, hence utilizing PKCE helps ensure that stolen authorization codes cannot be redeemed at the token endpoint without the appropriate code_verifier [1].

gold in context: False · gold cited: False

Judge: The assistant correctly explains that PKCE mitigates authorization code interception attacks and that this threat is not limited to mobile apps, which aligns with the reference answer's emphasis on PKCE being required for all client types. However, the assistant does not explicitly mention that current OAuth 2.0 best practice requires PKCE for all client types including backend web apps, nor does it mention the deprecation of the Implicit Grant or that PKCE protects the Authorization Code Grant regardless of client type. Thus, the answer is partially correct but misses some key points from the reference.


## q040 (procedural) — partial

**Q:** What should I actually do to stop a stolen refresh token from being reused by an attacker?

**Reference:** Either sender-constrain the refresh token (bind it to the client using DPoP or mTLS, so a stolen token can't be used without the matching private key) or implement refresh token rotation -- issue a new refresh token on every use and immediately invalidate the old one so reuse of a stolen token is detectable. Combining both approaches provides defense-in-depth.

**Answer** (cited [5]): To stop a stolen refresh token from being reused by an attacker, you should implement sender-constraining mechanisms such as DPoP or mTLS, or use refresh token rotation [5].

gold in context: False · gold cited: False

Judge: The assistant correctly identifies sender-constraining mechanisms (DPoP or mTLS) and refresh token rotation as methods to prevent reuse of stolen refresh tokens, which aligns with the reference answer. However, the assistant's answer omits the important detail that refresh token rotation involves issuing a new refresh token on every use and immediately invalidating the old one to detect reuse. It also does not mention that combining both approaches provides defense-in-depth, which is part of the reference answer's key points.


## q041 (factual) — partial

**Q:** What's the baseline transport protection I need for SAML messages flowing between my IdP and SP?

**Reference:** At minimum, use TLS 1.2, the most common solution cited for protecting SAML message confidentiality and integrity at the transport layer; this helps counter eavesdropping, theft of authentication information/bearer tokens, message deletion/modification, and man-in-the-middle attacks.

**Answer** (cited [1]): The baseline transport protection for SAML messages flowing between the IdP and SP should include the use of TLS to prevent Man-in-the-Middle (MITM) attacks, as risks apply to both IdP-initiated and SP-initiated flows if transport security is compromised [1].

gold in context: False · gold cited: False

Judge: The assistant correctly identifies TLS as the baseline transport protection to prevent MITM attacks and notes that risks apply to both IdP-initiated and SP-initiated flows if transport security is compromised, which aligns with the source. However, it does not specify the minimum TLS version (TLS 1.2) as the reference answer does, nor does it explicitly mention the protection of confidentiality and integrity or the types of attacks mitigated (eavesdropping, theft, message deletion/modification). Thus, the answer is partially correct but lacks the full detail of the reference answer.


## q044 (multi_sheet) — partial

**Q:** If I decide to use a JWT as my session token, what do I actually need to nail down about expiration so I don't end up with sessions I can't kill early?

**Reference:** Plan session invalidation separately from expiration. The JWT sheet gives a denylist of revoked sessions/tokens as one solution, while noting that it makes sessions no longer completely stateless. The Session Management sheet requires an idle timeout and an absolute timeout regardless of activity, with expiration enforced server-side. At the absolute limit, invalidate the session and require re-authentication. JWT-based sessions still need those expiration and invalidation controls.

**Answer** (cited [1, 2, 5]): When using JWTs as session tokens, you should ensure to have a strategy for session invalidation. This can be achieved by implementing a deny list of revoked sessions/tokens, as the JWT's state may become disconnected from the actual session state if, for instance, the session is terminated before its expiration time. Specifically, you should submit a unique, server-issued identifier (`jti` claim, optionally combined with `aud`) to a denylist upon any explicit session termination event, which will invalidate that JWT for requests until the token's expiration time [1][2]. Additionally, ensure that the token's expiration (`exp`) claim is validated to prevent the reuse of a JWT after its intended lifespan [2][5].

gold in context: True · gold cited: True

Judge: The assistant correctly explains the need for session invalidation strategies with JWTs, including deny lists and validating the expiration claim, which aligns with the reference answer. However, it misses the important point from the reference about enforcing both idle timeout and absolute timeout server-side, and the necessity of absolute timeout invalidation requiring re-authentication. Thus, the answer is partially correct but incomplete regarding expiration controls needed to avoid sessions that cannot be killed early.


## q049 (procedural) — partial

**Q:** I've added permission checks to most of my API's controller methods one by one -- is that a solid way to enforce authorization?

**Reference:** No -- relying on manually adding checks method-by-method is risky because an attacker only needs to find the one place you missed, and even a single missed check can jeopardize a resource. Instead use a global, application-wide enforcement mechanism (such as a servlet filter, framework middleware, or an interceptor) so permissions are validated consistently on every request, rather than depending on per-method diligence.

**Answer** (cited [1]): Validating permissions correctly on just the majority of requests is insufficient. Even if just a single access control check is 'missed', the confidentiality and/or integrity of a resource can be jeopardized. You should validate the permissions on every request, regardless of whether the request was initiated by an AJAX script, server-side, or any other source [1].

gold in context: True · gold cited: True

Judge: The assistant correctly states that validating permissions on most requests is insufficient and that missing a single check can jeopardize resources, aligning with the reference answer's key points. However, it misses the crucial recommendation to use a global, application-wide enforcement mechanism (such as filters or middleware) rather than relying on manual per-method checks, which is the main advice in the reference answer.


## q050 (comparative) — incorrect

**Q:** I keep seeing both an 'Authorization' and an 'Access Control' cheat sheet in OWASP's series -- are these two different topics I need to read separately, or is one just an old version of the other?

**Reference:** The Access Control Cheat Sheet is marked deprecated and tells readers to use the Authorization Cheat Sheet instead. They are not two separately maintained sets of guidance for this purpose.

**Answer** (cited [1, 5]): Authorization and Access Control are related but distinct topics. Authorization is defined as the process of verifying that a requested action or service is approved for a specific entity, while access control is a broader term that encompasses how access permissions are granted and enforced within a system [1]. For general access control guidance, see the Access Control Cheat Sheet and the Authorization Cheat Sheet, indicating that they serve complementary purposes [5].

gold in context: False · gold cited: False

Judge: The reference answer states that the Access Control Cheat Sheet is deprecated and readers should use the Authorization Cheat Sheet instead, indicating they are not separate maintained topics. The assistant's answer incorrectly implies they are distinct and complementary, which contradicts the reference answer.

- unsupported: Access control is a broader term that encompasses how access permissions are granted and enforced within a system.
- mis-cited: Access control is a broader term that encompasses how access permissions are granted and enforced within a system.

## q061 (procedural) — partial

**Q:** How can I run a Docker container with an unprivileged user or map container root to an unprivileged host user?

**Reference:** Three options: (1) at runtime, pass the -u option to docker run (e.g. docker run -u 4000 alpine); (2) at build time, add a dedicated user in the Dockerfile with groupadd/useradd and then a USER directive before the app runs; or (3) enable user namespace remapping (--userns-remap=default) in the Docker daemon so container root maps to an unprivileged host user.

**Answer** (cited [1, 2]): Configuring the container to use an unprivileged user can be done in three ways: 1. During runtime using the `-u` option of `docker run`, for example: `docker run -u 4000 alpine` [1]. 2. During build time, by adding a user in the Dockerfile, for example: `USER myuser` [1]. 3. By enabling user namespace support (`--userns-remap=default`) in the Docker daemon [1]. Additionally, in Kubernetes, this can be configured in the Security Context using the `runAsUser` field [1]. For extra security, you can run Docker in rootless mode, which mitigates vulnerabilities by running the Docker daemon and containers without host-root privileges [2].

gold in context: True · gold cited: True

Judge: The assistant correctly lists the three main methods to run a Docker container with an unprivileged user or map container root to an unprivileged host user, matching the reference answer. However, it adds extra information about Kubernetes and rootless mode, which is not in the reference answer but is supported by the sources. The reference answer focuses strictly on the three options without mentioning Kubernetes or rootless mode. Since the question is about Docker containers specifically, the Kubernetes detail is extra but not incorrect. The rootless mode is additional security advice beyond the reference. Overall, the assistant answer is mostly correct but includes additional details beyond the reference, so it is graded as partial correctness because it does not strictly match the reference answer's scope.


## q068 (procedural) — correct

**Q:** Before I pull in some open-source library for a project, what questions should I actually be asking to vet it from a security angle?

**Reference:** Among others: Is the project actively maintained? Is it sufficiently popular/well-known in its community? Is it mature? Is the version you'd use an actual release (not alpha/beta)? Does it have enough maintainers/contributors for its complexity? Does it keep its own dependencies updated? Does it have solid test coverage including security-relevant tests? Is it well-documented, including secure-usage guidance? Does it have an established, documented vulnerability-reporting process with timely fixes? And is your intended use consistent with its license?

**Answer** (cited [2]): You should consider the following questions to assess the security of an open-source library before incorporating it into your project: 
- Is the project actively maintained? 
- Is the project sufficiently popular and well-known in the applicable community? 
- Is the project sufficiently mature? 
- Is the product or version being evaluated a 'release' version, e.g. not an alpha, beta, or comparable versions? 
- Given the complexity of the project, does the project have a sufficient number of maintainers and contributors? 
- Does the project keep its dependencies updated? 
- Does the project have sufficient test coverage and do the tests include security relevant rules? 
- Is the project well-documented and does the document include guidance on how to use the component securely? 
- Does the project have an established and documented process for reporting vulnerabilities and are these vulnerabilities addressed in a timely manner? 
- Is the intended usage of the project consistent with the project's license? [2].

gold in context: True · gold cited: True

Judge: The assistant's answer lists all the key questions from the reference answer, matching the points exactly and supported by source [2]. It covers all the important aspects of vetting an open-source library from a security perspective without contradiction or omission.

- unsupported: You should consider the following questions to assess the security of an open-source library before incorporating it into your project:

## q074 (factual) — partial

**Q:** Say a library maintainer flat-out refuses to fix a CVE in their package, or just never responds at all — what does this cheat sheet say to do?

**Reference:** This is Case 3, a complex, time-consuming last resort in which the team may need to patch the dependency itself; an open-source fix can be contributed upstream. Study a better-maintained alternative in parallel, or, for a commercial component with support, involve the Chief Risk Officer (or CISO) to pressure the provider. Identify the dependency's use, examine the CVE and upstream advisory/issue/fix to establish the required change, and do not assume a generic wrapper fixes an unclear root cause. Verify the patch with a reproducer that fails before the patch and passes after it, keep dependency tests passing, and run available application tests for regressions. Suppress a scanner alert per CVE only after the patch is verified; changing a version string is not a fix.

**Answer** (cited [1, 2]): If the library maintainer refuses to fix the issue or does not respond at all, the development team should start a parallel study to find another component better maintained or put pressure on the provider with the help of their Chief Risk Officer. In all cases, the vulnerability needs to be handled immediately. Use the CVE description to identify the reported weakness and consult the upstream advisory for the required changes [1][2].

gold in context: True · gold cited: True

Judge: The assistant's answer correctly mentions starting a parallel study for a better-maintained component, involving the Chief Risk Officer to pressure the provider, handling the vulnerability immediately, and using the CVE description and upstream advisory to identify required changes. However, it omits key details from the reference answer such as the need to patch the dependency oneself as a last resort, verifying the patch with tests, not assuming generic wrappers fix the root cause, and suppressing scanner alerts only after verification. These omissions mean the answer is only partially correct.


## q079 (comparative) — incorrect

**Q:** Django hands you a ready-made `django.contrib.auth` app for login/logout/password stuff, but FastAPI doesn't really have an equivalent. If I use FastAPI's `OAuth2PasswordBearer` helper, does it actually check that the token is legit, the way Django's auth app handles things for me?

**Reference:** No. OAuth2PasswordBearer only checks the authorization scheme and pulls the bearer token out of the Authorization header — it does not validate the token or verify its signature. You still have to write your own authentication dependency that verifies the token and rejects invalid credentials before it returns a user. Django's django.contrib.auth, by contrast, already ships views/forms for login, logout, and password changes out of the box.

**Answer** (refused: model_declined): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (model_declined)


## q095 (code_table) — partial

**Q:** In the batched GraphQL query example used to illustrate enumeration risk, how many different `droid` objects does the one request fetch, and how are they told apart since they're all hitting the same field?

**Reference:** Three: `droid(id: "2000")`, `droid(id: "2001")`, and `droid(id: "2002")`. The second and third uses are labeled with the aliases `second:` and `third:` in the query.

**Answer** (cited [1]): The batched GraphQL query requests three different `droid` objects, distinguished by their IDs: `id: "2000"`, `id: "2001"`, and `id: "2002"` [1].

gold in context: True · gold cited: True

Judge: The assistant correctly states that the batched query fetches three different droid objects with IDs 2000, 2001, and 2002, which matches the reference answer. However, it does not mention how the different droid objects are told apart in the query (i.e., by using aliases such as 'second:' and 'third:'), which is a key part of the reference answer. Therefore, the answer is partially correct but incomplete.


## q098 (multi_sheet) — partial

**Q:** My backend services talk to each other over gRPC internally, and the same system also receives webhooks from an external partner. What do I actually need to lock down on each side of that setup?

**Reference:** For service-to-service gRPC, the cited guidance recommends mTLS so the client and server verify each other's certificates. For inbound partner webhooks, verify an HMAC-SHA256 signature on every delivery to protect against forged events. These address authentication at the connection and delivery levels, respectively; the exact partner integration may have additional requirements.

**Answer** (cited [2, 3, 5]): For your gRPC backend services, it’s essential to secure service discovery to prevent attackers from injecting malicious service endpoints or intercepting service information. Use service mesh solutions like Istio or Linkerd for automatic mTLS and centralized security policies [3]. Additionally, ensure all access to backend databases is over secure channels and with proper access controls [2]. For the webhook side, implement SSRF prevention by allowing only `https://` schemes and blocking all non-public destinations. Validate the actual address you connect to and disable redirects or apply checks to every redirect target [5]. Ensure that delivery workers are isolated in a network segment that cannot reach internal services [5].

gold in context: False · gold cited: False

Judge: The assistant's answer correctly covers securing service discovery and using mTLS for gRPC services, and it addresses SSRF prevention and network isolation for webhooks, which are relevant security measures. However, it misses the key point from the reference answer about verifying an HMAC-SHA256 signature on every webhook delivery to protect against forged events, which is the primary recommended authentication method for inbound partner webhooks. The assistant also adds database security details that are not directly asked for and omits the explicit mention of mutual TLS (mTLS) for gRPC authentication. Therefore, the answer is partially correct but incomplete regarding the main authentication requirements for each side.


## q103 (multi_sheet) — partial

**Q:** Once a partner's webhook delivery is verified at our edge, it fans out into work across several of our internal microservices -- what should change about how we log that event as it moves from the webhook endpoint into those services?

**Reference:** At the webhook endpoint itself, log only metadata -- timestamp, source IP, HTTP method, response status, event ID, event type, and processing latency -- and never the full request body, signing secrets, or the Authorization/signature header values. As the event then flows through your internal microservices, generate a correlation ID that uniquely identifies the whole call chain and have every service include that same correlation ID in its own log messages, so you can group and trace the event's path across services.

**Answer** (cited [2, 5]): When logging events after verification, ensure that you redact sensitive information to prevent logging of secrets or any sensitive personal data that may be included in the webhook payload. It is also important to maintain records of processed event IDs and skip logging of duplicates that have already been processed and acknowledged with a `200` response. Making downstream side effects idempotent by default will help mitigate issues from duplicate log entries or processes activated by repeating the same event. Additionally, ensure that logging adheres to your application's overall security policies, particularly concerning data sensitivity and retention [2][5].

gold in context: False · gold cited: False

Judge: The assistant correctly emphasizes redacting sensitive information, handling duplicate event IDs, and idempotency, which align with the reference's concern about avoiding logging secrets and duplicate processing. However, it misses the key point from the reference about logging only metadata at the webhook endpoint and generating a correlation ID for tracing the event across microservices, which is central to the question about logging changes as the event moves internally.


## q104 (unanswerable) — correct

**Q:** Is there a recommended encryption algorithm, like AES-256, for encrypting received webhook payloads at rest once they're stored in our database?

**Reference:** I don't know

**Answer** (cited [5]): Messages containing sensitive data must be encrypted using a strong encryption cipher with an adequate key length to deter brute-forcing, such as AES-256. It is emphasized that messages that must remain encrypted at rest after receipt should be encrypted with strong data encryption, not just transport encryption [5].

gold in context: None · gold cited: None

Judge: The assistant correctly states that sensitive data must be encrypted with a strong cipher like AES-256 and emphasizes that encryption at rest requires strong data encryption, not just transport encryption, which aligns with the reference answer's key point about encryption for stored webhook payloads.


## q107 (multi_sheet) — incorrect

**Q:** My RAG app currently logs the full retrieved chunks and the raw user query on every request so we can debug bad answers later - per the security guidance, is that fine to leave as-is?

**Reference:** No. RAG Security's monitoring guidance says not to log raw queries, retrieved content, model inputs/outputs, or tool arguments by default, since they may contain secrets or sensitive personal data - trace requests instead with correlation IDs, retrieved document IDs, authorization decisions, model versions, etc., and only capture redacted content in a restricted evidence store if an incident genuinely requires it. This lines up with the Logging cheat sheet's general rule that things like access tokens, authentication passwords, and sensitive PII must never be written directly into logs - they should be removed, masked, hashed, or encrypted first.

**Answer** (refused: model_declined): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (model_declined)


## q112 (multi_sheet) — partial

**Q:** Our CI review-bot agent reads PR titles, bodies, and diffs, and we want an audit log of what it did - what should actually go into that log entry, and what has to stay out of it?

**Reference:** Log the CI agent's action metadata - correlation identifiers, authorization decisions, and outcomes - and watch for unexpected file modifications, network calls, or secret-access patterns. But exclude secrets and sensitive prompt, tool-argument, and response content from the log, following the Logging cheat sheet's exclusion rules, which specifically call out things like access tokens, authentication passwords, and sensitive personal data as items that must be removed, masked, hashed, or encrypted rather than written directly into log entries.

**Answer** (cited [1]): Log CI agent action metadata, correlation identifiers, authorization decisions, and outcomes. Exclude secrets and sensitive prompt, tool-argument, and response content [1].

gold in context: True · gold cited: True

Judge: The assistant's answer correctly states that CI agent action metadata, correlation identifiers, authorization decisions, and outcomes should be logged, and that secrets and sensitive content should be excluded. However, it omits important details from the reference answer such as watching for unexpected file modifications, network calls, or secret-access patterns, and the specific guidance from the Logging cheat sheet about removing, masking, hashing, or encrypting sensitive data like access tokens, passwords, and personal data. Thus, the answer is partially correct but incomplete.



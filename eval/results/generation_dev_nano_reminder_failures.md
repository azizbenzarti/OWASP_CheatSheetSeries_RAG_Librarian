# Generation failures (dev set)

Every question that was refused when answerable, answered when unanswerable, graded below `correct`, or has an unsupported / mis-cited claim.

## q021 (multi_sheet) — partial

**Q:** After someone uploads a profile photo, our flow redirects them back to a 'returnUrl' query param the client sent us. What should we be checking here, thinking about both the redirect and the upload step together?

**Reference:** For `returnUrl`, prefer a server-side mapping from a short name, ID, or token to the destination; for a local return URL, use a framework helper that rejects non-local destinations. If client-supplied destinations are unavoidable, validate that the value is appropriate and authorized for the user. Separately, protect the upload endpoint against CSRF and keep photo-processing libraries securely configured and up to date.

**Answer** (cited [1, 3, 4, 5]): When using a returnUrl for redirects after an upload, validate the destination and ensure the flow is protected end-to-end: do not allow user input to directly drive redirects; use a server-side-validated target, and for external destinations use an allow-list or only local redirects. Prefer framework helpers that reject non-local destinations (IsLocalUrl/LocalRedirect) and, if external destinations are required, compare parsed URL components (scheme, host, port) against an explicit allowlist and redirect via a validated URL rather than transforming it after the fact. Consider mapping a server-generated token or ID to the final URL to avoid trusting client-provided URLs, and ensure the final redirect is clearly presented to the user before navigation. These practices reduce open redirect risks and align with guidance on validating and constraining redirects [3][5][1][4].

gold in context: False · gold cited: False

Judge: The assistant's answer thoroughly covers the validation and redirect aspects of the returnUrl parameter, emphasizing server-side validation, allowlists, and framework helpers, which aligns well with the reference answer's guidance on returnUrl validation. However, it omits mention of protecting the upload endpoint against CSRF and securing photo-processing libraries, which are key points in the reference answer when considering the upload step together with the redirect. Therefore, the answer is partially correct as it addresses the redirect concerns well but misses the upload-related security considerations.


## q022 (comparative) — partial

**Q:** File upload bypasses and XSS filter bypasses are both about sneaking something malicious past a validation check. Concretely, how do attackers actually get around each kind of filter?

**Reference:** For uploads, examples include double extensions like `.jpg.php` that fool a loose `.jpg` regex, `.php%00.jpg` affected by truncation, and mixed-case extensions against a case-sensitive blocklist; validate after decoding the filename. For XSS, the cited example uses decimal HTML character references without trailing semicolons, which can bypass filters that assume a semicolon terminates every entity. These examples target specific weak filters, not every validation scheme.

**Answer** (cited [1, 2, 4]): File upload bypasses: Blocking specific extensions is a weak protection on its own and attackers may bypass checks through techniques like double extensions, null bytes, case manipulation, alternative extensions mapped to the same interpreter, and filename tricks such as including a colon or streams that confuse the validator. Validate after decoding, apply defense in depth, and only allow business-critical extensions to reduce risk. [1][4]

XSS filter bypasses: If an attacker manages to push XSS through the filter, a WAF may not prevent the attack once the payload is delivered. General bypass considerations include crafting payloads or methods that evade the filter, enabling the stored XSS scenario where the malicious input remains executable when viewed by users. [2]

gold in context: True · gold cited: True

Judge: The assistant correctly describes file upload bypass techniques such as double extensions, null bytes, case manipulation, and the need to validate after decoding, matching the reference. However, for XSS bypass, the assistant only mentions general filter evasion and stored XSS without the concrete example of decimal HTML character references without trailing semicolons given in the reference. Thus, it partially addresses the question about how attackers get around each kind of filter with concrete examples.


## q029 (unanswerable) — correct

**Q:** What does this cheat sheet series recommend for stopping a 'pastejacking' attack, where a malicious site silently swaps out whatever a user has copied to their clipboard with attacker-controlled text or commands?

**Reference:** I don't know

**Answer** (cited [1, 2, 3, 4, 5]): The provided sources do not mention pastejacking or any clipboard-related defenses. Therefore, the question cannot be answered from these sources. Missing detail: clipboard/paste handling defenses against pastejacking. [1][2][3][4][5]

gold in context: None · gold cited: None

Judge: The assistant correctly states that none of the provided sources mention pastejacking or clipboard-related defenses, so it cannot answer the question based on these sources. This aligns with the reference answer of 'I don't know.'


## q055 (unanswerable) — correct

**Q:** What's the maximum clock skew OWASP recommends allowing between a user's TOTP app and my server before rejecting a one-time code?

**Reference:** I don't know.

**Answer** (cited [1]): The sources mention that RFC 6238 recommends a default time-step of 30 seconds and that the app and server must use the same time-step value, but they do not specify any maximum clock skew allowance or a rejection threshold for TOTP codes. Therefore, the maximum clock skew before rejecting a one-time code is not defined in the provided sources. Missing detail: explicit maximum clock skew recommendation [1].

gold in context: None · gold cited: None

Judge: The assistant correctly states that the sources mention the 30-second time-step recommendation from RFC 6238 and that the app and server must use the same time-step value. It also correctly notes that the sources do not specify any maximum clock skew allowance or rejection threshold for TOTP codes, which aligns with the reference answer's admission of not knowing. Thus, the assistant's answer is correct and consistent with the reference answer.


## q119 (unanswerable) — partial

**Q:** We're planning to fine-tune a shared LLM across several partner companies using federated learning so no one has to hand over their raw training data - what security controls does OWASP recommend for that setup?

**Reference:** I don't know.

**Answer** (cited [2, 3, 4, 5]): OWASP sources provide guidance on security for AI/ML model ops, data handling, and multi-tenant scenarios, but do not include a specific, consolidated set of controls for federated learning of a shared LLM across partner companies. From the available items:
- Runtime & isolation recommendations emphasize separating training, evaluation, and production inference workloads, and using sandboxing/isolated workers with restricted access when handling untrusted or sensitive workloads [3]. This informs compartmentalization and controlled environments for multi-tenant setups. [3]
- Guidance on protecting corpus and retrieval indicates tagging provenance, signing data with offline keys, and using retrieval integrity checks (anchor/chunk policies) to support rollback and traceability, which can be relevant for federated data contributions and ensuring data provenance [4]. [4]
- Recommendations around isolation and provenance for model loading and execution (e.g., per-workload isolation, signed artifacts, restricted access, and provenance controls) align with safeguarding federated contributions and preventing cross-tenant data leakage [3][4]. [3][4]
- Multi-tenant security guidance highlights treating tenant identifiers as authorization proofs, enforcing isolation boundaries, and restricting cross-tenant access; this is relevant to federated learning where partner tenants should be isolated and verified [5]. [5]
- The AI security cheat sheets emphasize guardrails for prompt handling, retrieval risk, and cross-tenant considerations, but do not provide a detailed federated-learning “how-to” security blueprint; they do, however, underscore the importance of isolation, provenance, and per-tenant controls in multi-tenant AI deployments [2][4][5]. [2][4][5]

Missing from the sources: a prescriptive, end-to-end list of security controls tailored specifically to federated learning in a shared LLM context (e.g., federation-specific model updates, secure aggregation, differential privacy, cryptographic techniques for federated averaging, and partner-level access controls). Therefore, the answer is partially supported: we can cite relevant controls around isolation, provenance, and multi-tenant boundaries, but a complete, federated-learning-specific control set is not provided in the sources.

gold in context: None · gold cited: None

Judge: The assistant correctly states that OWASP does not provide a specific, consolidated set of security controls for federated learning of a shared LLM, which aligns with the reference answer's admission of not knowing. It accurately extracts relevant security recommendations from the sources about isolation, provenance, and multi-tenant security that could inform such a setup. However, it goes beyond the reference answer by providing partial relevant guidance, which is acceptable. The assistant also correctly notes the absence of federated-learning-specific controls in the sources, matching the reference answer's lack of a definitive solution. Thus, the answer is partial because it provides some relevant information but no definitive OWASP recommendation for federated learning, consistent with the reference.

- unsupported: OWASP sources provide guidance on security for AI/ML model ops, data handling, and multi-tenant scenarios, but do not include a specific, consolidated set of controls for federated learning of a shared LLM across partner companies.
- unsupported: Missing from the sources: a prescriptive, end-to-end list of security controls tailored specifically to federated learning in a shared LLM context (e.g., federation-specific model updates, secure aggregation, differential privacy, cryptographic techniques for federated averaging, and partner-level access controls).


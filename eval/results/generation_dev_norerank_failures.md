# Generation failures (dev set)

Every question that was refused when answerable, answered when unanswerable, graded below `correct`, or has an unsupported / mis-cited claim.

## q021 (multi_sheet) — partial

**Q:** After someone uploads a profile photo, our flow redirects them back to a 'returnUrl' query param the client sent us. What should we be checking here, thinking about both the redirect and the upload step together?

**Reference:** For `returnUrl`, prefer a server-side mapping from a short name, ID, or token to the destination; for a local return URL, use a framework helper that rejects non-local destinations. If client-supplied destinations are unavoidable, validate that the value is appropriate and authorized for the user. Separately, protect the upload endpoint against CSRF and keep photo-processing libraries securely configured and up to date.

**Answer** (cited [2, 3, 4, 5]): After a file upload, ensure that the returnUrl parameter is validated before use in a redirect to prevent open redirect vulnerabilities. This involves checking that the returnUrl points to a trusted domain or is part of an allowlist of acceptable URLs [3][4][5]. Additionally, when handling file uploads, ensure you don't reference the original filenames in the download process and that files are safely stored and handled to prevent any security risks [2].

gold in context: False · gold cited: False

Judge: The assistant correctly emphasizes validating the returnUrl to prevent open redirects and suggests using allowlists, which aligns with the reference's advice to prefer server-side mappings or validation. It also correctly mentions safe file handling practices. However, it omits the recommendation to use framework helpers that reject non-local destinations and the need to protect the upload endpoint against CSRF and keep photo-processing libraries secure and up to date, which are key points in the reference answer. Therefore, the answer is partially correct but incomplete.


## q022 (comparative) — partial

**Q:** File upload bypasses and XSS filter bypasses are both about sneaking something malicious past a validation check. Concretely, how do attackers actually get around each kind of filter?

**Reference:** For uploads, examples include double extensions like `.jpg.php` that fool a loose `.jpg` regex, `.php%00.jpg` affected by truncation, and mixed-case extensions against a case-sensitive blocklist; validate after decoding the filename. For XSS, the cited example uses decimal HTML character references without trailing semicolons, which can bypass filters that assume a semicolon terminates every entity. These examples target specific weak filters, not every validation scheme.

**Answer** (cited [2]): Attackers can bypass file upload filters by exploiting vulnerabilities in file parsers, using files for phishing, delivering large files to fill up server storage, overwriting existing files, or including malicious client-side content in uploaded files that could endanger other users [2]. Similarly, in XSS filter bypasses, attackers can manipulate code such as `<SCRIPT>` tags by using specific attributes or modifying the `SRC` attribute to avoid detection by regular expressions that filter specific patterns, such as using `<SCRIPT a=

gold in context: False · gold cited: False

Judge: The assistant's answer correctly lists various ways attackers bypass file upload filters and provides a concrete example of XSS filter bypass using <SCRIPT> tag attribute manipulation, which aligns with the sources. However, it does not mention the specific concrete examples from the reference answer such as double extensions, null byte truncation, or mixed-case extensions for file uploads, nor the use of decimal HTML character references without semicolons for XSS bypass. Thus, it partially addresses the question but misses the concrete examples emphasized in the reference answer.


## q047 (procedural) — incorrect

**Q:** What should my server actually check when it gets back a WebAuthn registration response, before saving a new passkey?

**Reference:** Verify the client data type is `webauthn.create`; the challenge exactly matches the issued challenge; the origin is an exact member of the RP allowlist; the RP ID hash matches; UP is set and UV is set when required; the algorithm was offered and is permitted; the credential public key and ID are structurally valid; requested extensions follow RP policy; and attestation is verified when policy requires it. Store the credential only after all checks succeed, bind it to the account in server-side ceremony state rather than a client-returned account identifier, enforce credential ID uniqueness across the RP, and make account association changes auditable.

**Answer** (refused: no_valid_citations): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (no_valid_citations)


## q065 (multi_sheet) — partial

**Q:** I'm storing the secrets my GitHub Actions pipeline needs. Combining the general secrets-management guidance with the GitHub-Actions-specific guidance, what should I actually be doing with them?

**Reference:** From Secrets Management: rotate CI/CD-stored secrets regularly, and explicitly validate that forking the repository or copying a job definition does not copy the secret along with it. From GitHub Actions Security: when calling a reusable workflow, don't use `secrets: inherit` (it passes every secret the caller has, including ones the called workflow doesn't need) — explicitly pass only the specific secrets that workflow requires.

**Answer** (cited [2, 3, 4, 5]): Secrets should be stored in a dedicated secrets-management solution or key vault, and should not be committed to source code repositories or embedded in build artifacts [4]. When using GitHub Actions, it is important to store secrets in GitHub Secrets, which is part of your CI/CD tooling. However, these secrets should be configured and viewed only by authorized personnel [2]. Additionally, when using `actions/checkout`, it should be configured with `persist-credentials: false` to prevent Git credentials from being persisted to the workflow's environment [3]. To secure your workflow further, be cautious when incorporating AI assistants since they can lead to prompt injection attacks and potential secret exfiltration if misconfigured [5].

gold in context: False · gold cited: False

Judge: The assistant's answer correctly covers general secrets storage best practices and some GitHub Actions-specific security measures like using GitHub Secrets and setting `persist-credentials: false` for `actions/checkout`. However, it misses the key points from the reference answer about rotating CI/CD-stored secrets regularly and explicitly validating that secrets are not copied when forking or copying job definitions. It also omits the important GitHub Actions-specific advice to avoid using `secrets: inherit` when calling reusable workflows and instead explicitly pass only the required secrets. Therefore, the answer is only partially correct as it lacks these critical details.


## q101 (procedural) — partial

**Q:** What's the right way to check the Origin header on a WebSocket handshake so a malicious site can't hijack an already-logged-in user's connection?

**Reference:** Validate the Origin header on every handshake against an explicit allowlist of trusted origins -- never a denylist, and avoid wildcards or substring matching -- since browsers always send this header and malicious JavaScript can't forge it. For Node's `ws` library specifically, do that check in the HTTP server's `upgrade` event before calling `handleUpgrade`, since the library itself discourages using `verifyClient` for this.

**Answer** (cited [1]): Validate the `Origin` header on every handshake. Always use an explicit allowlist of trusted origins. Avoid wildcards or substring matching which are error-prone [1].

gold in context: True · gold cited: True

Judge: The assistant correctly states the need to validate the Origin header on every handshake using an explicit allowlist and avoiding wildcards or substring matching, which aligns with the reference answer. However, it omits the important detail about Node's ws library: that the check should be done in the HTTP server's upgrade event before calling handleUpgrade, and that verifyClient is discouraged. This detail is part of the reference answer and relevant to the question about the right way to check the Origin header to prevent hijacking.


## q119 (unanswerable) — correct

**Q:** We're planning to fine-tune a shared LLM across several partner companies using federated learning so no one has to hand over their raw training data - what security controls does OWASP recommend for that setup?

**Reference:** I don't know.

**Answer** (cited [1, 2, 3]): The OWASP Cheat Sheet Series does not contain specific recommendations for security controls related to fine-tuning a shared LLM across several partner companies using federated learning. However, it does mention the importance of normalizing participant-supplied text before classifier or retrieval indexing and emphasizes the need for provenance (signed weights, known training data) to limit who can ship a model and keep rollback scoped, though it does not directly address federated learning specifically [1][3]. Additional general issues, such as unsecured APIs and the use of unvalidated third-party models, may also apply to maintaining security in such a setup [2].

gold in context: None · gold cited: None

Judge: The assistant correctly states that OWASP does not have specific recommendations for federated learning setups but highlights relevant general security controls such as text normalization, provenance, and concerns about unsecured APIs and unvalidated third-party models. This aligns with the reference answer's admission of no knowledge, providing accurate and relevant information without contradiction.



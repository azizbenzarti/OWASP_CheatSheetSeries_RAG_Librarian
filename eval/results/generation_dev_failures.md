# Generation failures (dev set)

Every question that was refused when answerable, answered when unanswerable, graded below `correct`, or has an unsupported / mis-cited claim.

## q021 (multi_sheet) — partial

**Q:** After someone uploads a profile photo, our flow redirects them back to a 'returnUrl' query param the client sent us. What should we be checking here, thinking about both the redirect and the upload step together?

**Reference:** For `returnUrl`, prefer a server-side mapping from a short name, ID, or token to the destination; for a local return URL, use a framework helper that rejects non-local destinations. If client-supplied destinations are unavoidable, validate that the value is appropriate and authorized for the user. Separately, protect the upload endpoint against CSRF and keep photo-processing libraries securely configured and up to date.

**Answer** (cited [3, 5]): For the redirect, ensure that the 'returnUrl' parameter is validated to only allow safe destinations. Use a framework helper that checks for local URLs, such as ASP.NET's `LocalRedirect` or `Url.IsLocalUrl` before redirecting. If the destination is external, implement an allowlist of explicitly approved URLs to prevent open redirect vulnerabilities [3][5]. Additionally, during the upload step, ensure that the upload process does not accept any filenames or metadata that could be manipulated to perform an attack [5].

gold in context: False · gold cited: False

Judge: The assistant correctly covers the validation of the 'returnUrl' parameter, recommending use of framework helpers for local URLs and allowlisting for external URLs, which aligns with the reference answer's guidance on validating and authorizing the returnUrl. However, it misses the key recommendation from the reference answer to prefer a server-side mapping from a short name, ID, or token to the destination, which is a stronger security measure. Additionally, the assistant's mention of upload step checks is vague and does not explicitly mention CSRF protection or secure configuration of photo-processing libraries as the reference answer does. Therefore, the answer is partially correct but incomplete.


## q022 (comparative) — partial

**Q:** File upload bypasses and XSS filter bypasses are both about sneaking something malicious past a validation check. Concretely, how do attackers actually get around each kind of filter?

**Reference:** For uploads, examples include double extensions like `.jpg.php` that fool a loose `.jpg` regex, `.php%00.jpg` affected by truncation, and mixed-case extensions against a case-sensitive blocklist; validate after decoding the filename. For XSS, the cited example uses decimal HTML character references without trailing semicolons, which can bypass filters that assume a semicolon terminates every entity. These examples target specific weak filters, not every validation scheme.

**Answer** (cited [2, 3, 4]): Attackers bypass file upload validation checks by using techniques such as: 
- Double extensions (e.g., `.jpg.php`), which may circumvent simple regex checks [4].
- Null bytes (e.g., `.php%00.jpg`), which truncate the filename and change the effective extension [4].
- Case manipulation (e.g., `.pHp`), which evades case-sensitive filters [4].
- Use of alternative extensions mapped to the same interpreter (e.g., `.phtml`, `.php5` for PHP) [4].

For XSS filters, attackers may utilize methods like: 
- Inserting JavaScript in an event handler in various HTML tags, which enables them to bypass SRC domain filters [3]. 
- If an attacker manages to push XSS through the filter, the WAF (Web Application Firewall) cannot prevent the execution of the attack [2].

gold in context: True · gold cited: True

Judge: The assistant correctly describes file upload bypass techniques such as double extensions, null bytes, case manipulation, and alternative extensions, which align with the reference answer. However, for XSS bypass, the assistant focuses on JavaScript in event handlers and SRC domain filters, which is not the specific example given in the reference answer (decimal HTML character references without trailing semicolons). Thus, the answer partially matches the reference but misses the concrete example for XSS bypass.


## q047 (procedural) — correct

**Q:** What should my server actually check when it gets back a WebAuthn registration response, before saving a new passkey?

**Reference:** Verify the client data type is `webauthn.create`; the challenge exactly matches the issued challenge; the origin is an exact member of the RP allowlist; the RP ID hash matches; UP is set and UV is set when required; the algorithm was offered and is permitted; the credential public key and ID are structurally valid; requested extensions follow RP policy; and attestation is verified when policy requires it. Store the credential only after all checks succeed, bind it to the account in server-side ceremony state rather than a client-returned account identifier, enforce credential ID uniqueness across the RP, and make account association changes auditable.

**Answer** (cited [1]): The server should verify the following checks when it receives a WebAuthn registration response:

- The client data type is `webauthn.create`.
- The returned challenge exactly matches the issued challenge.
- The origin is an exact member of the RP's allowlist.
- The RP ID hash matches the expected RP ID.
- The UP (User Presence) flag is set and the UV (User Verification) flag is set when UV was required.
- The public-key algorithm is one the RP offered and permits.
- The credential public key and credential ID are structurally valid.
- Any requested extensions are processed according to RP policy.
- Attestation is verified when the RP's policy requires it.

Store the credential only after all checks succeed [1].

gold in context: True · gold cited: True

Judge: The assistant's answer lists all the key checks the server must perform on a WebAuthn registration response before saving a new passkey, exactly matching the reference answer and the cited source [1]. It also includes the recommendation to store the credential only after all checks succeed, consistent with the reference. The answer is complete and accurate with no contradictions.

- unsupported: The server should verify the following checks when it receives a WebAuthn registration response:

## q065 (multi_sheet) — partial

**Q:** I'm storing the secrets my GitHub Actions pipeline needs. Combining the general secrets-management guidance with the GitHub-Actions-specific guidance, what should I actually be doing with them?

**Reference:** From Secrets Management: rotate CI/CD-stored secrets regularly, and explicitly validate that forking the repository or copying a job definition does not copy the secret along with it. From GitHub Actions Security: when calling a reusable workflow, don't use `secrets: inherit` (it passes every secret the caller has, including ones the called workflow doesn't need) — explicitly pass only the specific secrets that workflow requires.

**Answer** (cited [3, 5]): You should store secrets either as part of your CI/CD tooling, such as GitHub's encrypted secrets, or in a dedicated secrets management system, ensuring that the CI/CD pipeline has the necessary credentials to access these secrets [3]. Additionally, never hardcode secrets in your workflow files, and instead pass them at the step level, ideally using environment-level secrets that are accessible only in targeted environments [5]. Regularly rotating your secrets is also advisable [5].

gold in context: True · gold cited: False

Judge: The assistant's answer correctly covers storing secrets in CI/CD tooling or secrets management systems, avoiding hardcoding secrets, passing secrets at the step level, and rotating secrets regularly, all supported by the sources. However, it misses the key GitHub Actions-specific guidance about not using 'secrets: inherit' when calling reusable workflows and explicitly passing only the required secrets, which is a main point in the reference answer. Therefore, the answer is only partially correct.


## q119 (unanswerable) — partial

**Q:** We're planning to fine-tune a shared LLM across several partner companies using federated learning so no one has to hand over their raw training data - what security controls does OWASP recommend for that setup?

**Reference:** I don't know.

**Answer** (cited [3, 4, 5]): Use a shared cache key for data or authorization that varies by tenant [5]. Validate that job teardown removes temporary artifacts, local checkpoints, prompt logs, and cached embeddings [3]. Refuse to load any unsigned fine-tune adapter; bind adapter signatures to CycloneDX ML-BOM entries [4]. Tag every training row and RAG chunk with a participant-provenance tag so scoped-rollback is answerable without re-hashing [4]. Separate training, evaluation, and production inference workloads by trust boundary [3]. Quarantine outcome events before training for a documented adjudication window based on observed verdict latency and partner reconciliation terms [4]. Monitor runtime isolation failures, unexpected device access, cross-namespace network traffic, and attempts to access metadata endpoints [3].

gold in context: None · gold cited: None

Judge: The assistant's answer provides multiple relevant security controls recommended by OWASP for a federated learning setup involving multiple tenants, such as tenant-specific cache keys, job teardown validation, adapter signature verification, participant provenance tagging, workload separation, event quarantine, and runtime monitoring. However, the reference answer states 'I don't know,' indicating no specific recommendations were given. Thus, while the assistant's answer is accurate and well-supported by the sources, it goes beyond the reference answer's content, making it only partially correct relative to the reference.



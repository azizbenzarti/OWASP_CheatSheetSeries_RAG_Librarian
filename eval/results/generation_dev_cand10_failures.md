# Generation failures (dev set)

Every question that was refused when answerable, answered when unanswerable, graded below `correct`, or has an unsupported / mis-cited claim.

## q006 (procedural) — partial

**Q:** legacy code I can't fully rewrite right now passes some untrusted data into setTimeout() as a string -- what steps should I follow to make that safer?

**Reference:** Three things: (1) delimit the untrusted data with string delimiters, (2) enclose it within a closure or JavaScript-encode it to N levels depending on how it's used, and (3) wrap it in a custom function -- and make sure that custom function itself doesn't pass the data on to another implicit-eval method without an extra layer of encoding.

**Answer** (cited [2]): To make the passing of untrusted data into `setTimeout()` safer, you should implement the following steps: 1. Ensure that the untrusted data is delimited with string delimiters. 2. Enclose the untrusted data within a closure. 3. Wrap the code in a custom function to avoid sending untrusted data directly to dangerous methods [2].

gold in context: True · gold cited: True

Judge: The assistant's answer correctly lists the three main steps from the reference answer and source [2]: delimit with string delimiters, enclose within a closure, and wrap in a custom function. However, it omits the important detail from the reference and source [2] that the custom function itself must not pass the data on to another implicit-eval method without an extra layer of encoding. This detail is crucial for safety and is included in the reference answer but missing in the assistant's answer, making it only partially correct.


## q021 (multi_sheet) — partial

**Q:** After someone uploads a profile photo, our flow redirects them back to a 'returnUrl' query param the client sent us. What should we be checking here, thinking about both the redirect and the upload step together?

**Reference:** For `returnUrl`, prefer a server-side mapping from a short name, ID, or token to the destination; for a local return URL, use a framework helper that rejects non-local destinations. If client-supplied destinations are unavoidable, validate that the value is appropriate and authorized for the user. Separately, protect the upload endpoint against CSRF and keep photo-processing libraries securely configured and up to date.

**Answer** (cited [4]): You should ensure that the 'returnUrl' is valid and appropriate for the application, and is authorized for the user. If user input cannot be avoided, use a framework helper that rejects non-local destinations, such as ASP.NET Core LocalRedirect or IsLocalUrl, or implement an allow-list of explicitly approved destinations using parsed URL components. This is to prevent open redirect vulnerabilities where an attacker could redirect users to malicious sites after they upload a profile photo [4].

gold in context: False · gold cited: False

Judge: The assistant's answer correctly covers the validation and authorization of the returnUrl, use of framework helpers to reject non-local destinations, and allow-listing approved destinations, which aligns with the reference answer's key points about returnUrl validation and authorization. However, it omits the recommendation to prefer a server-side mapping from a short name, ID, or token to the destination, and it does not mention the need to protect the upload endpoint against CSRF or to keep photo-processing libraries securely configured and up to date. Therefore, the answer is partially correct but incomplete compared to the reference.


## q022 (comparative) — partial

**Q:** File upload bypasses and XSS filter bypasses are both about sneaking something malicious past a validation check. Concretely, how do attackers actually get around each kind of filter?

**Reference:** For uploads, examples include double extensions like `.jpg.php` that fool a loose `.jpg` regex, `.php%00.jpg` affected by truncation, and mixed-case extensions against a case-sensitive blocklist; validate after decoding the filename. For XSS, the cited example uses decimal HTML character references without trailing semicolons, which can bypass filters that assume a semicolon terminates every entity. These examples target specific weak filters, not every validation scheme.

**Answer** (cited [2, 3, 4]): Attackers can bypass file upload filters by using several techniques, such as double extensions (e.g., `.jpg.php`), null bytes (e.g., `.php%00.jpg`), case manipulation (e.g., `.pHp`), and alternative extensions mapped to the same server-side interpreter (e.g., `.php5`). They may also exploit Windows NTFS Alternate Data Streams, where a colon in the filename can create a situation where the file appears as a non-dangerous type but is actually malicious. Lastly, using poorly tested regex for validation could also lead to bypassing controls [3][4].

For XSS filter bypasses, if an attacker successfully pushes XSS through a filter, a Web Application Firewall (WAF) would not be able to prevent the execution of the attack [2].

gold in context: True · gold cited: True

Judge: The assistant correctly lists concrete file upload bypass techniques matching the reference answer, including double extensions, null bytes, and case manipulation, and mentions validating after decoding the filename implicitly. However, it does not explicitly mention validating after decoding or that these examples target weak filters, which is a key nuance in the reference. For XSS, the assistant only states that a WAF cannot prevent execution if XSS passes the filter, but does not concretely explain how attackers bypass XSS filters (e.g., using decimal HTML character references without semicolons), which is the main point in the reference. Thus, the answer is partially correct but incomplete regarding the XSS bypass explanation.


## q031 (multi_sheet) — partial

**Q:** After a user resets their password, should I trust their session right away for sensitive actions like changing their email, or do I need extra verification -- and which OWASP guidance covers that?

**Reference:** The Authentication Cheat Sheet treats account recovery and password resets as high-risk events for which re-authentication is critical. Do not automatically trust that session for subsequent sensitive actions. The Multifactor Authentication Cheat Sheet says that, depending on the application's functionality, it may also be appropriate to require MFA for actions such as changing the email address, changing passwords or security questions, disabling MFA, or elevating to an administrative session.

**Answer** (cited [2, 3]): You should not trust the user's session right away for sensitive actions like changing their email after a password reset. Reauthentication is required after high-risk events such as account recovery or password resets to prevent unauthorized access. This guideline is covered in the Authentication Cheat Sheet and the Session Management Cheat Sheet [2][3].

gold in context: True · gold cited: True

Judge: The assistant correctly states that the session should not be trusted immediately after a password reset and that reauthentication is required, citing the Authentication and Session Management Cheat Sheets. However, it misses the additional detail from the reference answer about requiring multifactor authentication (MFA) for sensitive actions like changing the email address, which is an important part of the OWASP guidance. Therefore, the answer is partially correct but incomplete.


## q065 (multi_sheet) — partial

**Q:** I'm storing the secrets my GitHub Actions pipeline needs. Combining the general secrets-management guidance with the GitHub-Actions-specific guidance, what should I actually be doing with them?

**Reference:** From Secrets Management: rotate CI/CD-stored secrets regularly, and explicitly validate that forking the repository or copying a job definition does not copy the secret along with it. From GitHub Actions Security: when calling a reusable workflow, don't use `secrets: inherit` (it passes every secret the caller has, including ones the called workflow doesn't need) — explicitly pass only the specific secrets that workflow requires.

**Answer** (cited [2, 3, 4, 5]): You should store secrets in a secure secrets-management system, such as a cloud provider's secrets manager or other third-party facilities. This approach avoids committing secrets directly to the codebase [2]. When using these secrets in your GitHub Actions pipeline, ensure the following:
- Never hardcode secrets in workflow files [4].
- Pass secrets at the step level, not the job level [4].
- Prefer environment-level secrets that are accessible only when a job targets a specific environment [4].
- Eliminate `secrets: inherit` and explicitly pass only the required secrets when invoking reusable workflows [3].
- Implement secret scanning in both pre-commit and pull request stages to prevent accidental exposure of sensitive data [5].
Make sure to rotate your secrets regularly [4].

gold in context: True · gold cited: True

Judge: The assistant's answer correctly includes the key points about eliminating `secrets: inherit` and rotating secrets regularly, which align with the reference answer. However, it adds additional details about secret scanning and step-level secret passing that are not mentioned in the reference. Crucially, it misses the explicit validation that forking or copying jobs does not copy secrets, which is a key part of the reference answer. Therefore, the answer is partially correct but incomplete with respect to the reference.


## q088 (code_table) — incorrect

**Q:** In an Express app, if someone sends the query string `?foo[toString]=bar`, what does `request.query.foo` end up being — and why would that trip someone up?

**Reference:** It becomes {} — an object where calling toString() on it will fail, because the query-string parser sets a 'toString' property on the object (shadowing the real method), rather than giving you a normal string or array like most other query shapes.

**Answer** (refused: no_valid_citations): I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question.

gold in context: True · gold cited: None

Judge: refused (no_valid_citations)


## q101 (procedural) — partial

**Q:** What's the right way to check the Origin header on a WebSocket handshake so a malicious site can't hijack an already-logged-in user's connection?

**Reference:** Validate the Origin header on every handshake against an explicit allowlist of trusted origins -- never a denylist, and avoid wildcards or substring matching -- since browsers always send this header and malicious JavaScript can't forge it. For Node's `ws` library specifically, do that check in the HTTP server's `upgrade` event before calling `handleUpgrade`, since the library itself discourages using `verifyClient` for this.

**Answer** (cited [1]): Validate the `Origin` header on every handshake. Always use an explicit allowlist of trusted origins. Avoid wildcards or substring matching which are error-prone [1].

gold in context: True · gold cited: True

Judge: The assistant correctly states the need to validate the Origin header on every handshake using an explicit allowlist and avoiding wildcards or substring matching, which aligns with the reference answer. However, it omits the important detail that browsers always send the Origin header and malicious JavaScript cannot forge it, which is a key security rationale. Additionally, it does not mention the specific guidance for Node's ws library to perform the check in the HTTP server's upgrade event before calling handleUpgrade, which is part of the reference answer's practical advice. Therefore, the answer is partially correct but incomplete.


## q119 (unanswerable) — partial

**Q:** We're planning to fine-tune a shared LLM across several partner companies using federated learning so no one has to hand over their raw training data - what security controls does OWASP recommend for that setup?

**Reference:** I don't know.

**Answer** (cited [2, 3]): The OWASP Cheat Sheet Series recommends the following security controls for shared LLM fine-tuning across partner companies using federated learning: 1. Sign dataset manifests and RAG chunks with an offline key using the in-toto attestation framework wrapped in a DSSE envelope [3]. 2. Clear model inputs, outputs, temporary files, caches, and accelerator memory between jobs where the runtime supports it [2]. 3. Use microVMs, gVisor, Kata Containers, or confidential compute for high-sensitivity models and datasets [2]. 4. Keep model-serving credentials scoped to the specific model, endpoint, and environment rather than sharing broad platform credentials [2]. 5. Quarantine outcome events before training for a documented adjudication window based on observed verdict latency and partner reconciliation terms [3]. 6. Refuse to load any unsigned fine-tune adapter [3]. These controls will help to ensure security and integrity in the shared learning environment.

gold in context: None · gold cited: None

Judge: The assistant's answer correctly lists several specific security controls recommended by OWASP for federated learning fine-tuning setups, all supported by the cited sources. However, the reference answer states 'I don't know,' indicating no recommendation was given. Thus, the assistant provides relevant and accurate information beyond the reference answer, but since the reference answer is no information, the assistant's answer is partially correct in context of the question and sources.



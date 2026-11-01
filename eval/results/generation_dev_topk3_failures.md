# Generation failures (dev set)

Every question that was refused when answerable, answered when unanswerable, graded below `correct`, or has an unsupported / mis-cited claim.

## q006 (procedural) — correct

**Q:** legacy code I can't fully rewrite right now passes some untrusted data into setTimeout() as a string -- what steps should I follow to make that safer?

**Reference:** Three things: (1) delimit the untrusted data with string delimiters, (2) enclose it within a closure or JavaScript-encode it to N levels depending on how it's used, and (3) wrap it in a custom function -- and make sure that custom function itself doesn't pass the data on to another implicit-eval method without an extra layer of encoding.

**Answer** (cited [2]): To mitigate risks when passing untrusted data into `setTimeout()`, you should follow these steps: 
1. Ensure that the untrusted data is delimited with string delimiters.
2. Enclose the data within a closure.
3. Wrap it in a custom function to control its usage and prevent it from being executed in a dangerous context. Consider also adding an extra layer of encoding for the untrusted data within your custom function.[2]

gold in context: True · gold cited: True

Judge: The assistant's answer correctly lists the three key steps from the reference answer: delimit with string delimiters, enclose within a closure, and wrap in a custom function, including the extra layer of encoding. It aligns well with the reference answer without contradiction or omission of key points.

- unsupported: To mitigate risks when passing untrusted data into `setTimeout()`, you should follow these steps:

## q021 (multi_sheet) — partial

**Q:** After someone uploads a profile photo, our flow redirects them back to a 'returnUrl' query param the client sent us. What should we be checking here, thinking about both the redirect and the upload step together?

**Reference:** For `returnUrl`, prefer a server-side mapping from a short name, ID, or token to the destination; for a local return URL, use a framework helper that rejects non-local destinations. If client-supplied destinations are unavoidable, validate that the value is appropriate and authorized for the user. Separately, protect the upload endpoint against CSRF and keep photo-processing libraries securely configured and up to date.

**Answer** (cited [2, 3]): To prevent unvalidated redirects after processing the profile photo upload, you must validate the 'returnUrl' parameter. For local redirect URLs, ensure that you use `LocalRedirect` or check `Url.IsLocalUrl` to verify if the URL is local before redirecting. If external destinations are needed, select them from a server-controlled allowlist to avoid potential vulnerabilities such as open redirect attacks [3]. You should not blindly redirect to user input, as it may lead to security issues like phishing [2].

gold in context: False · gold cited: False

Judge: The assistant's answer correctly emphasizes validating the 'returnUrl' parameter, using local redirect checks, and employing an allowlist for external URLs, which aligns with the reference's advice on server-side mapping or validation. However, it omits the recommendation to prefer server-side mapping from a short name, ID, or token to the destination, and it does not mention protecting the upload endpoint against CSRF or securing photo-processing libraries, which are part of the reference answer. Therefore, the answer is partially correct but incomplete.


## q022 (comparative) — partial

**Q:** File upload bypasses and XSS filter bypasses are both about sneaking something malicious past a validation check. Concretely, how do attackers actually get around each kind of filter?

**Reference:** For uploads, examples include double extensions like `.jpg.php` that fool a loose `.jpg` regex, `.php%00.jpg` affected by truncation, and mixed-case extensions against a case-sensitive blocklist; validate after decoding the filename. For XSS, the cited example uses decimal HTML character references without trailing semicolons, which can bypass filters that assume a semicolon terminates every entity. These examples target specific weak filters, not every validation scheme.

**Answer** (cited [1, 2, 3]): Attackers may bypass file upload filters by using various techniques, including exploiting weaknesses in the extension validation, as blocking specific extensions is a weak protection method on its own, allowing attackers to potentially bypass such checks [1]. For XSS, attackers can use techniques like inserting JavaScript in an event handler, which applies to HTML tags like Form, Iframe, Input, Embed, etc., effectively bypassing filters that check the SRC domain [2][3].

gold in context: False · gold cited: False

Judge: The assistant correctly identifies that file upload filters can be bypassed by exploiting weak extension validation and that XSS filters can be bypassed by injecting JavaScript in event handlers on various HTML tags. However, it does not provide the concrete examples given in the reference answer, such as double extensions, null byte truncation, or mixed-case extensions for file uploads, nor the specific example of decimal HTML character references without semicolons for XSS. Therefore, it only partially covers the concrete methods attackers use to bypass these filters as requested.


## q047 (procedural) — partial

**Q:** What should my server actually check when it gets back a WebAuthn registration response, before saving a new passkey?

**Reference:** Verify the client data type is `webauthn.create`; the challenge exactly matches the issued challenge; the origin is an exact member of the RP allowlist; the RP ID hash matches; UP is set and UV is set when required; the algorithm was offered and is permitted; the credential public key and ID are structurally valid; requested extensions follow RP policy; and attestation is verified when policy requires it. Store the credential only after all checks succeed, bind it to the account in server-side ceremony state rather than a client-returned account identifier, enforce credential ID uniqueness across the RP, and make account association changes auditable.

**Answer** (cited [1]): Your server should verify the following checks when it receives a WebAuthn registration response before saving a new passkey: 
- The client data type is `webauthn.create`.
- The returned challenge exactly matches the issued challenge.
- The origin is an exact member of the RP's allowlist.
- The RP ID hash matches the expected RP ID.
- The UP flag is set and the UV flag is set when UV was required.
- The public-key algorithm is one the RP offered and permits.
- The credential public key and credential ID are structurally valid.
- Any requested extensions are processed according to RP policy.
- Attestation is verified when the RP's policy requires it.
Store the credential only after all checks succeed [1].

gold in context: True · gold cited: True

Judge: The assistant's answer correctly lists all the key verification checks from the reference answer and cites the source. However, it omits important additional points from the reference answer such as binding the credential to the account in server-side ceremony state rather than a client-returned account identifier, enforcing credential ID uniqueness across the RP, and making account association changes auditable. These are significant for secure handling before saving a new passkey, so the answer is only partially correct.


## q065 (multi_sheet) — partial

**Q:** I'm storing the secrets my GitHub Actions pipeline needs. Combining the general secrets-management guidance with the GitHub-Actions-specific guidance, what should I actually be doing with them?

**Reference:** From Secrets Management: rotate CI/CD-stored secrets regularly, and explicitly validate that forking the repository or copying a job definition does not copy the secret along with it. From GitHub Actions Security: when calling a reusable workflow, don't use `secrets: inherit` (it passes every secret the caller has, including ones the called workflow doesn't need) — explicitly pass only the specific secrets that workflow requires.

**Answer** (cited [2, 3]): You should store secrets as part of your CI/CD tooling, such as GitHub's encrypted secrets, rather than committing them to code directly. It's also recommended to manage secrets using a secrets-management system, like AWS Secrets Manager or Hashicorp Vault, ensuring that you have the necessary credentials for your CI/CD tool to access these secrets. Additionally, when creating secrets within a pipeline, make sure they adhere to best practices, including secure randomness and proper length for generation [2][3]. Be cautious of best practices for exposing secrets to CI/CD jobs, as these secrets may be viewable by those with the proper authorization [3].

gold in context: False · gold cited: False

Judge: The assistant's answer correctly covers general secrets management practices such as storing secrets in CI/CD tooling or secret management systems, and generating secrets securely. However, it misses the key GitHub Actions-specific guidance from the reference answer, such as avoiding 'secrets: inherit' when calling reusable workflows and rotating secrets regularly. Therefore, the answer is only partially correct.


## q088 (code_table) — partial

**Q:** In an Express app, if someone sends the query string `?foo[toString]=bar`, what does `request.query.foo` end up being — and why would that trip someone up?

**Reference:** It becomes {} — an object where calling toString() on it will fail, because the query-string parser sets a 'toString' property on the object (shadowing the real method), rather than giving you a normal string or array like most other query shapes.

**Answer** (cited [1]): `request.query.foo` would end up being `{}` (an object where calling `toString()` will fail) because the input has a key that is the method name `toString`, which is not a valid key in terms of storing data in an object) [1]. This could trip someone up because they might expect to get a value associated with the `toString` method, but instead, they get an empty object, leading to unexpected behavior in the application.

gold in context: True · gold cited: True

Judge: The answer correctly states that `request.query.foo` becomes `{}` and that calling `toString()` on it will fail, which matches the reference answer. However, the explanation given for why this happens is inaccurate; the claim that `toString` is not a valid key for storing data in an object is false and not supported by the source. The reference answer explains that the query-string parser sets a 'toString' property on the object, shadowing the real method, which is the key reason for the issue. The assistant's explanation misses this nuance, so the answer is only partially correct.

- unsupported: This happens because the input has a key that is the method name `toString`, which is not a valid key in terms of storing data in an object
- mis-cited: This happens because the input has a key that is the method name `toString`, which is not a valid key in terms of storing data in an object

## q101 (procedural) — partial

**Q:** What's the right way to check the Origin header on a WebSocket handshake so a malicious site can't hijack an already-logged-in user's connection?

**Reference:** Validate the Origin header on every handshake against an explicit allowlist of trusted origins -- never a denylist, and avoid wildcards or substring matching -- since browsers always send this header and malicious JavaScript can't forge it. For Node's `ws` library specifically, do that check in the HTTP server's `upgrade` event before calling `handleUpgrade`, since the library itself discourages using `verifyClient` for this.

**Answer** (cited [1]): Validate the `Origin` header on every handshake. Always use an explicit allowlist of trusted origins. Avoid wildcards or substring matching which are error-prone [1].

gold in context: True · gold cited: True

Judge: The assistant correctly states the need to validate the Origin header on every handshake using an explicit allowlist and avoiding wildcards or substring matching, which aligns with the reference answer. However, it omits the important detail about Node's ws library: that the check should be done in the HTTP server's upgrade event before calling handleUpgrade, and that verifyClient is discouraged. This detail is part of the reference answer and relevant to the question, so the assistant's answer is only partially correct.


## q117 (factual) — partial

**Q:** For a free-text 'additional comments' box on a form, should I just restrict it to letters, digits, and basic punctuation to be safe from injection?

**Reference:** No. The sheet says free-form comments can allow broad Unicode text with length limits rather than restricting users to letters and digits. Define the field's acceptance rules instead of trying to recognize every malicious string. Blocking apostrophes rejects legitimate input without making database queries safe. Use parameterized queries for SQL injection prevention and context-aware output encoding for XSS prevention.

**Answer** (cited [1]): For a free-form comments box, instead of strictly restricting it to letters, digits, and basic punctuation, an allowlist can permit broad Unicode text while limiting its length; it need not restrict users to letters and digits [1].

gold in context: True · gold cited: True

Judge: The assistant correctly states that free-form comments can allow broad Unicode text with length limits rather than restricting to letters and digits, which aligns with the reference answer. However, it omits the important points about defining acceptance rules instead of trying to recognize malicious strings, the example that blocking apostrophes rejects legitimate input without improving safety, and the recommendation to use parameterized queries and context-aware output encoding for injection prevention. Thus, the answer is only partially correct as it misses key security recommendations from the reference.


## q119 (unanswerable) — incorrect

**Q:** We're planning to fine-tune a shared LLM across several partner companies using federated learning so no one has to hand over their raw training data - what security controls does OWASP recommend for that setup?

**Reference:** I don't know.

**Answer** (cited [3]): When fine-tuning a shared LLM across several partner companies using federated learning, OWASP recommends several security controls: 
- Separate training workloads by trust boundary [3]. 
- Avoid sharing GPU or accelerator devices between mutually untrusted tenants unless the platform provides strong hardware-backed partitioning and memory isolation [3]. 
- Run untrusted model evaluation, fine-tuning, and conversion jobs in sandboxes or isolated workers with restricted network egress [3]. 
- Apply per-workload CPU, memory, GPU, disk, process, and network limits to prevent noisy-neighbor and denial-of-service impact [3]. 
- Monitor runtime isolation failures, unexpected device access, cross-namespace network traffic, and attempts to access metadata endpoints [3].

gold in context: None · gold cited: None

Judge: The assistant provides detailed security controls recommended by OWASP for federated learning setups, citing source [3] extensively. However, the reference answer explicitly states "I don't know," indicating no recommended controls are known or provided. Therefore, the assistant's answer contradicts the reference answer by giving specific recommendations rather than admitting lack of knowledge.



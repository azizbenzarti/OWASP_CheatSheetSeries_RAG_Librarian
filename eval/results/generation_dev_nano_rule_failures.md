# Generation failures (dev set)

Every question that was refused when answerable, answered when unanswerable, graded below `correct`, or has an unsupported / mis-cited claim.

## q065 (multi_sheet) — partial

**Q:** I'm storing the secrets my GitHub Actions pipeline needs. Combining the general secrets-management guidance with the GitHub-Actions-specific guidance, what should I actually be doing with them?

**Reference:** From Secrets Management: rotate CI/CD-stored secrets regularly, and explicitly validate that forking the repository or copying a job definition does not copy the secret along with it. From GitHub Actions Security: when calling a reusable workflow, don't use `secrets: inherit` (it passes every secret the caller has, including ones the called workflow doesn't need) — explicitly pass only the specific secrets that workflow requires.

**Answer** (cited [1, 3, 4, 5]): Do not hardcode secrets in workflow files. Pass secrets at the step level (not the job level) and prefer environment-level secrets that are accessible only when targeting a specific environment. When using reusable workflows, avoid secrets: inherit and explicitly pass only the required secrets. Review environment secrets for overrides and ensure you rotate secrets regularly. Consider storing secrets in a secrets-management system or CI/CD tooling, and keep encrypted variants if stored in git; ensure per-environment Secrets and metadata control access. Do not expose secrets to all workflows or environments. Use sidecar decryption where appropriate and ensure the secrets used by pipelines are still protected by best practices for secret generation and access control. [4][5][1][3]

gold in context: True · gold cited: True

Judge: The assistant's answer covers many relevant points from the reference, including avoiding secrets: inherit and rotating secrets regularly. However, it adds details not explicitly in the reference (like passing secrets at step level, sidecar decryption, and storing encrypted variants in git) and misses the key point from the reference about explicitly validating that forking or copying jobs does not copy secrets. Also, the reference emphasizes rotating CI/CD-stored secrets and explicit validation about fork/copy behavior, which the assistant does not mention explicitly. Thus, the answer is partially correct but not fully aligned with the reference.

- unsupported: Do not expose secrets to all workflows or environments.


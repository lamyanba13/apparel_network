# Security Policy

## Reporting a vulnerability

Do not open a public issue, discussion, or pull request for a suspected vulnerability. Do not include credentials, exploit details, personal data, store data, or production evidence in public channels.

Use GitHub's **Report a vulnerability** function on the repository Security tab. This creates a private security advisory visible only to the repository's security maintainers. If private vulnerability reporting is not yet enabled, contact a repository owner privately and ask them to open a draft security advisory before sending technical details.

Include:

- the affected version, commit, component, and environment;
- impact and realistic attack preconditions;
- minimal reproduction steps or a proof of concept;
- known mitigations or workarounds;
- whether the issue is actively exploited or publicly known;
- a safe way to contact the reporter.

Maintainers will acknowledge a complete report within three business days, assign a coordinator, validate severity, and provide a remediation or status update target. Timelines depend on severity and safe-release constraints. Reporters are asked to keep details confidential until a fix and disclosure plan are agreed.

## Supported versions

Fashion Network is currently in Phase 1.1 and has not made a production release.

| Version                                      | Supported |
| -------------------------------------------- | --------- |
| Current `main` branch                        | Yes       |
| Current release line after production launch | Yes       |
| Older release lines and unmerged branches    | No        |

This table must be replaced with explicit release ranges before the first production release.

## Security policy

- Security fixes use private advisories and private forks until coordinated disclosure.
- Severity is assessed using exploitability, confidentiality, integrity, availability, tenant isolation, and inventory/reservation correctness.
- Critical fixes may use the documented `hotfix/*` workflow with required review and CI; audit and secret-handling controls are never bypassed.
- Credentials are never committed. Suspected exposure requires immediate revocation and rotation in addition to repository cleanup.
- Dependency and CI changes require lockfile review and least-privilege workflow permissions.
- Security-sensitive changes require negative tests and a security-aware owner.
- Public disclosure credits reporters when requested and safe.

This policy is not a bug-bounty program and does not authorize access to data or systems, service disruption, social engineering, or destructive testing.

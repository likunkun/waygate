# Security Policy

## Supported Versions

Waygate is currently pre-1.0. Security fixes are applied to the main development line.

## Reporting a Vulnerability

Please do not disclose vulnerabilities publicly before maintainers have had a chance to respond.

If this repository is hosted on GitHub, use GitHub private vulnerability reporting when available. Otherwise, open a minimal issue that says you have a security report and avoid including exploit details, secrets, or private project artifacts.

## Sensitive Data

Waygate state directories can contain prompts, review context, local file paths, command output, and project-specific artifacts. Do not commit or publish:

- `.rrc-controller-*` directories;
- runner logs containing secrets;
- environment variable values;
- database URLs, API tokens, or credentials;
- private target-project artifacts.

The project attempts to record environment variable keys without recording secret values, but users should still review artifacts before sharing them.

---
name: review-security-report
description: Review vulnerability reports about FastMCP before accepting, rejecting, patching, scoring, or publishing them. Use for GitHub Security Advisories, bug-bounty submissions, claimed OAuth or MCP vulnerabilities, and proposed security fixes where the result may instead be an ordinary bug, an upstream issue, expected protocol behavior, or an insecure deployment.
---

# Review a FastMCP security report

A working proof of concept establishes behavior, not ownership or classification. Determine which
component violates which promised security boundary before changing code or advisory state.

## Preserve the original evidence

Export the original report, comments, proof of concept, reporter configuration, and claimed
affected versions before editing an advisory. Record the FastMCP commit used for reproduction.
Derive affected release tags from git history rather than the reporter's estimate.

Keep the investigation read-only until the classification checkpoint. Do not accept the report,
rewrite advisory fields, create a private fork, assign severity, request a CVE, or prepare a patch
merely because the proof of concept works.

## Reproduce the exact claim

Use the smallest end-to-end reproduction against a supported FastMCP release. Record:

- all non-default arguments, environment settings, and deployment assumptions;
- what the attacker controls and what the victim must do;
- the credential, data, or authority the attacker obtains;
- the check or trust boundary allegedly bypassed;
- whether the result occurs with current defaults.

Do not stop at reproduction. A supported non-default configuration can still contain a
vulnerability, while a default can intentionally delegate a security decision elsewhere.

## Identify the responsible layer

Classify where the disputed behavior lives:

- **FastMCP vulnerability:** FastMCP violates a security boundary promised for the supported
  configuration.
- **FastMCP bug:** FastMCP behaves incorrectly, but no security boundary or attacker capability is
  involved.
- **Upstream vulnerability:** The defect is in an implemented standard, dependency, identity
  provider, client, reverse proxy, or deployment platform rather than FastMCP.
- **Insecure deployment:** The operator omitted required controls, exposed a development mode, or
  disabled or delegated the protection without supplying the replacement required by its
  contract.
- **Expected behavior:** The result follows the documented API contract or implemented protocol.
- **Documentation gap:** The implementation follows its intended contract, but the guidance could
  reasonably lead operators to expect a protection that does not exist.

Name both the vulnerable component and the boundary it owns. Do not turn every dangerous setup
into a FastMCP vulnerability, and do not dismiss a real FastMCP boundary violation merely because
another layer could mitigate it.

## Establish FastMCP's contract

Read the implementation, public documentation, docstrings, runtime warnings, tests, and the
commits or PRs that introduced the behavior. Answer:

1. What protection does FastMCP promise in this configuration?
2. Was that protection bypassed, explicitly disabled, or delegated under a documented contract?
3. Is the observed behavior required or permitted by OAuth, MCP, OIDC, or another implemented
   protocol?
4. Does the proof of concept use the public API as supported?
5. Did earlier released documentation promise more than current code provides?

When the intended contract is unclear, stop and ask the subsystem maintainer before accepting the
advisory or proposing a fix. Code shows current behavior; it does not by itself define supported
product behavior.

## Trace OAuth proxy boundaries separately

For OAuth proxy reports, check each layer instead of treating the flow as one authorization step:

- **DCR:** An unknown client may register redirect metadata. Registration alone does not establish
  trust in that client.
- **Redirect validation:** Verify that the authorization request matches the redirect URI stored
  for that client. An attacker using its own correctly registered callback does not bypass
  redirect matching.
- **Downstream consent:** FastMCP's consent page identifies and authorizes the downstream MCP
  client. Ordinary upstream consent generally authorizes FastMCP's shared upstream application,
  not that downstream client.
- **Consent opt-outs:** `require_authorization_consent=False` removes FastMCP consent for local or
  testing use. `"external"` asserts that equivalent consent and transaction binding exist outside
  FastMCP; FastMCP does not verify the replacement controls.
- **PKCE:** PKCE prevents redemption by a party without the verifier. It does not prevent a
  malicious client from redeeming a code issued for its own challenge.
- **Redirect policy:** `allowed_client_redirect_uris` is an optional deployment policy. A static
  allowlist can break hosted clients and open DCR, and it is not the only valid external control.

Use current primary specifications and relevant FastMCP history. Other projects provide context,
not proof of FastMCP's contract.

## Review the proposed fix independently

A patch can block the proof of concept and still be wrong. Check whether it:

- fixes the violated boundary at its source;
- changes an intentional default or documented opt-in behavior;
- breaks open DCR, hosted MCP clients, external consent systems, or another supported workflow;
- assumes one replacement control is the only acceptable design;
- enforces the claimed property rather than checking only that a setting is present.

If the patch changes the supported product contract, treat it as an enhancement and obtain
maintainer agreement independently of the security report.

## Classification checkpoint

Before any GitHub mutation, return a short verdict with the decisive configuration, affected
versions, violated or delegated boundary, responsible component, realistic impact, and proposed
next action. Recommend exactly one:

- accept as a draft advisory and prepare a private patch;
- request specific missing evidence;
- route as a normal FastMCP bug or upstream issue;
- close as expected behavior or an insecure deployment;
- make a documentation or warning change without publishing an advisory;
- ask the relevant maintainer to decide the contract.

For a rejection, acknowledge any valid reproduction and explain the decisive precondition. Do not
insult the reporter or speculate about how the report was produced.

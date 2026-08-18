---
name: review-security-report
description: Review private vulnerability reports and security advisories about FastMCP before accepting, rejecting, patching, scoring, or publishing them. Use for GitHub Security Advisories, bug-bounty reports, claimed OAuth or MCP vulnerabilities, and proposed security fixes where demonstrated behavior may instead be an explicit configuration tradeoff or protocol requirement.
---

# Review a FastMCP security report

Determine whether a report shows a FastMCP security-boundary violation, a dangerous but
documented configuration, expected protocol behavior, or a documentation gap. A working exploit
is evidence of behavior, not by itself evidence of a vulnerability.

## Preserve the report before changing anything

Export the original report, comments, reporter configuration, affected versions, and proof of
concept before editing an advisory. Record the FastMCP commit SHA used for reproduction.
Derive the first affected and fixed release tags from git history; do not infer a version range
from an approximate feature date or the reporter's estimate.

Keep investigation read-only until the classification checkpoint below. Do not accept the
report, rewrite advisory fields, create a private fork, request a CVE, assign severity, or write a
patch merely because the proof of concept works.

## Reproduce the actual claim

Reproduce the smallest end-to-end attack against a supported FastMCP version. Record:

- the exact non-default constructor arguments, environment settings, and deployment assumptions;
- what the attacker controls and what the victim must do;
- the credential or authority the attacker actually obtains;
- which check the reporter claims was bypassed;
- whether the same attack works with current defaults.

Distinguish a validation bypass from a value that passed the intended validation. For OAuth DCR,
a client may register a callback it owns. Sending that client's response to its registered
callback is not an open redirect if FastMCP validates the authorization request against the
client's registration.

## Establish the intended security contract

Read the implementation, public documentation, parameter docstrings, warnings, tests, and the
commits or PRs that introduced the behavior. The key question is:

> Which protection does FastMCP promise in this exact configuration, and was it bypassed?

Answer all of these before assigning a verdict:

1. Does the attack work with default settings?
2. Does it require an explicit security opt-out or an assertion that replacement controls exist?
3. Is the observed behavior required or permitted by OAuth, MCP, OIDC, or another implemented
   protocol?
4. Does FastMCP still enforce the checks it promises, such as client registration matching,
   PKCE binding, audience validation, or user consent?
5. Is the reporter crossing a documented trust boundary, or demonstrating the consequence of
   removing it?
6. Did older documentation promise more protection than current documentation or code provides?

A warning or name such as `unsafe`, `insecure`, `external`, `disable`, or `development only` is
not automatically dispositive. Confirm the full contract. Conversely, do not call the documented
consequence of disabling a control a bypass of that control.

## Apply FastMCP OAuth-specific checks

For OAuth proxy reports, trace these boundaries separately:

- **Client registration:** Open DCR intentionally lets previously unknown clients register.
  Registration does not establish that FastMCP trusts the client.
- **Redirect validation:** Verify that the authorization request matches the redirect URI stored
  for that client. Do not conflate attacker-owned registration with a redirect-matching bypass.
- **Downstream authorization:** FastMCP's consent screen identifies and authorizes the downstream
  MCP client. Ordinary upstream consent usually authorizes FastMCP's shared upstream application,
  not the downstream client.
- **Explicit opt-outs:** `require_authorization_consent=False` removes FastMCP consent for local or
  testing use. `"external"` asserts that equivalent consent and transaction binding exist outside
  FastMCP; FastMCP does not verify those controls.
- **PKCE:** PKCE blocks interception by a party that lacks the verifier. It does not stop a
  malicious public client from redeeming a code issued for its own challenge.
- **Redirect policy:** `allowed_client_redirect_uris` is an optional deployment policy. Requiring a
  static allowlist can break hosted clients and open DCR, and it is not the only possible external
  authorization control.

Consult current primary specifications and relevant FastMCP history. Treat analogous project
behavior as supporting context, not as proof of FastMCP's contract.

## Classification checkpoint

Write a short verdict before any mutation:

- **Vulnerability:** A supported configuration violates a promised security boundary, a default
  protection is bypassed, or an operator cannot safely supply the required replacement control.
- **Dangerous explicit configuration:** The behavior follows from a documented, non-default
  removal of the relevant protection. Recommend warnings or documentation only if the consequence
  is unclear.
- **Expected protocol behavior:** The report misclassifies required or intentional behavior such
  as attacker-owned DCR registration. Explain the separate control that supplies authorization.
- **Documentation gap:** The code follows the intended contract, but public guidance could
  reasonably cause an operator to believe a missing protection exists.
- **Unclear contract:** Stop and ask the subsystem maintainer whether the disputed pattern is
  supported. Do this before accepting an advisory or preparing a fix.

For any verdict other than **Vulnerability**, do not create a security patch or publish an
advisory unless a maintainer explicitly chooses defense-in-depth work as a product change.

## Evaluate a proposed fix as product policy

A patch can prevent the proof of concept and still be wrong. Determine whether it:

- fixes the violated boundary rather than compensating elsewhere;
- changes an intentional default or makes an opt-in combination impossible;
- breaks open DCR, hosted MCP clients, external consent systems, or other supported workflows;
- assumes one replacement control is the only acceptable design;
- actually enforces the claimed property instead of checking only that a setting is present;
- adds a special-case babysitter to one unsafe setting while similar opt-outs remain intentional.

If the patch changes the supported product contract, classify it as an enhancement and obtain
maintainer agreement independently of the security report.

## Recommend the next action

Return one of these outcomes with evidence:

- accept as a draft advisory and prepare a private patch;
- request specific missing reproduction evidence;
- close as expected behavior or an explicit security opt-out;
- make a documentation or warning change without publishing an advisory;
- ask the relevant maintainer to decide the contract.

For a rejection, acknowledge any mechanically valid reproduction. Explain the decisive
precondition, the intended contract, and the control that was explicitly removed or delegated.
Do not insult the reporter or speculate about how the report was produced.

# Code comment review — 2026-10-02

Reviewed live MCP server source revision
`c5865c10ec2ed9e62dd98d1bc88525eb956caf94` for `gm-mcp-server-tci`.
The previous bead notes reported 59 extracted comments and a no-change review;
this review rechecked Python comments and docstrings, shell comments, workflow
references, and test annotations against their current implementations.

## Corrections

- `scripts/check-image-source.sh` referred to a “private library”. The wheel
  preparation script resolves the pinned shared library through public HTTPS.
  The comment now says “shared library”; the pinned revision, permitted checkout,
  cleanliness requirement, and fail-closed untracked-source guard are unchanged.
- `_call` in `mcp_server/catalog_api.py` claimed every failure reported only URL
  and status. That describes the `HTTPStatusError` branch, but the generic branch
  logs `repr(exc)` and returns its message. The docstring now distinguishes those
  branches and explicitly states that exception messages are not sanitized.
  No logging, response mapping, authorization, or request behaviour changed.

The second correction documents a limitation rather than a new security
assurance. Arbitrary exception messages can contain information supplied by the
exception producer; this comment-only review does not establish that those
messages are safe for every failure source.

## Retained rationale and directives

| Scope | Checked against live source |
| --- | --- |
| `catalog_api.py` delegated route allowlist | `_auth` uses a full regex match, so the bearer header is restricted to activity and consent routes. The contract-scan explanation, historical logger identity, and unconfigured-delegation rationale remain useful. |
| `tool_routing.py` lookup, outcomes, consent comments | Lookup providers match the promoted route contract; reported outcomes omit impressions; consent purposes come from the shared runtime. |
| Concrete imports and lint/type/security suppressions | MCP runtime annotation boundaries, fixed local subprocess commands, and configured-versus-tool-input distinctions remain intentional. Directives were not removed. |
| Server and telemetry tests | Section comments locate fixtures, real-handler paths, exporter-disabled regressions, event-loop monitoring, and provider-flush coverage. Inline expectations match the assertions and tested calls. |
| Image-source script | The configured dependency exception and rejection of other untracked files preserve complete image source identity. |
| Workflows and provenance | Full commit pins, license/provenance metadata, shebangs, and build/release boundaries remain intact. |

No executable statements, runtime dependencies, promoted contracts, workflow
pins, application policy, or release behaviour changed. The existing complete
`just check` gate validates this handoff; no new behaviour tests are needed for
comment-only corrections.

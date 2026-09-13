# MCP server development

Install the pinned tools and locked environment, then run the authoritative gate:

```bash
mise install
just setup
just check
```

The maintained recipe graph is:

| Recipe | Contract |
| --- | --- |
| `just source-check` | Run format, lint, documentation, and promoted-contract checks. |
| `just protocol-check` | Verify the twelve registered tools, stable input schemas, shared path policy, and promoted route contract. |
| `just automation-check` | Run Actionlint and verify workflow, recipe, dependency, and image policy. |
| `just ci-check` | Run source, type, protocol, automation, and version-preview checks. This is CI's primary check command. |
| `just test` / `just coverage` | Run the adapter suite and write `coverage.xml`; `coverage` is the CI-facing alias. |
| `just secret-scan` | Scan Git history and the working tree with Gitleaks. |
| `just check` | Run `ci-check`, secret scans, coverage, build, isolated installation, and license checks. This is the authoritative local gate. |
| `just audit` | Run the network-backed locked-dependency vulnerability scan. |
| `just image` | Build and inspect the non-root, repository-named local image. |
| `just release-dry-run` | Run `just check`, stage first-party wheels, and assemble checksums, notices, SBOM, and provenance without publishing. |

The same required workflow runs for every pull request, pushes to `main`, manual dispatches,
and the weekly schedule. There is no actor-specific or reduced dependency-update path. The
only mapped CI secret is `CODECOV_TOKEN`; first-party source is fetched from public repositories
at immutable revisions. Releases run only for version tags and use the immutable shared
automation revision to attest package artifacts and the `mcp-server` image.

`pyproject.toml` and `uv.lock` pin `groovemap-agent-tools` and `groovemap-runtime` to the same
public `python-libraries` commit. Runtime and ordinary development use installed packages,
not sibling source imports. `just prepare-library-wheels` may reuse an adjacent clean checkout
at that exact commit or create a temporary checkout; `GROOVEMAP_LIBRARIES_REPO` can name an
explicit clean checkout for build preparation. No cross-repository personal access token or
GitHub App credential is required.

New tool behavior belongs in `python-libraries/agent-tools` when it is framework-neutral.
Keep runtime construction in `server`, CLI dispatch in `transport`, registration in
`registration`, local argument/route policy in `tool_routing`, and HTTP adaptation in
`catalog_api`. Promote contract changes through the producer repository and update the
committed digest before changing adapters.

See the [architecture](architecture.md), [tool reference](tools.md),
[configuration](configuration.md), [transports and security](security.md), and
[documentation index](README.md).

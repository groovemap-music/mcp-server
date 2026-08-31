# MCP server development

Install the pinned tools and locked environment, then run the authoritative gate:

```bash
mise install
just setup
just check
```

`just test` runs adapter tests with coverage. `just protocol-check` validates tool
registration and the promoted Catalog API contract. `just build` creates the wheel and
source distribution, while `just install-check` verifies the built wheel in an isolated
environment. `just image` builds and inspects the non-root, repository-named local image.

The same required workflow runs for ordinary and Dependabot pull requests, pushes to `main`,
manual dispatches, and the weekly schedule. It fails closed when the read-only GitHub App or
Codecov credentials are unavailable; there is no reduced dependency-update path. Releases run
only for version tags and use the immutable shared automation revision to attest package
artifacts and the `mcp-server` image.

The `groovemap-agent-tools` source revision is recorded in `uv.lock`. Developers use their
normal Git credential helper; CI uses a short-lived, read-only GitHub App token. Do not use
a cross-repository personal access token.

New tool behavior belongs in `python-libraries/agent-tools` when it is framework-neutral.
Keep only MCP transport and registration code here. Promote contract changes through the
producer repository and update the committed digest before changing adapters.

See the [architecture](architecture.md), [tool reference](tools.md),
[configuration](configuration.md), [transports and security](security.md), and
[documentation index](README.md).

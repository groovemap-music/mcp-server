# Repository instructions

- Run `just check` before proposing a change.
- Treat `contracts/catalog-api/mcp-server/v1` as a promoted producer contract; update provenance and checks together.
- `groovemap-agent-tools` is the framework-neutral tool authority. Do not reintroduce Catalog API or database implementation imports.
- Never add a relative import or build-context dependency on another GrooveMap repository.
- Do not commit credentials, local state, generated client configuration, or decrypted secret material.
- Releases use Commitizen and approved `v$version` tags. Migration work must not publish artifacts.

# Changelog

All notable changes to this project will be documented here by Commitizen.

## v0.2.1 (2026-09-15)

### Fix

- **changelog**: drop the legacy epic reference the docs gate rejects

## v0.2.0 (2026-09-15)

### Feat

- **tools**: add lookup_release
- **tools**: add record_recommendation_outcome, get_consent, and set_consent
- **adapter**: add the optional delegated app token boundary
- **telemetry**: adopt wave-2 tracing, runtime metrics, and the event-loop monitor
- **tools**: add a media filter to search and document media in release details
- **telemetry**: record OTEL metrics for every MCP tool and Catalog API call
- establish GrooveMap MCP server repository
- remove the Digger feature entirely (#374)
- **api**: Discogs OAuth callback flow (no more PIN copy/paste) (#373)
- **neo4j-tls**: configurable client-side Neo4j Bolt TLS (#74) (#354)
- **digger**: M3 Layer E — perf tests, docs, deployment wiring, E2E smoke (completes M3) (#353)
- **digger**: M3 Layer D — MCP tools + agent eval suite (#352)
- **digger**: M2 Layer E — perf tests, optimizer docs, E2E smoke (completes M2) (#348)
- **digger**: M2 Layer C — scheduler + worker Redis publish (#346)
- **digger**: M1 integration + docs — compose/justfile, perftest, smoke, scraping policy (#343)
- redesign Ask as global pill with agent-driven UI actions (#304)
- add MusicBrainz release-group support (#230)
- Collaboration Network — artist connection graph and centrality (#220)
- Admin Dashboard Phase 4 — unified identity and audit log (#139) (#211)
- password reset flow and TOTP two-factor authentication (#190) (#210)
- Natural Language Graph Queries — conversational access to the knowledge graph (#203) (#209)
- **admin**: admin dashboard phase 1 — auth, extraction history, trigger, DLQ purge (#104) (#136)
- MCP server — expose knowledge graph to AI assistants (#124)
- artist collaborators panel and genre/style tree (#84) (#169)
- **collection**: add gap analysis for labels, artists, and pressings (#96)
- **api**: migrate SnapshotStore from in-memory dict to Redis (#55) (#78)
- **security**: Docker Compose runtime secrets via _FILE convention (#77)
- Discogs user integration — authenticate, sync collection & wantlist (#66)
- **schema-init**: add one-shot schema initialiser service

### Fix

- **ci**: use public python libraries
- **publication**: advance private archive boundary
- **ci**: allow injected library image input
- security & config/deploy hardening — 5 bug-hunt findings (batch:p2-security-config) (#459)
- P1 release blockers — 9 bug-hunt findings (batch:p1-release-blockers) (#458)
- **api**: build the password reset link from an absolute APP_BASE_URL (#445)
- **deps**: CVE-2026-69247, full dependency refresh, and cooldown policy (#447)
- deployment portability & config correctness — 6 bug-hunt findings (batch:deploy-config) (#439)
- insights/Neo4j performance failures — P1 rarity timeout + 4 related (batch:insights-perf) (#435)
- deep bug-hunt 2026-07-19 — land all 72 P0/P1/P2 fixes (#420)
- **postgres**: right-size pools & bound brainztableinator concurrency to fit shared PgBouncer cap (#396)
- **config**: accept host:port in POSTGRES_HOST (pooler support) (#393)
- **common**: support REDIS_PASSWORD for authenticated Redis connections (#357)
- comprehensive bug fixes across all services — round 21 (#262)
- comprehensive bug fixes and documentation updates — round 17 (#258)
- comprehensive bug fixes across all services — round 14 (#254)
- comprehensive bug fixes across all services — round 13 (#252)
- comprehensive bug fixes across all services — round 12 (#251)
- comprehensive bug fixes across all services — round 9 (#248)
- comprehensive bug fixes across all services — round 4 (#243)
- comprehensive bug fixes across all services — round 2 (#235)
- comprehensive bug fixes across all services (#233)
- ensure database count parity with post-extraction cleanup (#106)
- **explore**: resolve gap analysis bugs in info panel
- **config**: accept plain hostnames for NEO4J_HOST, POSTGRES_HOST, REDIS_HOST
- **config**: rename *_ADDRESS to *_HOST across entire codebase
- **config**: rename REDIS_URL→REDIS_ADDRESS and RABBITMQ_HOST→RABBITMQ_ADDRESS
- **config**: use username/USERNAME consistently across all secrets
- **config**: rename rabbitmq_pass secret to rabbitmq_password
- **security**: resolve all Semgrep blocking findings (closes #80) (#81)
- **security**: harden API against issue #71 findings (#73)

### Refactor

- **ci**: normalize validation recipes
- **server**: separate composition concerns
- **common**: split versioned Python libraries
- **rabbitmq**: replace topic exchange with per-data-type fanout exchanges (#105)
- remove curator service (dead code after sync migration)
- rename rustextractor to extractor
- remove pyextractor and discovery services

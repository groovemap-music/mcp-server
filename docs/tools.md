# MCP tool reference

The server exports exactly twelve tools. The MCP SDK derives the input schemas from the typed
handlers in `mcp_server.tool_routing`; injected `ctx` is never exposed as an input. All data
operations use the promoted Catalog API v1 [route contract](../contracts/catalog-api/mcp-server/v1/routes.json),
whose [provenance record](../contracts/catalog-api/mcp-server/v1/source.json) pins the producer
revision and digest.

| MCP tool | Required schema fields | Optional schema fields and defaults | Catalog API operation |
| --- | --- | --- | --- |
| `search` | `query: string` | `types: string = "artist,label,master,release"`; `media: list[string] \| null = null`; `limit: integer = 20` | `GET /api/search` |
| `get_artist_details` | `artist_id: string` | none | `GET /api/node/{node_id}?type=artist` |
| `get_label_details` | `label_id: string` | none | `GET /api/node/{node_id}?type=label` |
| `get_release_details` | `release_id: string` | none | `GET /api/node/{node_id}?type=release` |
| `get_genre_details` | `genre_name: string` | none | `GET /api/node/{node_id}?type=genre` |
| `get_style_details` | `style_name: string` | none | `GET /api/node/{node_id}?type=style` |
| `find_path` | `from_name: string`; `from_type: string`; `to_name: string`; `to_type: string` | `max_depth: integer = 10` | `GET /api/path` |
| `get_trends` | `name: string` | `entity_type: string = "artist"` | `GET /api/trends` |
| `get_graph_stats` | none | none | `GET /api/graph/stats` |
| `get_collaborators` | `artist_id: string` | `limit: integer = 20` | `GET /api/collaborators/{artist_id}` |
| `get_genre_tree` | none | none | `GET /api/genre-tree` |
| `nlq_query` | `query: string` | none | `POST /api/nlq/query` |

## Validation behavior

- Search types are limited to `artist`, `label`, `master`, and `release`; an empty `types`
  string selects all four. Result limits are clamped to 1–100. The producer rejects search
  queries shorter than three characters; that constraint is not encoded in the MCP input
  schema.
- `search`'s optional `media` filter takes a list of family or medium ids from the ADR 0007
  canonical media taxonomy (see [Media filter and block](#media-filter-and-block)). An id the
  taxonomy does not define returns an error naming the unknown ids and the valid families,
  instead of an empty result set that reads as "no such records".
- Path and trend entity types are limited to `artist`, `genre`, `label`, and `style`; path
  depth is clamped to 1–10.
- Artist, label, and release identifiers must be numeric strings.
- Genre and style names are URL-encoded before they become route segments.
- Catalog API HTTP and transport failures become structured MCP error results instead of
  direct database errors.

## Media filter and block

Both `search` and `get_release_details` speak the ADR 0007 canonical media taxonomy.
`common.agent_tools.discovery` is supplied by the installed `groovemap-agent-tools` package;
`common.media` is supplied by the installed `groovemap-runtime` package.

- **`search`'s `media` filter** takes any mix of family ids (`vinyl`, `shellac`,
  `grooved_other`, `tape`, `optical`, `digital`, `video`, `other`) and narrower medium ids
  underneath them (for example `vinyl_12`, `optical_cd`, `tape_cassette`). A family id matches
  every medium in that family; a medium id matches only itself. Ids are validated against the
  taxonomy before the request reaches the Catalog API, which reads the filter as repeated
  `media` query parameters on `GET /api/search`.
- **`get_release_details`'s response** carries an additive top-level `media` block when the
  release has media data:

  | Field | Meaning |
  | --- | --- |
  | `families` | Sorted family ids the release's media belong to. |
  | `items` | One entry per medium: `family`, `medium`, `qty`, and attributes (`size_inches`, `speed_rpm`, `channels`, `codec`, `variants`, `appearance`). |
  | `release_kind` | `album`, `single`, `ep`, `broadcast`, `other`, or `null`. |
  | `edition` | Edition facts such as `reissue`, `remastered`, `limited`, `promo`. |
  | `unmapped` | Raw provider values the taxonomy did not recognize, kept for coverage rather than dropped. |

  See [ADR 0007](https://github.com/groovemap-music/design/blob/main/docs/adr/0007-canonical-media-taxonomy.md)
  in the `design` repository for the full block shape, including `packaging`, `container`,
  `traits`, and `flags`.

`Discogs` in an argument description means the upstream catalog identifier namespace. It
is a data-source protocol term, not the name of this server or the GrooveMap project.

Run `just protocol-check` after changing a tool, route, or promoted contract. See
[architecture and ownership](architecture.md) for the promotion boundary.

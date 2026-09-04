# MCP tool reference

The server exports exactly twelve tools. All data operations use the promoted Catalog API
v1 route contract in [`contracts/catalog-api/mcp-server/v1`](../contracts/catalog-api/mcp-server/v1).

| MCP tool | Important inputs | Catalog API operation |
| --- | --- | --- |
| `search` | `query`, comma-separated `types`, `media`, `limit` | `GET /api/search` |
| `get_artist_details` | numeric `artist_id` | `GET /api/node/{id}?type=artist` |
| `get_label_details` | numeric `label_id` | `GET /api/node/{id}?type=label` |
| `get_release_details` | numeric `release_id` | `GET /api/node/{id}?type=release` |
| `get_genre_details` | exact `genre_name` | `GET /api/node/{name}?type=genre` |
| `get_style_details` | exact `style_name` | `GET /api/node/{name}?type=style` |
| `find_path` | entity names/types, `max_depth` | `GET /api/path` |
| `get_trends` | entity name/type | `GET /api/trends` |
| `get_graph_stats` | none | `GET /api/graph/stats` |
| `get_collaborators` | numeric `artist_id`, `limit` | `GET /api/collaborators/{artist_id}` |
| `get_genre_tree` | none | `GET /api/genre-tree` |
| `nlq_query` | natural-language `query` | `POST /api/nlq/query` |

## Validation behavior

- Search types are limited to `artist`, `label`, `master`, and `release`; result limits are
  clamped to 1–100.
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

Both `search` and `get_release_details` speak the ADR 0007 canonical media taxonomy that the
`groovemap-agent-tools` and `groovemap-runtime` libraries vendor (`common.media`,
`common.agent_tools.discovery`).

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

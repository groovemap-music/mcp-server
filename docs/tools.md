# MCP tool reference

The server exports exactly twelve tools. All data operations use the promoted Catalog API
v1 route contract in [`contracts/catalog-api/mcp-server/v1`](../contracts/catalog-api/mcp-server/v1).

| MCP tool | Important inputs | Catalog API operation |
| --- | --- | --- |
| `search` | `query`, comma-separated `types`, `limit` | `GET /api/search` |
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
- Path and trend entity types are limited to `artist`, `genre`, `label`, and `style`; path
  depth is clamped to 1–10.
- Artist, label, and release identifiers must be numeric strings.
- Genre and style names are URL-encoded before they become route segments.
- Catalog API HTTP and transport failures become structured MCP error results instead of
  direct database errors.

`Discogs` in an argument description means the upstream catalog identifier namespace. It
is a data-source protocol term, not the name of this server or the GrooveMap project.

Run `just protocol-check` after changing a tool, route, or promoted contract. See
[architecture and ownership](architecture.md) for the promotion boundary.

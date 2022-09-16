## Regions

---

Regions are resolved by the bot in the following order:

- The provided region, if present.
- The user's region, if they are linked.
- The guild's region, if set by a user with the `manage_server` permission.
- The user's inferred region.
- If none of these options succeeds, the bot falls back to `eu`, the largest region by population.

The bot infers regions using the following conversion table:


| Locale  | Region |
|:--------|:-------|
| `en-US` | `na`   |
| `en-GB` | `eu`   |
| `bg`    | `eu`   |
| `zh-CN` | `asia` |
| `zh-TW` | `asia` |
| `hr`    | `eu`   |
| `cs`    | `eu`   |
| `da`    | `eu`   |
| `nl`    | `eu`   |
| `fi`    | `eu`   |
| `fr`    | `eu`   |
| `de`    | `eu`   |
| `el`    | `eu`   |
| `hi`    | `eu`   |
| `hu`    | `eu`   |
| `it`    | `eu`   |
| `ja`    | `asia` |
| `ko`    | `asia` |
| `lt`    | `eu`   |
| `no`    | `eu`   |
| `pl`    | `eu`   |
| `pt-BR` | `na`   |
| `ro`    | `eu`   |
| `ru`    | `ru`   |
| `es-ES` | `eu`   |
| `sv-SE` | `eu`   |
| `th`    | `asia` |
| `tr`    | `eu`   |
| `uk`    | `eu`   |
| `vi`    | `asia` |

If you disagree with this table, feel free to open an Issue.
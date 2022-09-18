## Commands

All commands, except for the ones in `general`, can be disabled by server users with the `manage_server` permission.

If you think you have found an error in any of the commands, please open an Issue.

---

### `#general`

`/help`

Shows the user an ephemeral message with basic information about the bot.


`/invite`

Shows the user an ephemeral message with the invite url for the bot.

`/profile [user]`

Shows the profile of the given user.
If a user is not provided, shows the profile of the invoker.

This is just `guess` count and record for now.

`/setlanguage <language>`

Set a user's preferred language.

`/setserverregion <region>`

Set a server's default region.

Requires the `manage_server` permission.

`/toggle <command_or_category> [channel]`

Locally disables or enables a command or category from this bot. If a channel is not provided, this action is global.

Requires the `manage_server` permission.

---

### `#wows`

`/build <ship>`

Shows applicable builds from https://wo.ws/builds given a ship. If you would like to contribute a build, please contact `@Yurra#3315`, the creator of the document.

`/clan [region] <clan>`

Fetches clan information, optionally in a specified region.
The following information is available:

- Tag, Name, Description
- Members
- Creation Date
- Achievement Count
- Port Upgrades
- Member statistics for Randoms, Co-Op, Ranked, and Clan Battles
- Clan Battles Ratings

Additionally, this command has the shortcut `myclan` for linked users.

`/dualrender <replay_a> <replay_b> [name_a] [name_b] [fps] [quality] [team_tracers]`

Merges two `*.wowsreplay` files from opposing sides of the same match into a minimap timelapse.

Options:
- `name_a`, `name_b` - The names to use for the teams. Defaults to `Alpha` and `Bravo`.
- `fps` - Can be a value from `15` to `30`; defaults to `20`.
- `quality` - Can be a value from `1` to `9`; defaults to `7`.
  - Higher values may require the Discord server to have Nitro boosts.
- `team_tracers` - Colors tracers by their relation to the replay creator instead of shell type; defaults to `false`.

`/guess [difficulty] [min_level] [max_level] [historical]`

A silhouette guessing game based on "Who's that Pokémon?". 
Tests ships and other "carbon copies" are excluded from appearing here.

Options:

- `difficulty`
  - `easy` - All similar ships are accepted.
  - `normal` - Similar ships of valid tiers are accepted.
  - `hard` - No extra help.
- `min_tier`, `max_tier` - Tiers to restrict the answer to.
- `historical` - Paper ships are excluded when this option is enabled.

`/inspect <ship>`

Shows basic ship information about a ship. Mostly useful for checking `guess` results, but may also be useful to developers.

`/link`

Opens a prompt for linking Discord accounts to WG accounts.

`/render <replay> [fps] [quality] [logs] [anon] [chat] [team_tracers]`

Generates a minimap timelapse and more from a `*.wowsreplay` file.

Options:
- `fps` - Can be a value from `15` to `30`; defaults to `20`.
- `quality` - Can be a value from `1` to `9`; defaults to `7`.
  - Higher values may require the Discord server to have Nitro boosts.
- `logs` - Additionally shows a detailed HP bar, metrics, ribbons & achievements, chat, and killfeed; defaults to `true`.
- `anon` - Anonymizes player names in the format `Player X`; defaults to `false`. Ignored when `logs` is disabled.
- `chat` - Shows chat; defaults to `true`. Ignored when `logs` is disabled.
- `team_tracers` - Colors tracers by their relation to the replay creator instead of shell type; defaults to `false`.

This is a wrapper of [Minimap Renderer](https://github.com/WoWs-Builder-Team/minimap_renderer).
Issues with it should be redirected there.

`/stats [region] <player> [ship]`

Fetches player information, optionally in a specified region.
The following information is available:

- Username, Karma
- Battle Count
- Wins, Losses, and Ties
- Survival
- Clan, Role, and Join Date
- Averages and Records of Metrics, including Base Experience
- Armaments Usage

If `ship` is provided, then the statistics displayed will be limited to the specified ship.

If the player's profile visibility is set to `hidden`, limited statistics will be displayed instead. 
These are identical to those found in the clan members view.

Additionally, this command has the shortcut `mystats` for linked users.

`/update`

Shows details about the latest update's maintenance times, as well as providing a URL.

---

### `#fun`

`/aah [hd]`

Monday is coming...
Now in HD!

`/buki [query]`

Shows a queried emoji of (Fu)buki from [Kantai Collection](https://en.wikipedia.org/wiki/Kantai_Collection).
If a query is not provided, instead sends a random emoji.

The main server where these are hosted can be joined with [this invite](https://discord.gg/TcumFwj).

`/pog`

poggers

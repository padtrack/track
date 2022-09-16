## Cleaning and Romanization

---

The bot processes user input for convenience and romanization for users with English keyboards.

The bot first performs a "clean" step that removes all whitespace characters and then further removes the following characters:

- `-`
- `.`
- `'`
- `·`
- `.`

Afterwards, it also performs a romanization step.
This starts with the cleaned strings of the `en` localization.
For ships of the nations of `Japan` and `Germany`, the bot will convert characters with the following table:

| From | To   |
|:-----|:-----|
| `ō`  | `ou` |
| `ū`  | `uu` |
| `ä`  | `ae` |
| `ö`  | `oe` |
| `ü`  | `uu` |

Regardless of nationality, it will also run [Unidecode](https://pypi.org/project/Unidecode/) against the cleaned strings.
The bot will check cleaned user input against the cleaned strings in the user's language and romanizations.
For example, after cleaning, the bot would expect

- any of `zaō`, `zaou`, or `zao` from an English user.
- any of `蔵王`, `zaou`, or `zao` from a Japanese user.
- any of `gkurfürst`, `grosserkurfürst`, `gkurfurst`, `grosserkurfurst`, `grosserkurfuerst`, `gkurfuerst` from an English user.

In addition, `kreml` is a hardcoded romanization for `Кремль`/`Kremlin`.

If you have found an issue with this process, feel free to open an Issue.
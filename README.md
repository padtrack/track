## Track

Track is a Discord bot with World of Warships utilities.

For a list of features, see the [commands reference](https://github.com/padtrack/track/wiki/Commands) in the wiki.

---

### Installation


1. Get Python 3.10 or higher

A virtual environment can be created with `python3.10 -m venv venv`.

2. Clone the repository

```
git clone https://github.com/padtrack/track.git
```

3. Install dependencies

```
cd track
pip install -U -r requirements.txt
```

4. Set up the database

```
python bot/utils/db.py
```

5. Create a `secrets.ini` file from `secrets_template.ini`

For more information about creating a Discord applications, see [this article](https://discordpy.readthedocs.io/en/stable/discord.html).

6. Install Redis

For more information, see [this article](https://redis.io/docs/getting-started/).

7. Install FFmpeg

For more information, see [this website](https://ffmpeg.org/).

8. Configure the project in `config.py`

Most of these can be left unchanged, but it is highly advised to change the values at the bottom.

9. You're set! For information about updating the bot between game updates, see [here](docs/UPDATING.md).

---

### Usage

The bot can be launched with `bot/run.py`. The full usage is:

```
python run.py [--sync | --no-sync]
```

The optional sync flag will cause the bot to sync the command tree on startup. 
Only use this flag when necessary to avoid being rate-limited.

Render workers can be launched with `bot/worker.py`. The full usage is:

```
python worker.py -q {single, dual} [{single,dual} ...]
```

Which queues the worker should listen to can be specified with the respective option.

---

### License

This project is licensed under the GNU AGPLv3 License.

---

### Credits and Links

- [@alpha#9432](https://github.com/0alpha) - Thank you for your invaluable insight and help with the OAuth 2.0 server!
- [@TenguBlade#3158](https://www.reddit.com/user/TenguBlade/) - Thank you for your help with the guess similarity groups!
- @dmc#3518 - Thank you for your help with the builds!
- The Minimap Renderer's repository is available [here](https://github.com/WoWs-Builder-Team/minimap_renderer).

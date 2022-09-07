## Updating the project

---

### Updating the bot

After pulling, you may need to re-sync the command tree in order for changes to be reflected in Discord. 
This can be done with the `--sync` flag:

```shell
cd bot
python run.py --sync
```


### Updating resources

1. Track relies on unpacked game files at each game update. 
To begin, install the WoWS Unpacker utility available 
[here](https://forum.worldofwarships.eu/topic/113847-all-wows-unpack-tool-unpack-game-client-resources/).


2. Move `scripts/extract.py` to the root of your WoWS installation, and run it.

```shell
python scripts/extract.py
```

3. This will create `res_extract/` in the root directory. 
Move `GameParams.data`, located in `res_extract/content`, to `resources/`. 
Move `ships_silhouettes`, located in `res_extract/gui`, to `bot/assets/public/`.


4. Locate `texts` in `bin/<bin_number>/res/`, where `bin_number` is the game version (highest for latest). Move it to `resources/`.


5. Run `scripts/ships/generate.py`.

```shell
python scripts/ships/generate.py
```

6. This will generate `ships.json` in `generated/`. Compare it the previous version by running `scripts/ships/compare.py`.

```shell
python scripts/ships/compare.py
```

7. Update `bot/assets/public/guess.toml` as appropriate, and then move `ships.json` to `bot/assets/public/`.

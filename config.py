import os

import environ

SECRETS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.ini")
ENVIRONMENT = os.environ.get("ENVIRONMENT", default="testing")
ini_secrets = environ.secrets.INISecrets.from_path(SECRETS_PATH, ENVIRONMENT)


@environ.config(prefix="")
class TrackConfig:
    created = environ.var(converter=int)

    @environ.config(prefix="DISCORD")
    class Discord:
        owner_ids = environ.var(converter=set)
        default_prefix = environ.var(")")
        token = ini_secrets.secret(name="discord_token")

    discord = environ.group(Discord)

    @environ.config(prefix="REDIS")
    class Redis:
        port = 6379
        password = ini_secrets.secret(name="redis_password")
        host = ini_secrets.secret(name="redis_host")

    redis = environ.group(Redis)

    @environ.config(prefix="CHANNELS")
    class ChannelIDs:
        failed_renders = environ.var(converter=int)

    channels = environ.group(ChannelIDs)

    @environ.config(prefix="WG")
    class Wargaming:
        app_id = ini_secrets.secret(name="wg_application_id")

    wg = environ.group(Wargaming)

    @environ.config(prefix="TWITTER")
    class Twitter:
        token = ini_secrets.secret(name="twitter_bearer_token", default=None)

    twitter = environ.group(Twitter)


cfg: TrackConfig = TrackConfig.from_environ(
    environ={
        "CREATED": 1663989263,
        "DISCORD_OWNER_IDS": {212466672450142208, 113104128783159296},
        "CHANNELS_FAILED_RENDERS": 1010834704804614184,
    }
)

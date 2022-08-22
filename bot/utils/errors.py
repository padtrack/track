class SilentError(Exception):
    pass


class CustomError(Exception):
    def __init__(self, message, ephemeral=False):
        self.message = message
        self.ephemeral = ephemeral

        # NOBUG: will not actually render as ephemeral
        # if interaction was deferred without ephemeral


class RenderError(Exception):
    def __init__(self, message):
        self.message = message


class ArenaMismatchError(RenderError):
    def __init__(self):
        super().__init__("Provided replays are not from the same match.")


class UnsupportedBattleTypeError(RenderError):
    def __init__(self):
        super().__init__("Unsupported battle type.")


class VersionNotFoundError(RenderError):
    def __init__(self):
        super().__init__("Unsupported Version (< 0.11.6).")

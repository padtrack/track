class SilentError(Exception):
    pass


class CustomError(Exception):
    def __init__(self, message, ephemeral=False):
        self.message = message
        self.ephemeral = ephemeral

        # when using ephemeral errors, ensure any defer is also ephemeral!


class RenderError(Exception):
    should_reupload = False

    def __init__(self, message):
        self.message = message

    def __str__(self) -> str:
        return self.message


class ReadingError(RenderError):
    should_reupload = True

    def __init__(self):
        super().__init__("Error while reading replay.")


class RenderingError(RenderError):
    should_reupload = True

    def __init__(self):
        super().__init__("Rendering failed.")


class UnsupportedBattleTypeError(RenderError):
    def __init__(self):
        super().__init__("Unsupported battle type.")


class VersionNotFoundError(RenderError):
    def __init__(self):
        super().__init__("Unsupported Version. Only 0.11.6 and 0.11.7 for now!")

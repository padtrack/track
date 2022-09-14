__all__ = ["SI", "IT", "ST", "config", "APIError"]

from typing import TypeVar
import datetime

import dacite


SI = TypeVar("SI", bound=int)  # string -> int
IT = TypeVar("IT", bound=datetime.datetime)  # "int" timestamp
ST = TypeVar("ST", bound=datetime.datetime)  # "string" timestamp


config = dacite.Config(
    type_hooks={
        SI: lambda x: int(x),
        IT: lambda x: datetime.datetime.fromtimestamp(x),
        ST: lambda x: datetime.datetime.fromisoformat(x),
    },
    check_types=False,
)


class APIError(Exception):
    def __init__(self, code: int):
        self.code = code

from __future__ import annotations
__all__ = [
    "Player",
    "PartialPlayer",
    "FullPlayer",
    "ClanRole",
    "ClanMemberStatistics",
    "FullClan",
    "SeasonsData",
    "BuildingsData",
]

from typing import Dict, List, Optional
from dataclasses import dataclass

from .urls import CLANS, URLS
from .utils import *


# --- Players ---

@dataclass
class Player:
    region: str
    id: int
    name: str
    hidden_profile: bool
    clan_role: Optional[ClanRole]
    is_empty: bool
    used_access_code: Optional[str]

    @property
    def profile_url(self) -> str:
        url = URLS[self.region]
        return f"{url}/community/accounts/{self.id}-{self.name}"

    @property
    def wows_numbers_url(self) -> str:
        return f"https://{self.region}.wows-numbers.com/player/{self.id},{self.name}"


@dataclass
class PartialPlayer(Player):
    statistics: dict[str, ClanMemberStatistics]


@dataclass
class FullPlayer(Player):
    statistics: dict[str, dict[str, int]]

    activated_at: IT
    created_at: IT
    last_battle_time: IT

    karma: int
    leveling_points: int
    leveling_tier: int


# --- Partial Clans ---


@dataclass
class ClanRole:
    clan: PartialClan
    clan_id: int
    joined_at: ST
    role: str


@dataclass
class PartialClan:
    color: int
    name: str
    members_count: int
    tag: str


# --- Clans ---

@dataclass
class ClanMemberStatistics:
    id: int
    name: str
    last_battle_time: IT

    days_in_clan: int
    battles_count: int
    battles_per_day: float

    damage_per_battle: float
    frags_per_battle: float
    exp_per_battle: float
    wins_percentage: float


@dataclass
class FullClan:
    region: str

    wows_ladder: Optional[ClanLadder]
    achievements: list[ClanAchievement]
    buildings: dict[str, ClanBuilding]
    clan: ClanInfo

    @property
    def profile_url(self):
        return f"{CLANS[self.region][:-3]}/clan-profile/{self.clan.id}"


@dataclass
class ClanLadder:
    team_number: int  # i.e. Alpha, Bravo "ratings"
    leading_team_number: int
    league: int
    division: int
    season_number: int
    color: int
    status: str  # active, ?...
    is_qualified: bool

    wins_count: int
    last_win_at: Optional[ST]
    battles_count: int
    total_battles_count: int
    last_battle_at: Optional[ST]

    current_winning_streak: int
    longest_winning_streak: int

    initial_public_rating: int
    public_rating: int
    division_rating: int
    division_rating_max: int

    max_position: ClanMaxPosition


@dataclass
class ClanMaxPosition:
    division_rating: int
    public_rating: int
    league: int  # i.e. Squall, Gale, etc.
    division: int


@dataclass
class ClanAchievement:
    count: int
    cd: int


@dataclass
class ClanBuilding:
    id: int
    name: str
    level: int
    modifiers: list[int]


@dataclass
class ClanInfo:
    id: int
    name: str
    tag: str
    description: str
    raw_description: str
    created_at: ST

    members_count: int
    max_members_count: int

    recruiting_policy: str
    recruiting_restrictions: dict


# --- Seasons ---

@dataclass
class SeasonsData:
    data: Dict[SI, Season]

    @property
    def last_clan_season(self):
        return max(
            season_id
            for season_id in self.data
            if season_id < 100
        )


@dataclass
class Season:
    season_id: int
    name: str

    start_time: IT
    finish_time: IT
    ship_tier_min: int
    ship_tier_max: int
    division_points: int
    leagues: List[League]


@dataclass
class League:
    name: str
    icon: str
    color: str


# --- Buildings ---

@dataclass
class BuildingsData:
    building_types: Dict[SI, BuildingType]
    buildings: Dict[SI, Building]
    clans_roles: Dict[str, str]

    def type_of(self, building_id: int):
        if not (building := self.buildings.get(building_id, None)):
            return None
        return self.building_types[building.building_type_id]

    def upgrades_count(self, building_type: BuildingType):
        return sum(
            1
            for building in self.buildings.values()
            if building.building_type_id == building_type.building_type_id
        ) - 1


@dataclass
class BuildingType:
    building_type_id: int
    name: str


@dataclass
class Building:
    building_id: int
    building_type_id: int
    name: str
    cost: int

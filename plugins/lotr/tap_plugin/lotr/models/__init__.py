"""LOTR plugin models package.

Re-exports all model classes so existing imports like
``from tap_plugin.lotr.models import Character`` continue to work.
"""

from tap_plugin.lotr.models.artifact import Artifact
from tap_plugin.lotr.models.character import Character
from tap_plugin.lotr.models.citadel import Citadel
from tap_plugin.lotr.models.faction import Faction
from tap_plugin.lotr.models.location import Location
from tap_plugin.lotr.models.race import Race
from tap_plugin.lotr.models.realm import Realm
from tap_plugin.lotr.models.sentinel import Sentinel
from tap_plugin.lotr.models.wanderer import Wanderer

__all__ = [
    "Artifact",
    "Character",
    "Citadel",
    "Faction",
    "Location",
    "Race",
    "Realm",
    "Sentinel",
    "Wanderer",
]

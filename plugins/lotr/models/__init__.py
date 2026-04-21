"""LOTR plugin models package.

Re-exports all model classes so existing imports like
``from plugins.lotr.models import Character`` continue to work.
"""

from plugins.lotr.models.artifact import Artifact
from plugins.lotr.models.character import Character
from plugins.lotr.models.citadel import Citadel
from plugins.lotr.models.faction import Faction
from plugins.lotr.models.location import Location
from plugins.lotr.models.race import Race
from plugins.lotr.models.realm import Realm
from plugins.lotr.models.sentinel import Sentinel
from plugins.lotr.models.wanderer import Wanderer

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

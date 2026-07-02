"""Comprehensive edge constraint tests using Lord of the Rings entities.

This test suite exercises all constraint patterns:
- Valid edges (basic happy path)
- Invalid edges (wrong edge type, wrong target)
- Multiple target types (one edge type, many valid targets)
- Self-referential edges (location -> location)
- Bidirectional edges (faction <-> faction)
- Wildcard outbound (sentinel -> anything)
- Blocked outbound (race -> nothing)
- Blocked inbound (citadel <- nothing)
- Unconstrained entities (wanderer has no restrictions)
- Cross-constraint failures (outbound ok, inbound blocked)
- Edge type not defined in constraints
- Correct edge type but wrong target type
"""

import pytest

# Import models to trigger constraint registration via __init_subclass__
import tap_plugin.lotr.models  # noqa: F401
from tap_grid.exceptions import EdgePropertyValidationError, InvalidEdgeError
from tap_grid.services import create_edge, create_entity, update_edge_properties

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def frodo():
    """Create a character entity (Frodo)."""
    return create_entity("character", name="Frodo Baggins")


@pytest.fixture
def gandalf():
    """Create another character entity (Gandalf)."""
    return create_entity("character", name="Gandalf the Grey")


@pytest.fixture
def sauron():
    """Create an antagonist character (Sauron)."""
    return create_entity("character", name="Sauron")


@pytest.fixture
def the_shire():
    """Create a location entity (The Shire)."""
    return create_entity("location", name="The Shire")


@pytest.fixture
def mordor():
    """Create another location entity (Mordor)."""
    return create_entity("location", name="Mordor")


@pytest.fixture
def bag_end():
    """Create a sub-location entity (Bag End)."""
    return create_entity("location", name="Bag End")


@pytest.fixture
def one_ring():
    """Create an artifact entity (The One Ring)."""
    return create_entity("artifact", name="The One Ring")


@pytest.fixture
def sting():
    """Create another artifact entity (Sting)."""
    return create_entity("artifact", name="Sting")


@pytest.fixture
def hobbit():
    """Create a race entity (Hobbit)."""
    return create_entity("race", name="Hobbit")


@pytest.fixture
def elf():
    """Create another race entity (Elf)."""
    return create_entity("race", name="Elf")


@pytest.fixture
def fellowship():
    """Create a faction entity (The Fellowship)."""
    return create_entity("faction", name="The Fellowship of the Ring")


@pytest.fixture
def mordor_forces():
    """Create another faction entity (Mordor Forces)."""
    return create_entity("faction", name="Forces of Mordor")


@pytest.fixture
def rohan():
    """Create another faction entity (Rohan)."""
    return create_entity("faction", name="Riders of Rohan")


@pytest.fixture
def sentinel():
    """Create a sentinel entity (for wildcard tests)."""
    return create_entity("sentinel", name="The Watcher")


@pytest.fixture
def citadel():
    """Create a citadel entity (for blocked inbound tests)."""
    return create_entity("citadel", name="Minas Tirith Citadel")


@pytest.fixture
def wanderer():
    """Create a wanderer entity (unconstrained)."""
    return create_entity("wanderer", name="Tom Bombadil")


# =============================================================================
# Basic Valid Edge Tests
# =============================================================================


@pytest.mark.django_db
class TestBasicValidEdges:
    """Test that valid edges succeed as expected."""

    def test_character_wields_artifact(self, frodo, sting):
        """Character can WIELDS an artifact."""
        edge = create_edge(frodo, sting, "WIELDS")
        assert edge.edge_type == "WIELDS"
        assert edge.from_entity == frodo
        assert edge.to_entity == sting

    def test_character_located_in_location(self, frodo, the_shire):
        """Character can be LOCATED_IN a location."""
        edge = create_edge(frodo, the_shire, "LOCATED_IN")
        assert edge.edge_type == "LOCATED_IN"

    def test_character_rules_location(self, sauron, mordor):
        """Character can RULES a location."""
        edge = create_edge(sauron, mordor, "RULES")
        assert edge.edge_type == "RULES"

    def test_character_belongs_to_race(self, frodo, hobbit):
        """Character can BELONGS_TO a race."""
        edge = create_edge(frodo, hobbit, "BELONGS_TO")
        assert edge.edge_type == "BELONGS_TO"

    def test_character_member_of_faction(self, frodo, fellowship):
        """Character can be MEMBER_OF a faction."""
        edge = create_edge(frodo, fellowship, "MEMBER_OF")
        assert edge.edge_type == "MEMBER_OF"

    def test_artifact_forged_in_location(self, one_ring, mordor):
        """Artifact can be FORGED_IN a location."""
        edge = create_edge(one_ring, mordor, "FORGED_IN")
        assert edge.edge_type == "FORGED_IN"


# =============================================================================
# Self-Referential Edge Tests (location -> location)
# =============================================================================


@pytest.mark.django_db
class TestSelfReferentialEdges:
    """Test edges where source and target are the same type."""

    def test_location_contains_location(self, the_shire, bag_end):
        """Location can CONTAINS another location."""
        edge = create_edge(the_shire, bag_end, "CONTAINS")
        assert edge.edge_type == "CONTAINS"
        assert edge.from_entity == the_shire
        assert edge.to_entity == bag_end

    def test_multiple_containment_edges(self, the_shire, bag_end, mordor):
        """Multiple CONTAINS edges from one location."""
        edge1 = create_edge(the_shire, bag_end, "CONTAINS")
        # Mordor can also contain things
        mount_doom = create_entity("location", name="Mount Doom")
        edge2 = create_edge(mordor, mount_doom, "CONTAINS")
        assert edge1.edge_type == "CONTAINS"
        assert edge2.edge_type == "CONTAINS"


# =============================================================================
# Bidirectional Edge Tests (faction <-> faction)
# =============================================================================


@pytest.mark.django_db
class TestBidirectionalEdges:
    """Test edges that can go both directions between same types."""

    def test_faction_allies_with_faction(self, fellowship, rohan):
        """Faction can ALLIES_WITH another faction."""
        edge = create_edge(fellowship, rohan, "ALLIES_WITH")
        assert edge.edge_type == "ALLIES_WITH"

    def test_faction_enemies_with_faction(self, fellowship, mordor_forces):
        """Faction can ENEMIES_WITH another faction."""
        edge = create_edge(fellowship, mordor_forces, "ENEMIES_WITH")
        assert edge.edge_type == "ENEMIES_WITH"

    def test_bidirectional_alliance(self, fellowship, rohan):
        """Both factions can ally with each other (two edges)."""
        edge1 = create_edge(fellowship, rohan, "ALLIES_WITH")
        edge2 = create_edge(rohan, fellowship, "ALLIES_WITH")
        assert edge1.from_entity == fellowship
        assert edge2.from_entity == rohan

    def test_character_allies_with_character(self, frodo, gandalf):
        """Characters can also ALLIES_WITH each other."""
        edge = create_edge(frodo, gandalf, "ALLIES_WITH")
        assert edge.edge_type == "ALLIES_WITH"

    def test_character_enemies_with_character(self, frodo, sauron):
        """Characters can ENEMIES_WITH each other."""
        edge = create_edge(frodo, sauron, "ENEMIES_WITH")
        assert edge.edge_type == "ENEMIES_WITH"


# =============================================================================
# Wildcard Edge Tests (sentinel -> anything)
# =============================================================================


@pytest.mark.django_db
class TestWildcardEdges:
    """Test wildcard constraints where outbound allows any target.

    IMPORTANT: Wildcard on SOURCE side doesn't override TARGET's inbound
    constraints. Both sides must agree for an edge to be valid.
    """

    def test_sentinel_references_another_sentinel(self, sentinel):
        """Sentinel -> sentinel works (both have matching constraints)."""
        other_sentinel = create_entity("sentinel", name="Palantir")
        edge = create_edge(sentinel, other_sentinel, "REFERENCES")
        assert edge.edge_type == "REFERENCES"

    def test_sentinel_references_wanderer(self, sentinel, wanderer):
        """Sentinel -> wanderer works (wanderer has no inbound constraints)."""
        edge = create_edge(sentinel, wanderer, "REFERENCES")
        assert edge.edge_type == "REFERENCES"

    def test_sentinel_blocked_by_target_inbound_character(self, sentinel, frodo):
        """Sentinel wildcard blocked by character's inbound constraints."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(sentinel, frodo, "REFERENCES")
        assert "character cannot receive 'REFERENCES' edges" in str(exc_info.value)

    def test_sentinel_blocked_by_target_inbound_location(self, sentinel, the_shire):
        """Sentinel wildcard blocked by location's inbound constraints."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(sentinel, the_shire, "REFERENCES")
        assert "location cannot receive 'REFERENCES' edges" in str(exc_info.value)

    def test_sentinel_blocked_by_target_inbound_artifact(self, sentinel, one_ring):
        """Sentinel wildcard blocked by artifact's inbound constraints."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(sentinel, one_ring, "REFERENCES")
        assert "artifact cannot receive 'REFERENCES' edges" in str(exc_info.value)

    def test_sentinel_blocked_by_target_inbound_faction(self, sentinel, fellowship):
        """Sentinel wildcard blocked by faction's inbound constraints."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(sentinel, fellowship, "REFERENCES")
        assert "faction cannot receive 'REFERENCES' edges" in str(exc_info.value)

    def test_sentinel_cannot_use_non_references_edge(self, sentinel, wanderer):
        """Sentinel can only use REFERENCES edge type (outbound constraint)."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(sentinel, wanderer, "WIELDS")
        assert "cannot create 'WIELDS' edges" in str(exc_info.value)


# =============================================================================
# Blocked Outbound Tests (race -> nothing)
# =============================================================================


@pytest.mark.django_db
class TestBlockedOutbound:
    """Test entities with empty outbound constraints (block all)."""

    def test_race_cannot_create_any_edge(self, hobbit, frodo):
        """Race has empty OUTBOUND_EDGES, cannot create any edges."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(hobbit, frodo, "BELONGS_TO")
        assert "cannot create any outbound edges" in str(exc_info.value)

    def test_race_cannot_create_edge_to_location(self, hobbit, the_shire):
        """Race cannot create edges even with different edge type."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(hobbit, the_shire, "LOCATED_IN")
        assert "cannot create any outbound edges" in str(exc_info.value)

    def test_race_cannot_create_edge_to_another_race(self, hobbit, elf):
        """Race cannot create edges to other races."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(hobbit, elf, "ALLIES_WITH")
        assert "cannot create any outbound edges" in str(exc_info.value)


# =============================================================================
# Blocked Inbound Tests (citadel <- nothing)
# =============================================================================


@pytest.mark.django_db
class TestBlockedInbound:
    """Test entities with empty inbound constraints (block all).

    To isolate the inbound constraint, we use wanderer (no outbound constraints)
    as the source. This ensures the inbound block is what fails, not outbound.
    """

    def test_citadel_blocks_inbound_from_unconstrained_source(self, wanderer, citadel):
        """Citadel blocks even unconstrained sources (wanderer)."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(wanderer, citadel, "VISITS")
        assert "cannot receive any inbound edges" in str(exc_info.value)

    def test_citadel_blocks_any_edge_type(self, wanderer, citadel):
        """Citadel blocks all edge types from any source."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(wanderer, citadel, "PROTECTS")
        assert "cannot receive any inbound edges" in str(exc_info.value)

    def test_constrained_source_fails_at_inbound_block(self, frodo, citadel):
        """Citadel's explicit inbound block is checked and fails.

        Even though edge constraint allows character -> location for LOCATED_IN,
        citadel's explicit block (INBOUND_EDGES=[]) cannot be overridden.
        """
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(frodo, citadel, "LOCATED_IN")
        # Explicit block wins over edge constraint
        assert "cannot receive any inbound edges" in str(exc_info.value)

    def test_citadel_can_still_create_edges(self, citadel, the_shire):
        """Citadel can create outbound edges (PROTECTS) to location."""
        edge = create_edge(citadel, the_shire, "PROTECTS")
        assert edge.edge_type == "PROTECTS"


# =============================================================================
# Unconstrained Entity Tests (wanderer)
# =============================================================================


@pytest.mark.django_db
class TestUnconstrainedEntity:
    """Test entities with no constraint definitions.

    Wanderer has no OUTBOUND_EDGES or INBOUND_EDGES defined, meaning:
    - Wanderer can CREATE any edge type (no outbound restrictions)
    - Wanderer can RECEIVE any edge type (no inbound restrictions)

    However, if the TARGET has inbound constraints, those still apply.
    Both sides must agree for an edge to be valid.
    """

    def test_wanderer_to_wanderer_any_edge(self, wanderer):
        """Wanderer -> wanderer works with any edge type."""
        goldberry = create_entity("wanderer", name="Goldberry")
        edge = create_edge(wanderer, goldberry, "LOVES")
        assert edge.edge_type == "LOVES"

    def test_wanderer_receives_edge_from_another_wanderer(self, wanderer):
        """Unconstrained source can send any edge to unconstrained target."""
        tom = wanderer
        goldberry = create_entity("wanderer", name="Goldberry")
        edge = create_edge(goldberry, tom, "ADMIRES")
        assert edge.edge_type == "ADMIRES"

    def test_constrained_source_still_applies_outbound(self, frodo, wanderer):
        """Even though wanderer has no inbound, source outbound still applies."""
        # Character's ALLIES_WITH only allows 'character' targets
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(frodo, wanderer, "ALLIES_WITH")
        assert "cannot create 'ALLIES_WITH' edge to wanderer" in str(exc_info.value)

    def test_wanderer_blocked_by_target_inbound(self, wanderer, frodo):
        """Wanderer blocked when target has inbound constraints."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(wanderer, frodo, "MYSTERIOUS_LINK")
        assert "character cannot receive 'MYSTERIOUS_LINK' edges" in str(exc_info.value)

    def test_wanderer_can_use_allowed_edge_to_constrained_target(self, wanderer, frodo):
        """Wanderer succeeds when using edge type allowed by target's inbound."""
        # Character's inbound allows ALLIES_WITH from character
        # But wanderer is not a character, so this still fails
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(wanderer, frodo, "ALLIES_WITH")
        assert "character cannot receive 'ALLIES_WITH' edge from wanderer" in str(exc_info.value)

    def test_wanderer_multiple_edges_to_other_wanderer(self, wanderer):
        """Wanderer can form multiple different edge types."""
        goldberry = create_entity("wanderer", name="Goldberry")
        edge1 = create_edge(wanderer, goldberry, "LOVES")
        edge2 = create_edge(wanderer, goldberry, "PROTECTS")
        edge3 = create_edge(wanderer, goldberry, "TEACHES")
        assert edge1.edge_type == "LOVES"
        assert edge2.edge_type == "PROTECTS"
        assert edge3.edge_type == "TEACHES"


# =============================================================================
# Invalid Edge Type Tests
# =============================================================================


@pytest.mark.django_db
class TestInvalidEdgeType:
    """Test that undefined edge types are blocked when constraints exist."""

    def test_character_cannot_use_undefined_edge_type(self, frodo, the_shire):
        """Character cannot use CONQUERS (not in their constraints)."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(frodo, the_shire, "CONQUERS")
        assert "cannot create 'CONQUERS' edges" in str(exc_info.value)
        assert "Allowed:" in str(exc_info.value)

    def test_artifact_cannot_use_wields(self, one_ring, frodo):
        """Artifact cannot WIELDS (that's backwards)."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(one_ring, frodo, "WIELDS")
        assert "cannot create 'WIELDS' edges" in str(exc_info.value)

    def test_location_cannot_use_member_of(self, the_shire, fellowship):
        """Location cannot use MEMBER_OF edge."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(the_shire, fellowship, "MEMBER_OF")
        assert "cannot create 'MEMBER_OF' edges" in str(exc_info.value)


# =============================================================================
# Invalid Target Type Tests
# =============================================================================


@pytest.mark.django_db
class TestInvalidTargetType:
    """Test that correct edge type to wrong target is blocked."""

    def test_character_cannot_wield_location(self, frodo, the_shire):
        """Character can WIELDS, but not to a location.

        Edge constraint allows character as source, but location's inbound
        doesn't include WIELDS, so target side rejects it.
        """
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(frodo, the_shire, "WIELDS")
        assert "cannot receive 'WIELDS' edges" in str(exc_info.value)

    def test_character_cannot_belong_to_faction(self, frodo, fellowship):
        """BELONGS_TO only works for race, not faction."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(frodo, fellowship, "BELONGS_TO")
        assert "cannot create 'BELONGS_TO' edge to faction" in str(exc_info.value)

    def test_artifact_cannot_forge_in_character(self, one_ring, frodo):
        """Artifact can be FORGED_IN location, not character.

        Edge constraint allows artifact as source, but character's inbound
        doesn't include FORGED_IN, so target side rejects it.
        """
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(one_ring, frodo, "FORGED_IN")
        assert "cannot receive 'FORGED_IN' edges" in str(exc_info.value)

    def test_faction_cannot_ally_with_character(self, fellowship, frodo):
        """Faction can ALLIES_WITH faction, not character."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(fellowship, frodo, "ALLIES_WITH")
        assert "cannot create 'ALLIES_WITH' edge to character" in str(exc_info.value)


# =============================================================================
# Inbound Constraint Violation Tests
# =============================================================================


@pytest.mark.django_db
class TestInboundConstraintViolation:
    """Test that inbound constraints are checked independently."""

    def test_location_cannot_receive_wields(self, frodo, the_shire):
        """Location's inbound doesn't allow WIELDS from character."""
        # Character defines WIELDS -> artifact, so this fails outbound first
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(frodo, the_shire, "WIELDS")
        assert "WIELDS" in str(exc_info.value)

    def test_artifact_cannot_receive_belongs_to(self, frodo, one_ring):
        """Artifact's inbound only allows WIELDS from character."""
        # First fails outbound: character's BELONGS_TO only goes to race
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(frodo, one_ring, "BELONGS_TO")
        assert "BELONGS_TO" in str(exc_info.value)

    def test_race_cannot_receive_from_artifact(self, one_ring, hobbit):
        """Race can only receive BELONGS_TO from character, not artifact."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(one_ring, hobbit, "BELONGS_TO")
        # Artifact can't create BELONGS_TO (outbound fails first)
        assert "cannot create 'BELONGS_TO' edges" in str(exc_info.value)

    def test_faction_cannot_receive_allies_from_artifact(self, one_ring, fellowship):
        """Faction's inbound ALLIES_WITH only from faction, not artifact."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(one_ring, fellowship, "ALLIES_WITH")
        # Artifact can't create ALLIES_WITH (outbound fails first)
        assert "cannot create 'ALLIES_WITH' edges" in str(exc_info.value)


# =============================================================================
# Cross-Constraint Tests (outbound ok, inbound blocked)
# =============================================================================


@pytest.mark.django_db
class TestCrossConstraintValidation:
    """Test cases where outbound allows but inbound blocks."""

    def test_sentinel_to_citadel_blocked_by_inbound(self, sentinel, citadel):
        """Sentinel can REFERENCES anything (outbound), but citadel blocks inbound."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(sentinel, citadel, "REFERENCES")
        assert "cannot receive any inbound edges" in str(exc_info.value)

    def test_wanderer_to_citadel_blocked_by_inbound(self, wanderer, citadel):
        """Wanderer has no outbound constraints, but citadel blocks inbound."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(wanderer, citadel, "VISITS")
        assert "cannot receive any inbound edges" in str(exc_info.value)


# =============================================================================
# Multiple Valid Targets Tests
# =============================================================================


@pytest.mark.django_db
class TestMultipleValidTargets:
    """Test edges with multiple allowed target types."""

    def test_character_located_in_accepts_location(self, frodo, the_shire):
        """LOCATED_IN works with location."""
        edge = create_edge(frodo, the_shire, "LOCATED_IN")
        assert edge.edge_type == "LOCATED_IN"

    def test_character_rules_accepts_location(self, sauron, mordor):
        """RULES also works with location (same constraint entry)."""
        edge = create_edge(sauron, mordor, "RULES")
        assert edge.edge_type == "RULES"


# =============================================================================
# Edge Properties Tests
# =============================================================================


@pytest.mark.django_db
class TestEdgeProperties:
    """Test that edge properties work with constraints."""

    def test_edge_with_properties(self, frodo, sting):
        """Edge can have properties attached."""
        edge = create_edge(frodo, sting, "WIELDS", properties={"acquired_at": "Bag End", "is_glowing": True})
        assert edge.properties["acquired_at"] == "Bag End"
        assert edge.properties["is_glowing"] is True

    def test_multiple_edges_same_type(self, frodo, gandalf, sauron):
        """Character can have multiple ENEMIES_WITH edges."""
        edge1 = create_edge(frodo, sauron, "ENEMIES_WITH")
        edge2 = create_edge(gandalf, sauron, "ENEMIES_WITH")
        assert edge1.to_entity == sauron
        assert edge2.to_entity == sauron


# =============================================================================
# Constraint Strictness Tests
# =============================================================================


@pytest.mark.django_db
class TestConstraintStrictness:
    """Test that constraints are enforced strictly."""

    def test_constrained_entity_cannot_use_random_edge(self, frodo, gandalf):
        """Constrained entities cannot use undefined edge types."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(frodo, gandalf, "TEACHES")
        assert "cannot create 'TEACHES' edges" in str(exc_info.value)

    def test_case_sensitivity_of_edge_types(self, frodo, sting):
        """Edge types are case-sensitive (lowercase should fail)."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            create_edge(frodo, sting, "wields")  # lowercase
        assert "cannot create 'wields' edges" in str(exc_info.value)

    def test_case_sensitivity_matters(self, frodo, sting):
        """Only ALL CAPS edge types work."""
        # This should succeed
        edge = create_edge(frodo, sting, "WIELDS")
        assert edge.edge_type == "WIELDS"


# =============================================================================
# Edge Property Validation Tests
# =============================================================================


@pytest.mark.django_db
class TestEdgePropertyValidation:
    """Test edge property schema validation for WIELDS and MENTORS.

    WIELDS: optional properties — proficiency (enum) and primary (bool).
    MENTORS: required discipline (string), optional duration_years (int >= 0),
             additionalProperties: False.
    """

    def test_wields_no_properties_accepted(self, frodo, sting):
        """WIELDS with empty properties is valid — no required fields."""
        edge = create_edge(frodo, sting, "WIELDS")
        assert edge.properties == {}

    def test_wields_valid_proficiency(self, frodo, sting):
        """WIELDS with a valid enum value for proficiency."""
        edge = create_edge(frodo, sting, "WIELDS", properties={"proficiency": "master"})
        assert edge.properties["proficiency"] == "master"

    def test_wields_valid_all_fields(self, frodo, sting):
        """WIELDS with both proficiency and primary set."""
        edge = create_edge(frodo, sting, "WIELDS", properties={"proficiency": "apprentice", "primary": True})
        assert edge.properties == {"proficiency": "apprentice", "primary": True}

    def test_wields_invalid_proficiency_enum(self, frodo, sting):
        """WIELDS rejects proficiency values outside the allowed enum."""
        with pytest.raises(EdgePropertyValidationError):
            create_edge(frodo, sting, "WIELDS", properties={"proficiency": "expert"})

    def test_wields_invalid_primary_type(self, frodo, sting):
        """WIELDS rejects a non-boolean primary field."""
        with pytest.raises(EdgePropertyValidationError):
            create_edge(frodo, sting, "WIELDS", properties={"primary": "yes"})

    def test_wields_update_to_valid_properties(self, frodo, sting):
        """update_edge_properties() accepts valid WIELDS properties."""
        edge = create_edge(frodo, sting, "WIELDS")
        updated = update_edge_properties(edge, {"proficiency": "novice", "primary": False})
        updated.refresh_from_db()
        assert updated.properties == {"proficiency": "novice", "primary": False}

    def test_wields_update_to_invalid_properties(self, frodo, sting):
        """update_edge_properties() rejects invalid WIELDS properties."""
        edge = create_edge(frodo, sting, "WIELDS")
        with pytest.raises(EdgePropertyValidationError):
            update_edge_properties(edge, {"proficiency": "legendary"})

    def test_mentors_requires_discipline(self, gandalf, frodo):
        """MENTORS requires the discipline field."""
        with pytest.raises(EdgePropertyValidationError):
            create_edge(gandalf, frodo, "MENTORS", properties={})

    def test_mentors_valid_required_only(self, gandalf, frodo):
        """MENTORS succeeds with just the required discipline field."""
        edge = create_edge(gandalf, frodo, "MENTORS", properties={"discipline": "wizardry"})
        assert edge.properties["discipline"] == "wizardry"

    def test_mentors_valid_all_fields(self, gandalf, frodo):
        """MENTORS succeeds with discipline and duration_years."""
        edge = create_edge(gandalf, frodo, "MENTORS", properties={"discipline": "courage", "duration_years": 17})
        assert edge.properties == {"discipline": "courage", "duration_years": 17}

    def test_mentors_rejects_negative_duration(self, gandalf, frodo):
        """MENTORS rejects a negative duration_years value."""
        with pytest.raises(EdgePropertyValidationError):
            create_edge(gandalf, frodo, "MENTORS", properties={"discipline": "lore", "duration_years": -1})

    def test_mentors_rejects_additional_properties(self, gandalf, frodo):
        """MENTORS rejects unknown fields (additionalProperties: False)."""
        with pytest.raises(EdgePropertyValidationError):
            create_edge(gandalf, frodo, "MENTORS", properties={"discipline": "magic", "secret_technique": "fireball"})

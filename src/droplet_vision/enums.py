"""Separate process states, observed objects, and timing validation status."""

from enum import Enum


class DropletState(str, Enum):
    EVAPORATION = "EVAPORATION"
    NUCLEATION = "NUCLEATION"
    BUBBLE_GROWTH = "BUBBLE_GROWTH"
    PUFFING = "PUFFING"
    MICRO_EXPLOSION = "MICRO_EXPLOSION"
    IGNITION = "IGNITION"
    POST_BREAKUP = "POST_BREAKUP"
    UNCERTAIN = "UNCERTAIN"


class TimingStatus(str, Enum):
    TIMING_VALIDATED = "TIMING_VALIDATED"
    TIMING_VALIDATED_WITH_DECIMATION = "TIMING_VALIDATED_WITH_DECIMATION"
    TIMING_MISMATCH_UNRESOLVED = "TIMING_MISMATCH_UNRESOLVED"
    TIMING_UNKNOWN = "TIMING_UNKNOWN"


class ObjectType(str, Enum):
    PARENT_DROPLET = "parent_droplet"
    INTERNAL_CAVITY_CANDIDATE = "internal_cavity_candidate"
    DAUGHTER_DROPLET = "daughter_droplet"
    FLAME = "flame"
    SOOT = "soot"
    SUPPORT_STRUCTURE = "support_structure"

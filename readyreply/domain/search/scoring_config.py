"""Every number that shapes ranking lives here, named and documented."""

from types import MappingProxyType

MAX_QUERY_CHARS = 200

EXACT_STRENGTH = 1.0
SYNONYM_STRENGTH = 0.9
PREFIX_STRENGTH = 0.75
FUZZY_STRENGTH_ONE_EDIT = 0.6
FUZZY_PENALTY_PER_EXTRA_EDIT = 0.1

PREFIX_MIN_CHARS = 3
FUZZY_ONE_EDIT_MIN_CHARS = 4
FUZZY_TWO_EDITS_MIN_CHARS = 8

TITLE_WEIGHT = 3.0
TAG_WEIGHT = 2.5
CATEGORY_WEIGHT = 1.5
BODY_WEIGHT = 1.0

# Final score = sum of token scores * (COVERAGE_BASE + COVERAGE_BONUS * matched_share)
COVERAGE_BASE = 0.5
COVERAGE_BONUS = 0.5

MIN_SCORE = 0.3

FIELD_WEIGHTS = MappingProxyType(
    {"title": TITLE_WEIGHT, "tags": TAG_WEIGHT, "category": CATEGORY_WEIGHT, "body": BODY_WEIGHT}
)

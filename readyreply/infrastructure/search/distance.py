"""Edit distance backed by rapidfuzz (C++), used by the fuzzy scorer."""

from rapidfuzz.distance import OSA


class RapidfuzzDistance:
    def distance(self, left: str, right: str, limit: int) -> int | None:
        result = OSA.distance(left, right, score_cutoff=limit)
        return result if result <= limit else None

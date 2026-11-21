"""Test doubles for domain ports."""


class OsaDistance:
    """Optimal string alignment distance (Levenshtein plus adjacent swaps)."""

    def distance(self, left: str, right: str, limit: int) -> int | None:
        previous: list[int] = []
        current = list(range(len(right) + 1))
        for i in range(1, len(left) + 1):
            before, previous, current = previous, current, [i] + [0] * len(right)
            for j in range(1, len(right) + 1):
                cost = 0 if left[i - 1] == right[j - 1] else 1
                current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
                if i > 1 and j > 1 and left[i - 1] == right[j - 2] and left[i - 2] == right[j - 1]:
                    current[j] = min(current[j], before[j - 2] + 1)
        return current[-1] if current[-1] <= limit else None

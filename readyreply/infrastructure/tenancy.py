"""v1 serves one business. A SaaS version resolves it from the subdomain or the session."""

SINGLE_BUSINESS_ID = 1


class SingleBusinessResolver:
    def current(self) -> int:
        return SINGLE_BUSINESS_ID

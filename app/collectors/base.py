"""Collector interface."""
from datetime import date as date_cls


class BaseCollector:
    channel: str = ""

    def fetch(self, term: str, day: date_cls) -> int:
        """Return the buzz count for `term` on `day`.

        Real API collectors ignore `day` (they can only report "now").
        The mock collector uses it to synthesize history.
        """
        raise NotImplementedError

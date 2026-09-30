"""
Time grid for the departmental routine.

The whole scheduler runs on ONE atomic unit: a 50-minute period.
A theory class is 1 period. A 2.5-hour lab is 3 periods.

Breaks are NOT periods. They are gaps between period indices. That is what
splits the day into "contiguous blocks" -- runs of periods with no break in
between. A lab must fit entirely inside one block, which is how we stop a lab
from being scheduled across the lunch break or across midnight.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Period:
    name: str
    start: str
    end: str

    @property
    def label(self) -> str:
        return f"{self.start}-{self.end}"


@dataclass(frozen=True)
class Break:
    name: str
    after_period: str  # break happens immediately after this period
    start: str
    end: str


class TimeGrid:
    """Maps between (day, period) pairs and flat slot indices.

    A *slot* is a flat integer index: slot = day_index * n_periods + period_index.
    Flat indices make every conflict constraint a simple one-dimensional sum.
    """

    def __init__(
        self,
        days: list[str],
        periods: list[Period],
        breaks: list[Break],
        lab_periods: int = 3,
    ) -> None:
        self.days = days
        self.periods = periods
        self.breaks = breaks
        self.lab_periods = lab_periods

        self.n_days = len(days)
        self.n_periods = len(periods)
        self.n_slots = self.n_days * self.n_periods

        self._period_index = {p.name: i for i, p in enumerate(periods)}
        self._day_index = {d: i for i, d in enumerate(days)}

        self.blocks = self._compute_blocks()

    # ------------------------------------------------------------------ setup

    def _compute_blocks(self) -> list[list[int]]:
        """Split period indices into contiguous runs, cutting at every break."""
        cut_after: set[int] = set()
        for br in self.breaks:
            if br.after_period not in self._period_index:
                raise ValueError(
                    f"Break {br.name!r} says it follows period {br.after_period!r}, "
                    f"which is not in the period list."
                )
            cut_after.add(self._period_index[br.after_period])

        blocks: list[list[int]] = []
        current: list[int] = []
        for i in range(self.n_periods):
            current.append(i)
            if i in cut_after or i == self.n_periods - 1:
                blocks.append(current)
                current = []
        return blocks

    # -------------------------------------------------------------- accessors

    def day_index(self, day: str) -> int:
        if day not in self._day_index:
            raise ValueError(f"Unknown day {day!r}. Known days: {self.days}")
        return self._day_index[day]

    def period_index(self, period: str) -> int:
        if period not in self._period_index:
            raise ValueError(
                f"Unknown period {period!r}. Known periods: "
                f"{[p.name for p in self.periods]}"
            )
        return self._period_index[period]

    def slot(self, day_i: int, period_i: int) -> int:
        return day_i * self.n_periods + period_i

    def day_of(self, slot: int) -> int:
        return slot // self.n_periods

    def period_of(self, slot: int) -> int:
        return slot % self.n_periods

    def describe(self, slot: int) -> str:
        d, p = self.day_of(slot), self.period_of(slot)
        return f"{self.days[d]} {self.periods[p].name}"

    # ---------------------------------------------------------- start domains

    def theory_start_slots(self) -> list[int]:
        """A 1-period class may start anywhere."""
        return list(range(self.n_slots))

    def lab_start_slots(self, length: int | None = None) -> list[int]:
        """Start slots where a `length`-period lab fits inside one block.

        With your grid (blocks of exactly 3 periods) and a 3-period lab, this
        returns exactly one start per block per day: P1, P4, P7.
        """
        length = self.lab_periods if length is None else length
        starts: list[int] = []
        for d in range(self.n_days):
            for block in self.blocks:
                for offset in range(len(block) - length + 1):
                    starts.append(self.slot(d, block[offset]))
        return starts

    def covered_slots(self, start: int, length: int) -> list[int]:
        return [start + k for k in range(length)]

    def block_of_period(self, period_i: int) -> list[int]:
        for block in self.blocks:
            if period_i in block:
                return block
        raise ValueError(f"Period index {period_i} is in no block.")

    def block_windows(self, size: int) -> Iterable[list[int]]:
        """Yield every run of `size` consecutive period indices inside a block.

        Used for the 'no more than N classes back to back' soft constraint.
        Teaching either side of a break is not back-to-back, so windows never
        straddle a block boundary.
        """
        for block in self.blocks:
            for offset in range(len(block) - size + 1):
                yield block[offset : offset + size]

    # ------------------------------------------------------------ constructors

    @classmethod
    def from_dict(cls, cfg: dict) -> "TimeGrid":
        periods = [Period(**p) for p in cfg["periods"]]
        breaks = [Break(**b) for b in cfg.get("breaks", [])]
        return cls(
            days=cfg["days"],
            periods=periods,
            breaks=breaks,
            lab_periods=cfg.get("lab_periods", 3),
        )

    def pretty(self) -> str:
        """Human-readable printout of the day, breaks included in order."""
        cut_after = {self.period_index(b.after_period): b for b in self.breaks}
        lines = []
        for i, p in enumerate(self.periods):
            lines.append(f"  {p.name:<4} {p.start}-{p.end}")
            if i in cut_after:
                b = cut_after[i]
                lines.append(f"       -- {b.name} {b.start}-{b.end} --")
        blocks = ", ".join(
            "[" + "-".join(self.periods[i].name for i in blk) + "]" for blk in self.blocks
        )
        lines.append(f"  contiguous blocks: {blocks}")
        return "\n".join(lines)

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
    start: str = ""
    end: str = ""
    length_minutes: int = 0


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
        if "periods" in cfg:
            periods = [Period(**p) for p in cfg["periods"]]
            breaks = [Break(**b) for b in cfg.get("breaks", [])]
            return cls(
                days=cfg["days"],
                periods=periods,
                breaks=breaks,
                lab_periods=cfg.get("lab_periods", 3),
            )
        return build_time_grid_from_config(cfg)

    @classmethod
    def from_config(cls, cfg: dict) -> "TimeGrid":
        return build_time_grid_from_config(cfg)

    def pretty(self) -> str:
        """Human-readable printout of the day, breaks included in order."""
        cut_after = {self.period_index(b.after_period): b for b in self.breaks}
        lines = []
        for i, p in enumerate(self.periods):
            lines.append(f"  {p.name:<4} {p.start}-{p.end}")
            if i in cut_after:
                b = cut_after[i]
                t_info = f" {b.start}-{b.end}" if b.start and b.end else (f" ({b.length_minutes}m)" if b.length_minutes else "")
                lines.append(f"       -- {b.name}{t_info} --")
        blocks = ", ".join(
            "[" + "-".join(self.periods[i].name for i in blk) + "]" for blk in self.blocks
        )
        lines.append(f"  contiguous blocks: {blocks}")
        return "\n".join(lines)


# -----------------------------------------------------------------------------
# Time Grid Configuration & Calculation Utilities
# -----------------------------------------------------------------------------

DEFAULT_TIME_GRID_CONFIG = {
    "day_start": "08:00",
    "period_duration_minutes": 50,
    "periods_per_day": 9,
    "lab_periods": 3,
    "days": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"],
    "breaks": [
        {"name": "Snack break", "after_period": "P3", "duration_minutes": 10},
        {"name": "Lunch & prayer", "after_period": "P6", "duration_minutes": 80},
    ],
}


def parse_time_minutes(t_str: str) -> int:
    """Parse 'HH:MM' string to minutes from midnight."""
    if not t_str or ":" not in t_str:
        return 480  # 08:00 AM default
    try:
        parts = t_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return 480


def format_minutes_time(minutes: int) -> str:
    """Format minutes from midnight to 'HH:MM' (24-hour)."""
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def format_minutes_time_12h(minutes: int) -> str:
    """Format minutes from midnight to 'hh:mm AM/PM'."""
    h = (minutes // 60) % 24
    m = minutes % 60
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return f"{h12:02d}:{m:02d} {ampm}"


def compute_time_grid_details(config: dict | None = None) -> dict:
    """Compute detailed timeline, periods, and blocks from a time grid configuration."""
    cfg = dict(DEFAULT_TIME_GRID_CONFIG)
    if config:
        for k, v in config.items():
            if v is not None:
                cfg[k] = v

    day_start = str(cfg.get("day_start", "08:00")).strip()
    cur_m = parse_time_minutes(day_start)
    duration = max(15, min(180, int(cfg.get("period_duration_minutes", 50))))
    periods_count = max(4, min(16, int(cfg.get("periods_per_day", 9))))
    lab_periods = max(1, min(periods_count, int(cfg.get("lab_periods", 3))))
    days = cfg.get("days") or ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
    raw_breaks = cfg.get("breaks", [])

    # Index breaks by uppercase after_period, e.g. "P3"
    break_map: dict[str, dict] = {}
    for b in raw_breaks:
        if isinstance(b, dict):
            ap = str(b.get("after_period", "")).strip().upper()
            if ap:
                break_map[ap] = b

    periods: list[dict] = []
    breaks: list[dict] = []
    for i in range(1, periods_count + 1):
        p_name = f"P{i}"
        p_start = format_minutes_time(cur_m)
        cur_m += duration
        p_end = format_minutes_time(cur_m)
        periods.append({
            "name": p_name,
            "start": p_start,
            "end": p_end,
            "label": f"{p_start}-{p_end}",
            "period_index": i - 1,
            "duration_minutes": duration,
        })

        # Check if a break is scheduled after this period (cannot be after the last period)
        if p_name in break_map and i < periods_count:
            b_info = break_map[p_name]
            b_name = b_info.get("name") or f"Break after {p_name}"
            b_dur = max(5, int(b_info.get("duration_minutes", b_info.get("length_minutes", 15))))
            b_start = p_end
            cur_m += b_dur
            b_end = format_minutes_time(cur_m)
            breaks.append({
                "name": b_name,
                "after_period": p_name,
                "start": b_start,
                "end": b_end,
                "duration_minutes": b_dur,
                "length_minutes": b_dur,
            })

    day_end = format_minutes_time(cur_m)
    total_active_mins = periods_count * duration
    total_break_mins = sum(b["duration_minutes"] for b in breaks)
    total_day_mins = cur_m - parse_time_minutes(day_start)

    # Compute contiguous blocks
    cut_after = {b["after_period"] for b in breaks}
    blocks: list[dict] = []
    cur_block_p: list[dict] = []
    for p in periods:
        cur_block_p.append(p)
        if p["name"] in cut_after or p["name"] == periods[-1]["name"]:
            blocks.append({
                "block_index": len(blocks) + 1,
                "period_names": [x["name"] for x in cur_block_p],
                "periods": cur_block_p,
                "start": cur_block_p[0]["start"],
                "end": cur_block_p[-1]["end"],
                "length_periods": len(cur_block_p),
                "can_fit_lab": len(cur_block_p) >= lab_periods,
            })
            cur_block_p = []

    return {
        "day_start": day_start,
        "day_end": day_end,
        "day_span_formatted": f"{format_minutes_time_12h(parse_time_minutes(day_start))} – {format_minutes_time_12h(cur_m)}",
        "total_active_minutes": total_active_mins,
        "total_break_minutes": total_break_mins,
        "total_day_minutes": total_day_mins,
        "periods": periods,
        "breaks": breaks,
        "blocks": blocks,
        "days": days,
        "lab_periods": lab_periods,
        "periods_per_day": periods_count,
        "period_duration_minutes": duration,
    }


def build_time_grid_from_config(config: dict | None = None) -> TimeGrid:
    """Build a TimeGrid instance from a configuration dictionary."""
    computed = compute_time_grid_details(config)
    periods = [Period(name=p["name"], start=p["start"], end=p["end"]) for p in computed["periods"]]
    breaks = [
        Break(
            name=b["name"],
            after_period=b["after_period"],
            start=b["start"],
            end=b["end"],
            length_minutes=b["duration_minutes"],
        )
        for b in computed["breaks"]
    ]
    return TimeGrid(
        days=computed["days"],
        periods=periods,
        breaks=breaks,
        lab_periods=computed["lab_periods"],
    )

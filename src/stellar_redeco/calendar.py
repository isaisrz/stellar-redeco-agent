"""CONDUSEF business days. REDECO deadlines are counted in business days,
excluding weekends and the non-working days CONDUSEF publishes each year
(2026: agreement signed 17-Dec-2025, published in the DOF)."""
from __future__ import annotations

import datetime as dt

NON_WORKING_2026 = {dt.date.fromisoformat(d) for d in (
    "2026-01-01", "2026-01-02", "2026-02-02", "2026-03-16", "2026-04-02", "2026-04-03",
    "2026-05-01", "2026-05-05",
    "2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24",
    "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31",
    "2026-09-16", "2026-11-02", "2026-11-16",
    "2026-12-17", "2026-12-18", "2026-12-21", "2026-12-22", "2026-12-23", "2026-12-24",
    "2026-12-25", "2026-12-28", "2026-12-29", "2026-12-30", "2026-12-31",
)}
REDECO_TERM_DAYS = 10  # business days to answer a REDECO complaint


def is_business_day(d: dt.date) -> bool:
    if d.year != 2026:
        raise ValueError(f"no CONDUSEF calendar loaded for {d.year}")  # fail closed
    return d.weekday() < 5 and d not in NON_WORKING_2026


def parse(s: str) -> dt.date:
    """Accepts dd/mm/yyyy (portal format) or ISO yyyy-mm-dd."""
    s = s.strip().replace(".", "/")
    if "-" in s:
        return dt.date.fromisoformat(s[:10])
    return dt.datetime.strptime(s[:10], "%d/%m/%Y").date()


def business_days_between(start: dt.date, end: dt.date) -> int:
    """Business days in [start, end) — start included, end excluded."""
    n, d = 0, start
    while d < end:
        n += is_business_day(d)
        d += dt.timedelta(days=1)
    return n


def portal_day(received: dt.date, deadline: dt.date, today: dt.date) -> tuple[int, int]:
    """The 'X de 10' counter the REDECO portal shows: business days already elapsed
    (receipt day included, today excluded) out of the business days up to the deadline."""
    total = business_days_between(received, deadline + dt.timedelta(days=1))
    return business_days_between(received, today), total

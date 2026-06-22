"""
Deterministic day-plan scheduler and adaptive reconciliation engine.

This module is intentionally **pure stdlib** — it imports no Streamlit,
no Google credentials, and no network clients — so the scheduling and
reconciliation logic can be unit-tested fully offline. All side-effecting
work (reading signals from Sheets, writing calendar events, persisting the
plan) is performed by the caller (website.py), which feeds data in and
applies the decisions this module returns.

Core responsibilities
----------------------
1. build_structured_plan() — turn a sorted list of pending signals into a
   timed schedule (the source of truth for the day).
2. reconcile_plan()        — given a previously-saved plan and the current
   set of signals, compute what should change when a new serious concern
   surfaces: add a freed slot, swap out a strictly-lower-priority student,
   or — when two Critical students compete for one slot — refuse to decide
   and surface the tradeoff to the coach.
3. apply_decision()        — apply the coach's choice for a surfaced tie.

Every automated change carries an explicit, human-readable reason.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Ranking + scheduling constants
# ---------------------------------------------------------------------------

SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

URGENCY_RANK = {
    "today": 0,
    "tomorrow": 1,
    "this week": 2,
}

# Signal type -> session type (mirrors the coach prompt mapping)
SESSION_TYPE_MAP = {
    "academic struggle": "Concept Review Session",
    "mental health": "Check-in Session",
    "mental health/stress": "Check-in Session",
    "stress": "Check-in Session",
    "attendance risk": "Re-engagement Session",
    "attendance": "Re-engagement Session",
    "performance drop": "Performance Review Session",
    "performance": "Performance Review Session",
    "behavioral issues": "Coaching Session",
    "behavioral": "Coaching Session",
}

DEFAULT_SESSION_TYPE = "Coaching Session"

MAX_SLOTS = 5
FIRST_SLOT = "09:00"
SESSION_MINUTES = 45
GAP_MINUTES = 15
SERIOUS_SEVERITIES = {"critical", "high"}

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PLAN_PATH = BASE_DIR / "state" / "day_plan.json"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _sev(signal: dict) -> str:
    return str(signal.get("severity", "")).strip().lower()


def _urg(signal: dict) -> str:
    return str(signal.get("urgency", "")).strip().lower()


def priority_tuple(signal: dict) -> tuple[int, int]:
    """Lower tuple == higher priority. Sort/compare with this."""
    return (
        SEVERITY_RANK.get(_sev(signal), 99),
        URGENCY_RANK.get(_urg(signal), 99),
    )


def is_serious(signal: dict) -> bool:
    return _sev(signal) in SERIOUS_SEVERITIES


def session_type_for(signal_type: str) -> str:
    return SESSION_TYPE_MAP.get(
        str(signal_type).strip().lower(),
        DEFAULT_SESSION_TYPE,
    )


def slot_time(index: int, first_slot: str = FIRST_SLOT) -> tuple[str, str]:
    """
    Return (start, end) "HH:MM" strings for the i-th slot (0-based).

    Sessions are SESSION_MINUTES long with GAP_MINUTES between them, so each
    slot begins (SESSION_MINUTES + GAP_MINUTES) minutes after the previous.
    """
    base = datetime.strptime(first_slot, "%H:%M")
    step = SESSION_MINUTES + GAP_MINUTES
    start = base + timedelta(minutes=index * step)
    end = start + timedelta(minutes=SESSION_MINUTES)

    return start.strftime("%H:%M"), end.strftime("%H:%M")


def _top_signal_per_student(signals: list[dict]) -> dict[str, dict]:
    """Collapse multiple signals per student to the single highest-priority one."""
    best: dict[str, dict] = {}

    for sig in signals:
        sid = str(sig.get("student_id", "")).strip()

        if not sid:
            continue

        if sid not in best or priority_tuple(sig) < priority_tuple(best[sid]):
            best[sid] = sig

    return best


def _make_session(signal: dict, index: int) -> dict:
    start, end = slot_time(index)

    return {
        "student_id": str(signal.get("student_id", "")).strip(),
        "session_type": session_type_for(signal.get("signal_type", "")),
        "signal_type": signal.get("signal_type", ""),
        "severity": signal.get("severity", ""),
        "urgency": signal.get("urgency", ""),
        "reason": signal.get("reason", ""),
        "start_time": start,
        "end_time": end,
        "slot_index": index,
        "calendar_event_id": None,
    }


def _make_deferred(signal: dict, defer_reason: str) -> dict:
    return {
        "student_id": str(signal.get("student_id", "")).strip(),
        "signal_type": signal.get("signal_type", ""),
        "severity": signal.get("severity", ""),
        "urgency": signal.get("urgency", ""),
        "reason": signal.get("reason", ""),
        "defer_reason": defer_reason,
        # Carried through so the UI can remove a calendar event when a
        # previously-scheduled student is bumped to tomorrow.
        "calendar_event_id": signal.get("calendar_event_id"),
    }



# ---------------------------------------------------------------------------
# Initial plan construction
# ---------------------------------------------------------------------------

def build_structured_plan(
    signals: list[dict],
    date: str | None = None,
    max_slots: int = MAX_SLOTS,
) -> dict:
    """
    Build a fresh structured day plan from pending signals.

    Rules:
    - One session per student (highest-priority signal wins).
    - Ranked by severity then urgency.
    - First `max_slots` are scheduled today; the rest are deferred with an
      explicit reason.
    """
    today = date or datetime.now().strftime("%Y-%m-%d")

    ranked = sorted(
        _top_signal_per_student(signals).values(),
        key=priority_tuple,
    )

    sessions: list[dict] = []
    deferred: list[dict] = []

    for sig in ranked:
        if len(sessions) < max_slots:
            sessions.append(_make_session(sig, len(sessions)))
        else:
            deferred.append(
                _make_deferred(
                    sig,
                    f"Beyond today's {max_slots}-session capacity; lower priority "
                    f"than the {max_slots} students already scheduled.",
                )
            )

    return {
        "date": today,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "max_slots": max_slots,
        "sessions": sessions,
        "deferred": deferred,
    }


# ---------------------------------------------------------------------------
# Adaptive reconciliation
# ---------------------------------------------------------------------------

def _lowest_priority_session(sessions: list[dict]) -> dict | None:
    """Return the scheduled session with the *worst* (highest) priority tuple."""
    if not sessions:
        return None

    return max(sessions, key=priority_tuple)


def reconcile_plan(
    saved_plan: dict,
    current_signals: list[dict],
) -> tuple[dict, list[dict], list[dict]]:
    """
    Reconcile a previously-saved plan against the current set of signals.

    Returns (new_plan, changelog, decisions) — a PURE computation with no
    persistence or calendar side effects.

    - changelog : list of {type, student_id, reason, ...} describing every
      automated change applied to the plan.
    - decisions : list of unresolved Critical-vs-Critical conflicts that the
      engine refuses to auto-resolve. The incoming student in a decision is
      left UNscheduled (parked) until the coach chooses via apply_decision().

    Auto-resolution policy for a new serious (Critical/High) student when the
    plan is full:

    - If strictly higher priority than the lowest scheduled student -> swap
      (defer the incumbent, schedule the newcomer), UNLESS both are Critical.
    - If both newcomer and the lowest incumbent are Critical -> surface a
      decision; do not modify the plan.
    - Otherwise -> defer the newcomer with a reason.
    """
    max_slots = saved_plan.get("max_slots", MAX_SLOTS)

    sessions = [dict(s) for s in saved_plan.get("sessions", [])]
    deferred = [dict(d) for d in saved_plan.get("deferred", [])]

    changelog: list[dict] = []
    decisions: list[dict] = []

    scheduled_ids = {s["student_id"] for s in sessions}
    current_top = _top_signal_per_student(current_signals)

    # Candidates: serious concerns for students not currently scheduled,
    # processed strictly in priority order so the most urgent claims slots first.
    candidates = sorted(
        (
            sig
            for sid, sig in current_top.items()
            if is_serious(sig) and sid not in scheduled_ids
        ),
        key=priority_tuple,
    )

    def _used_slot_indices() -> set[int]:
        return {s["slot_index"] for s in sessions}

    def _next_free_index() -> int:
        used = _used_slot_indices()
        i = 0

        while i in used:
            i += 1

        return i

    def _drop_from_deferred(sid: str) -> None:
        nonlocal deferred
        deferred = [d for d in deferred if d["student_id"] != sid]

    for sig in candidates:
        sid = sig["student_id"]

        # Free slot available -> simply add.
        if len(sessions) < max_slots:
            idx = _next_free_index()

            new_session = _make_session(sig, idx)

            sessions.append(new_session)
            scheduled_ids.add(sid)

            was_deferred = any(d["student_id"] == sid for d in deferred)

            _drop_from_deferred(sid)

            changelog.append(
                {
                    "type": "added",
                    "student_id": sid,
                    "slot": f'{new_session["start_time"]}–{new_session["end_time"]}',
                    "reason": (
                        f"New {sig.get('severity')} {sig.get('signal_type')} signal surfaced"
                        + (" (moved up from tomorrow); " if was_deferred else "; ")
                        + f"a free slot was available, so {sid} was scheduled today."
                    ),
                }
            )

            continue

        # Plan is full -> compare against the lowest-priority incumbent.
        incumbent = _lowest_priority_session(sessions)

        cand_pri = priority_tuple(sig)
        inc_pri = priority_tuple(incumbent)

        both_critical = (
            _sev(sig) == "critical"
            and _sev(incumbent) == "critical"
        )

        if both_critical:
            # Two Critical students, one slot: refuse to auto-decide and
            # surface the tradeoff to the coach.
            decisions.append(
                {
                    "incoming": {
                        "student_id": sid,
                        "severity": sig.get("severity"),
                        "signal_type": sig.get("signal_type"),
                        "urgency": sig.get("urgency"),
                        "reason": sig.get("reason"),
                    },
                    "incumbent": {
                        "student_id": incumbent["student_id"],
                        "severity": incumbent.get("severity"),
                        "signal_type": incumbent.get("signal_type"),
                        "urgency": incumbent.get("urgency"),
                        "reason": incumbent.get("reason"),
                        "slot": (
                            f'{incumbent["start_time"]}–'
                            f'{incumbent["end_time"]}'
                        ),
                    },
                    "tradeoff": (
                        f'Both {sid} (incoming) and {incumbent["student_id"]} '
                        f'(scheduled {incumbent["start_time"]}–'
                        f'{incumbent["end_time"]}) '
                        f"are Critical, and today's {max_slots} slots are full. "
                        f"Only one can be seen today. Keeping "
                        f"{incumbent['student_id']} "
                        f"means {sid} waits until tomorrow; swapping means "
                        f"{incumbent['student_id']} is deferred instead. "
                        f"You decide."
                    ),
                    "options": [
                        {
                            "action": "keep_incumbent",
                            "label": (
                                f'Keep {incumbent["student_id"]} today, '
                                f"defer {sid} to tomorrow"
                            ),
                        },
                        {
                            "action": "swap",
                            "label": (
                                f"Schedule {sid} today, defer "
                                f'{incumbent["student_id"]} to tomorrow'
                            ),
                        },
                    ],
                }
            )

            # Leave the newcomer parked (unscheduled, not deferred).
            continue

        if cand_pri < inc_pri:
            # Strictly higher priority and not a Critical tie -> auto-swap.
            sessions.remove(incumbent)

            freed_idx = incumbent["slot_index"]

            deferred.append(
                _make_deferred(
                    incumbent,
                    f"Bumped to tomorrow: {sid} surfaced a higher-priority "
                    f"{sig.get('severity')} {sig.get('signal_type')} concern and "
                    f"today's {max_slots} slots were full.",
                )
            )

            new_session = _make_session(sig, freed_idx)

            sessions.append(new_session)

            scheduled_ids.add(sid)
            scheduled_ids.discard(incumbent["student_id"])

            _drop_from_deferred(sid)

            changelog.append(
                {
                    "type": "swapped",
                    "student_id": sid,
                    "replaced": incumbent["student_id"],
                    "slot": f'{new_session["start_time"]}–{new_session["end_time"]}',
                    "reason": (
                        f"{sid} ({sig.get('severity')} "
                        f"{sig.get('signal_type')}) took the "
                        f'{new_session["start_time"]} slot from '
                        f'{incumbent["student_id"]} '
                        f"({incumbent.get('severity')}), who was the "
                        f"lowest-priority student scheduled and is now "
                        f"deferred to tomorrow."
                    ),
                }
            )

        else:
            # Not higher priority than any scheduled student -> defer newcomer.
            deferred.append(
                _make_deferred(
                    sig,
                    f"Today's {max_slots} slots are full with equal-or-higher "
                    f"priority students; {sid} is deferred to tomorrow.",
                )
            )

            changelog.append(
                {
                    "type": "deferred",
                    "student_id": sid,
                    "reason": (
                        f"New {sig.get('severity')} "
                        f"{sig.get('signal_type')} signal for {sid}, "
                        f"but all {max_slots} slots hold equal-or-higher "
                        f"priority students. Deferred to tomorrow."
                    ),
                }
            )

    new_plan = {
        "date": saved_plan.get(
            "date",
            datetime.now().strftime("%Y-%m-%d"),
        ),
        "generated_at": saved_plan.get("generated_at"),
        "reconciled_at": datetime.now().isoformat(timespec="seconds"),
        "max_slots": max_slots,
        "sessions": sorted(
            sessions,
            key=lambda s: s["slot_index"],
        ),
        "deferred": deferred,
    }

    return new_plan, changelog, decisions


def apply_decision(
    plan: dict,
    decision: dict,
    choice: str,
) -> tuple[dict, dict]:
    """
    Apply a coach's resolution of a surfaced Critical-vs-Critical tie.

    choice:
    - "swap" -> schedule the incoming student, defer the incumbent.
    - "keep_incumbent" -> keep the incumbent, defer the incoming student.

    Returns (new_plan, changelog_entry).
    """
    sessions = [dict(s) for s in plan.get("sessions", [])]
    deferred = [dict(d) for d in plan.get("deferred", [])]

    incoming = decision["incoming"]
    incumbent = decision["incumbent"]

    in_sid = incoming["student_id"]
    inc_sid = incumbent["student_id"]

    if choice == "swap":
        target = next(
            (s for s in sessions if s["student_id"] == inc_sid),
            None,
        )

        if target is not None:
            sessions.remove(target)

            deferred.append(
                _make_deferred(
                    {
                        **incumbent,
                        "student_id": inc_sid,
                    },
                    f"Coach chose to prioritise {in_sid} (both Critical); "
                    f"{inc_sid} deferred to tomorrow.",
                )
            )

            idx = target["slot_index"]
        else:
            idx = len(sessions)

        new_session = _make_session(
            {
                **incoming,
                "student_id": in_sid,
            },
            idx,
        )

        sessions.append(new_session)

        deferred = [
            d
            for d in deferred
            if d["student_id"] != in_sid
        ]

        entry = {
            "type": "coach_decision",
            "student_id": in_sid,
            "replaced": inc_sid,
            "reason": (
                f"Coach resolved Critical tie: scheduled {in_sid} today "
                f"and deferred {inc_sid} to tomorrow."
            ),
        }

    elif choice == "keep_incumbent":
        deferred.append(
            _make_deferred(
                {
                    **incoming,
                    "student_id": in_sid,
                },
                f"Coach chose to keep {inc_sid} today (both Critical); "
                f"{in_sid} deferred to tomorrow.",
            )
        )

        entry = {
            "type": "coach_decision",
            "student_id": inc_sid,
            "deferred": in_sid,
            "reason": (
                f"Coach resolved Critical tie: kept {inc_sid} today "
                f"and deferred {in_sid} to tomorrow."
            ),
        }

    else:
        raise ValueError(f"Unknown decision choice: {choice!r}")

    new_plan = {
        **plan,
        "reconciled_at": datetime.now().isoformat(timespec="seconds"),
        "sessions": sorted(
            sessions,
            key=lambda s: s["slot_index"],
        ),
        "deferred": deferred,
    }

    return new_plan, entry


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_plan(path: str | os.PathLike | None = None) -> dict | None:
    """Load the persisted structured plan, or None if none exists."""
    p = Path(path) if path else DEFAULT_PLAN_PATH

    if not p.exists():
        return None

    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_plan(plan: dict, path: str | os.PathLike | None = None) -> None:
    """Persist the structured plan as JSON, creating the directory if needed."""
    p = Path(path) if path else DEFAULT_PLAN_PATH

    p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_plan_markdown(plan: dict) -> str:
    """Render a structured plan to the coach-facing markdown layout."""
    sessions = sorted(
        plan.get("sessions", []),
        key=lambda s: s["slot_index"],
    )
    deferred = plan.get("deferred", [])

    lines = [
        f"**📅 Day Plan — {plan.get('date', '')}**",
        f"**{len(sessions)} sessions scheduled · {len(deferred)} deferred**",
        "",
        "─── TODAY'S SESSIONS ───",
    ]

    if sessions:
        for s in sessions:
            lines += [
                f"🕘 {s['start_time']}–{s['end_time']} | "
                f"{s['student_id']} | {s['session_type']}",
                f"  Severity: {s.get('severity', 'N/A')}  |  "
                f"Signal: {s.get('signal_type', 'N/A')}",
                f"  Why: {s.get('reason', '')}",
                "",
            ]
    else:
        lines.append("_No sessions scheduled today._")
        lines.append("")

    lines.append("─── DEFERRED TO TOMORROW ───")

    if deferred:
        for d in deferred:
            lines.append(
                f"• {d['student_id']} — "
                f"{d.get('defer_reason', d.get('reason', ''))}"
            )
    else:
        lines.append("_None._")

    return "\n".join(lines)


def changelog_to_markdown(
    changelog: list[dict],
    decisions: list[dict],
) -> str:
    """Render the 'what changed since you last looked' summary for the coach."""
    if not changelog and not decisions:
        return ""

    lines = ["#### 🔔 What changed in your plan"]

    icon = {
        "added": "➕",
        "swapped": "🔁",
        "deferred": "⏭️",
        "coach_decision": "✅",
    }

    for c in changelog:
        lines.append(
            f"- {icon.get(c['type'], '•')} "
            f"**{c['student_id']}** — {c['reason']}"
        )

    if decisions:
        lines.append("")
        lines.append("#### ⚖️ Needs your call")

        for d in decisions:
            lines.append(f"- {d['tradeoff']}")

    return "\n".join(lines)




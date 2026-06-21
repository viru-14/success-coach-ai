import logging
import streamlit as st

from services.tools import run_agent, run_coach_agent
from services.memory import save_memory, get_all_factual_memories
from services.brief import generate_student_brief
from services.googlesheets import get_pending_signals_structured
from services.calendar import create_calendar_event, delete_calendar_event
from services import dp


# Suppress the noisy mem0 "Regional Access Boundary" warning — it is
# a retryable internal warning from mem0's transport layer and does not
# affect any functionality.
logging.getLogger("mem0").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)

# Constants
# ---------------------------------------------------------------------------

STUDENTS_ID = ["STU001", "STU002", "STU003"]
COACH_ID = "COACH001"

STUDENT_SYSTEM_PROMPT = """
You are an AI Coach assistant strictly limited to this online learning platform.

## HARD RULES — never break these

1. You ONLY answer questions that are directly about:
   - The course content available in THIS platform (verified via get_setup_data)
   - The student's own academic data in THIS platform (verified via get_student_specific_data)

2. You NEVER answer anything else — no exceptions. This includes but is not limited to:
   - Stories, jokes, poems, creative writing of any kind
   - General knowledge, trivia, or fun facts
   - Academic topics from subjects NOT found in this platform's course data
   - Advice, opinions, or personal guidance unrelated to the course
   - Anything a general-purpose chatbot would answer

3. Before answering any academic question, call get_setup_data to confirm the topic actually exists in this platform's course.
   If it does not appear in the retrieved data, refuse — even if the topic sounds academic.

5. You can answer casual question like:
   - Hii, how are you, etc

4. If you are unsure whether something is in scope, refuse.

## When a request is out of scope

Respond with exactly this and nothing more:

"I can only help you with the course content and your learning progress on
this platform. Let's get back to your studies!"

Do NOT apologise at length, do NOT engage with the off-topic request at all,
do NOT offer alternatives outside the platform.

## Tools — call these before answering, not after

1. get_student_specific_data(student_id)

   Call when the student asks about their own progress, performance,
   or attendance, or when you need to personalise a response to their level.

2. get_setup_data(query)

   Call to verify a topic exists in this platform's course and to retrieve
   relevant content. If the topic is not found in the results, refuse.

3. get_memories(student_id, query)

   Retrieves FACTUAL memory from past sessions:
   known stress triggers, what explanations have worked,
   recurring misunderstandings, and personal learning patterns.

   Call this at the start of each conversation, or when the student references
   something from a previous session.

   Use it to adapt your tone and approach — not to summarise past sessions
   aloud (session summaries are a separate system for coaches).

You may call multiple tools in the same turn.
Always prefer fetching over assuming.

## When a question IS in scope

- Give simple, clear, student-friendly explanations.
- Use step-by-step reasoning when needed.
- Adjust complexity based on the student's grade level
  (fetch their data first).
- Encourage understanding, not memorisation.
- Be supportive but factual — no false praise.
- If the student is repeatedly stuck, suggest a live session:

"This might be easier to cover with your coach directly.
Should I help schedule a session?"
"""

COACH_DAY_PLAN_PROMPT = """
You are an expert academic coaching assistant for Success Coach AI.

Your job is to generate a structured, actionable day plan for the coach
based entirely on student signals — not assumptions.

## Workflow — follow these steps in order

### Step 1 — Pull the data

1. Call get_pending_signals to see every student who needs attention.

   If there are no pending signals, tell the coach all students are on track
   and stop — no further steps needed.

2. For EACH flagged student call BOTH:

   - get_student_specific_data(student_id)
   - get_session_summaries(student_id)

### Step 2 — Prioritise

Rank students strictly by:

Severity → Critical > High > Medium > Low

Urgency → Today > Tomorrow > This Week

Students flagged "Today" must always be scheduled today.

### Step 3 — Build the schedule

- Sessions start at 09:00.
- Each session is 45 minutes; leave a 15-minute gap between sessions.
- Maximum 5 students today (last slot ends ~14:00).
- Students beyond the 5-slot limit are deferred to tomorrow.

Assign a session type from this mapping:

Academic Struggle → "Concept Review Session"

Mental Health/Stress → "Check-in Session"

Attendance Risk → "Re-engagement Session"

Performance Drop → "Performance Review Session"

Behavioral Issues → "Coaching Session"

### Step 4 — Create calendar events

For every student scheduled TODAY, call create_calendar_event:

title :
"[Student ID] – [Session Type]"

start_time :
"HH:MM" (24-hour)

end_time :
"HH:MM" (24-hour)

description :
Signal reason + 1-2 key talking points from their history

Do NOT call create_calendar_event for deferred students.

### Step 5 — Return the plan

Format the final response as:

** Day Plan — [Today's date] **

** [N] sessions scheduled · [M] deferred **

─── TODAY'S SESSIONS ───

For each student:

HH:MM – HH:MM | [Student ID] | [Session Type]

Severity: X | Signal: [signal type]

Why today:
[one sentence from the signal reason]

Focus:
[1-2 bullet talking points drawn from their data and history]

─── DEFERRED TO TOMORROW ───

For each deferred student:

• [Student ID] — [brief reason they were bumped]

─── COACH SUMMARY ───

2-3 sentences on the overall theme of today's caseload and the top priority.
"""

# ---------------------------------------------------------------------------
# Page config & custom CSS
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Success Coach AI",
    page_icon=" ",
    layout="centered",
)

st.markdown(
    """
<style>

/* ── View toggle pill ─────────────────────────────────────────── */

div[data-testid="stHorizontalBlock"]:has(.view-toggle) {
    gap: 0;
}

.stButton > button {
    border-radius: 0;
    border: 1px solid #d1d5db;
    background: #f9fafb;
    color: #374151;
    font-weight: 500;
    transition: all 0.15s ease;
}

.stButton > button:hover {
    background: #f3f4f6;
    border-color: #9ca3af;
}

/* Active tab feeling via session state class injection isn't trivial in
   Streamlit, so we rely on button labels + use_container_width for symmetry */

/* ── Section header badges ───────────────────────────────────── */

.badge-student {
    display: inline-block;
    background: #dbeafe;
    color: #1e40af;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 999px;
    margin-bottom: 0.5rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.badge-coach {
    display: inline-block;
    background: #fef3c7;
    color: #92400e;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 999px;
    margin-bottom: 0.5rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "view" not in st.session_state:
    st.session_state.view = "student"  # "student" | "coach"

if "messages" not in st.session_state:
    st.session_state.messages = []

if "selected_student_id" not in st.session_state:
    st.session_state.selected_student_id = None

if "student_memories" not in st.session_state:
    st.session_state.student_memories = ""

if "day_plan" not in st.session_state:
    st.session_state.day_plan = ""

if "student_brief" not in st.session_state:
    st.session_state.student_brief = ""

if "plan_changelog" not in st.session_state:
    st.session_state.plan_changelog = []

if "plan_decisions" not in st.session_state:
    st.session_state.plan_decisions = []

if "coach_reconciled" not in st.session_state:
    st.session_state.coach_reconciled = False


# ---------------------------------------------------------------------------
# Coach helpers — calendar sync + adaptive reconciliation
# ---------------------------------------------------------------------------

def _sync_calendar(plan: dict) -> bool:
    """
    Best-effort calendar sync for a structured plan.

    Creates events for scheduled sessions that don't yet have one,
    and deletes events for students who were moved to tomorrow.

    Returns True if the plan dict was mutated (so the caller can
    re-persist).

    All calendar errors are swallowed — the plan remains the source
    of truth even if calendar I/O fails.
    """
    changed = False

    for s in plan.get("sessions", []):
        if not s.get("calendar_event_id"):
            try:
                res = create_calendar_event(
                    title=f"{s['student_id']} – {s['session_type']}",
                    start_time=s["start_time"],
                    end_time=s["end_time"],
                    description=(
                        f"{s.get('signal_type', '')}: "
                        f"{s.get('reason', '')}"
                    ),
                    date=plan.get("date"),
                    return_details=True,
                )

                if isinstance(res, dict) and res.get("event_id"):
                    s["calendar_event_id"] = res["event_id"]
                    changed = True

            except Exception:
                pass

    for d in plan.get("deferred", []):
        eid = d.get("calendar_event_id")

        if eid:
            try:
                if delete_calendar_event(eid):
                    d["calendar_event_id"] = None
                    changed = True
            except Exception:
                pass

    return changed


def _reconcile_on_load():
    """
    Run automatically the moment the coach opens Coach View:

    pull the latest signals, reconcile them against the saved plan,
    persist any automated changes, and stash the changelog + pending
    decisions for display — so the coach sees what changed and why
    before doing anything.
    """
    saved = dp.load_plan()

    if not saved:
        st.session_state.plan_changelog = []
        st.session_state.plan_decisions = []
        return

    try:
        signals = get_pending_signals_structured()
    except Exception:
        signals = []

    new_plan, changelog, decisions = dp.reconcile_plan(
        saved,
        signals,
    )

    if changelog:
        _sync_calendar(new_plan)
        dp.save_plan(new_plan)

        st.session_state.day_plan = (
            dp.render_plan_markdown(new_plan)
        )

    elif not st.session_state.day_plan:
        st.session_state.day_plan = (
            dp.render_plan_markdown(saved)
        )

    st.session_state.plan_changelog = changelog
    st.session_state.plan_decisions = decisions


# ---------------------------------------------------------------------------
# ── View Toggle (top of page, always visible) ─────────────────────────────
# ---------------------------------------------------------------------------

st.markdown("### Success Coach AI")
st.markdown("---")

col_sv, col_cv = st.columns(2)

with col_sv:
    student_label = (
        " Student View"
        if st.session_state.view != "student"
        else " Student View (active)"
    )

    if st.button(
        student_label,
        use_container_width=True,
        key="btn_student_view",
    ):
        st.session_state.view = "student"
        st.rerun()

with col_cv:
    coach_label = (
        " Coach View"
        if st.session_state.view != "coach"
        else " Coach View (active)"
    )

    if st.button(
        coach_label,
        use_container_width=True,
        key="btn_coach_view",
    ):
        st.session_state.view = "coach"
        st.session_state.coach_reconciled = False  # force a fresh reconcile on entry
        st.rerun()

st.markdown("")  # breathing room


# ===========================================================================
# ██████████████████████████ STUDENT VIEW ██████████████████████████████████
# ===========================================================================

if st.session_state.view == "student":

    st.markdown(
        '<span class="badge-student">Student View</span>',
        unsafe_allow_html=True,
    )
    st.subheader("Student Chat")

    # ── Student selector ────────────────────────────────────────────────────
    selected_student_id = st.selectbox(
        "Select Student ID",
        STUDENTS_ID,
        index=None,
        placeholder="Choose a student",
        key="student_selector",
    )

    if selected_student_id != st.session_state.selected_student_id:
        st.session_state.selected_student_id = selected_student_id
        st.session_state.messages = []

        if selected_student_id:
            st.session_state.student_memories = get_all_factual_memories(
                selected_student_id
            )
        else:
            st.session_state.student_memories = ""

    # ── Action buttons ──────────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            " Refresh",
            use_container_width=True,
            key="student_refresh",
        ):
            st.session_state.messages = []
            st.rerun()

    with col2:
        if st.button(
            " End Chat & Save Memory",
            use_container_width=True,
            key="student_save",
        ):
            if (
                st.session_state.messages
                and st.session_state.selected_student_id
            ):
                with st.spinner("Saving memory..."):
                    save_memory(
                        st.session_state.selected_student_id,
                        st.session_state.messages,
                    )

                st.success("Session saved!")
                st.session_state.messages = []
                st.rerun()

    # ── Render conversation ─────────────────────────────────────────────────
    for message in st.session_state.messages:
        role = (
            message.get("role")
            if isinstance(message, dict)
            else message.role
        )

        content = (
            message.get("content")
            if isinstance(message, dict)
            else message.content
        )

        if role in ("user", "assistant") and content:
            st.chat_message(role).write(content)

    # ── Chat input ──────────────────────────────────────────────────────────
    user_input = st.chat_input("What do you want to ask?...")

    if user_input and st.session_state.selected_student_id:

        st.chat_message("user").write(user_input)

        memory_block = (
            f"\n\n## What you already know about this student (from past sessions)\n"
            f"{st.session_state.student_memories}"
            if st.session_state.student_memories
            else ""
        )

        agent_messages = [
            {
                "role": "system",
                "content": (
                    f"{STUDENT_SYSTEM_PROMPT}"
                    f"{memory_block}\n\n"
                    f"Student ID: {st.session_state.selected_student_id}\n"
                ),
            },
            *st.session_state.messages,
            {"role": "user", "content": user_input},
        ]

        with st.spinner("Thinking..."):
            final_response, updated_messages = run_agent(agent_messages)

        new_turns = updated_messages[
            1 + len(st.session_state.messages):
        ]

        st.session_state.messages.extend(new_turns)

        st.chat_message("assistant").write(final_response)


# ===========================================================================
# ██████████████████████████ COACH VIEW ████████████████████████████████████
# ===========================================================================

elif st.session_state.view == "coach":

    st.markdown(
        '<span class="badge-coach">Coach View</span>',
        unsafe_allow_html=True,
    )
    st.subheader("Coach Dashboard")

    # ── Auto-reconcile the saved plan the moment the coach lands here ────────
    if not st.session_state.coach_reconciled:
        with st.spinner("Checking for new signals since your last plan..."):
            _reconcile_on_load()

        st.session_state.coach_reconciled = True

    # ── "What changed" summary — shown before the coach does anything ───────
    if (
        st.session_state.plan_changelog
        or st.session_state.plan_decisions
    ):
        with st.container(border=True):
            st.markdown(
                dp.changelog_to_markdown(
                    st.session_state.plan_changelog,
                    st.session_state.plan_decisions,
                )
            )

    # ── Critical-vs-Critical ties — coach makes the call ────────────────────
    if st.session_state.plan_decisions:

        st.markdown("#### Decisions needed")

        for d_idx, decision in enumerate(
            st.session_state.plan_decisions
        ):

            with st.container(border=True):

                inc = decision["incoming"]
                cur = decision["incumbent"]

                st.markdown(
                    f"**{inc['student_id']}** "
                    f"(incoming · {inc['severity']} "
                    f"{inc['signal_type']}) vs "
                    f"**{cur['student_id']}** "
                    f"(scheduled {cur['slot']} · "
                    f"{cur['severity']} {cur['signal_type']})"
                )

                st.markdown(f"> {decision['tradeoff']}")

                bcol1, bcol2 = st.columns(2)

                with bcol1:
                    if st.button(
                        decision["options"][0]["label"],
                        key=f"dec_keep_{d_idx}",
                        use_container_width=True,
                    ):
                        saved = dp.load_plan()

                        if saved:
                            new_plan, entry = dp.apply_decision(
                                saved,
                                decision,
                                "keep_incumbent",
                            )

                            _sync_calendar(new_plan)
                            dp.save_plan(new_plan)

                            st.session_state.day_plan = (
                                dp.render_plan_markdown(new_plan)
                            )
                            st.session_state.plan_changelog = [entry]

                            st.session_state.plan_decisions.pop(d_idx)
                            st.rerun()

                with bcol2:
                    if st.button(
                        decision["options"][1]["label"],
                        key=f"dec_swap_{d_idx}",
                        use_container_width=True,
                    ):
                        saved = dp.load_plan()

                        if saved:
                            new_plan, entry = dp.apply_decision(
                                saved,
                                decision,
                                "swap",
                            )

                            _sync_calendar(new_plan)
                            dp.save_plan(new_plan)

                            st.session_state.day_plan = (
                                dp.render_plan_markdown(new_plan)
                            )
                            st.session_state.plan_changelog = [entry]

                            st.session_state.plan_decisions.pop(d_idx)
                            st.rerun()

    st.markdown("---")

    # ── Student Brief (on demand) ────────────────────────────────────────────
    st.markdown("#### Student Brief")

    bc1, bc2 = st.columns([3, 2])

    with bc1:
        brief_student = st.selectbox(
            "Brief a student",
            STUDENTS_ID,
            index=None,
            placeholder="Choose a student",
            key="brief_selector",
            label_visibility="collapsed",
        )

    with bc2:
        gen_brief = st.button(
            " Generate Brief",
            use_container_width=True,
            key="gen_brief",
            disabled=brief_student is None,
        )

    if gen_brief and brief_student:
        with st.spinner(
            f"Preparing brief for {brief_student}..."
        ):
            st.session_state.student_brief = (
                generate_student_brief(brief_student)
            )

    if st.session_state.student_brief:
        with st.container(border=True):
            st.markdown(st.session_state.student_brief)

    st.markdown("---")

    # ── Generate Day Plan (deterministic build + persist) ────────────────────
    if st.button(
        " Generate Day Plan",
        use_container_width=True,
        key="gen_day_plan",
    ):
        with st.spinner("Building your day plan..."):

            try:
                signals = get_pending_signals_structured()
            except Exception as e:
                signals = []
                st.error(
                    f"Could not fetch pending signals: {e}"
                )

            plan = dp.build_structured_plan(signals)

            _sync_calendar(plan)
            dp.save_plan(plan)

            st.session_state.day_plan = (
                dp.render_plan_markdown(plan)
            )

            # A freshly generated plan is the new baseline —
            # clear stale deltas.
            st.session_state.plan_changelog = []
            st.session_state.plan_decisions = []

    # ── Render plan ─────────────────────────────────────────────────────────
    if st.session_state.day_plan:

        st.markdown("#### Today's Day Plan")

        with st.container(border=True):
            st.markdown(st.session_state.day_plan)
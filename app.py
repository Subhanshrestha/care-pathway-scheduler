import streamlit as st
import numpy as np
import pandas as pd

# Config
SLOT_MINUTES = 15
DAY_START_HOUR = 8
DAY_END_HOUR = 17
NUM_SLOTS = (DAY_END_HOUR - DAY_START_HOUR) * 60 // SLOT_MINUTES  # 36 fifteen-min slots

# Column order matches the Excel reference sheet
RESOURCES = ["Doctor", "NMT", "Patient", "Scan"]
PATHWAY_RESOURCE_CHOICES = ["Doctor", "NMT", "Scan", "GAP"]

DEFAULT_PATHWAY = [
    {"resource": "Doctor", "duration": 45},
    {"resource": "NMT",    "duration": 30},
    {"resource": "GAP",    "duration": 30},
    {"resource": "GAP",    "duration": 30},
    {"resource": "Scan",   "duration": 30},
    {"resource": "Scan",   "duration": 30},
    {"resource": "Doctor", "duration": 30},
]

# Cell states used for both logic and color mapping
FREE = 0
BLOCKED = 1
PATIENT = 2

# Visual distinction: blocked = dark, patient = lighter (per spec)
COLOR_MAP = {
    FREE:    ("background-color: #ffffff; color: black;",  "#ffffff"),
    BLOCKED: ("background-color: #555555; color: white;",  "#555555"),
    PATIENT: ("background-color: #a8d4f0; color: black;",  "#a8d4f0"),
}

# Page setup
st.set_page_config(page_title="Care Pathway Scheduler", layout="wide")
st.markdown("""
    <style>
        .block-container { padding-top: 1rem; }
        section[data-testid="stSidebar"] > div { padding-top: 0rem; }
        section[data-testid="stSidebar"] .stMarkdown p { margin-bottom: 0.25rem; }
    </style>
""", unsafe_allow_html=True)


# Utility functions
def slot_to_time(slot_index):
    """Slot index (0-35) to 'HH:MM' string."""
    total_min = DAY_START_HOUR * 60 + slot_index * SLOT_MINUTES
    return f"{total_min // 60:02d}:{total_min % 60:02d}"

def time_to_slot(label):
    """'HH:MM' string to slot index."""
    h, m = map(int, label.split(":"))
    return (h * 60 + m - DAY_START_HOUR * 60) // SLOT_MINUTES

def col_index(resource_name):
    """Resource name to column index in the calendar matrix."""
    return RESOURCES.index(resource_name)

ALL_TIMES = [slot_to_time(i) for i in range(NUM_SLOTS)]


def build_display_df(calendar):
    """Wrap the numpy calendar in a labeled DataFrame for rendering.
    Appends a 17:00 row (all zeros) to match the Excel layout."""
    labels = ALL_TIMES + ["17:00"]
    padded = np.vstack([calendar, np.zeros((1, len(RESOURCES)), dtype=int)])
    return pd.DataFrame(padded, index=labels, columns=RESOURCES)


def style_cell(value):
    """Map cell value (0/1/2) to CSS style string."""
    return COLOR_MAP.get(value, COLOR_MAP[FREE])[0]


def sanitize_pathway(edited_df):
    """Validate and clean user edits from the pathway editor.
    Drops invalid rows, rounds durations up to nearest slot boundary."""
    result = []
    for _, row in edited_df.iterrows():
        res = row.get("resource")
        dur = row.get("duration")
        if res not in PATHWAY_RESOURCE_CHOICES:
            continue
        try:
            dur = int(dur)
        except (TypeError, ValueError):
            continue
        if dur <= 0:
            continue
        if dur % SLOT_MINUTES != 0:
            dur = ((dur // SLOT_MINUTES) + 1) * SLOT_MINUTES
        result.append({"resource": res, "duration": dur})
    return result


def detect_blocks(calendar):
    """Scan calendar for contiguous BLOCKED ranges per resource.
    Returns list of (resource_name, start_slot, end_slot) tuples."""
    blocks = []
    for ci, res in enumerate(RESOURCES):
        in_block = False
        bstart = 0
        for row in range(NUM_SLOTS):
            if calendar[row, ci] == BLOCKED and not in_block:
                in_block = True
                bstart = row
            elif calendar[row, ci] != BLOCKED and in_block:
                in_block = False
                blocks.append((res, bstart, row))
        if in_block:
            blocks.append((res, bstart, NUM_SLOTS))
    return blocks


# Scheduler
def find_earliest_slot(calendar, pathway):
    """Earliest-fit scheduling: slide a window across time slots, checking
    that every pathway step's resource column and the Patient lane are free.

    Returns dict with start_slot, end_slot, placements list, or None."""
    if not pathway:
        return None

    slots_per_step = [s["duration"] // SLOT_MINUTES for s in pathway]
    total_slots = sum(slots_per_step)

    if total_slots > NUM_SLOTS:
        return None

    pat_col = col_index("Patient")

    for start in range(NUM_SLOTS - total_slots + 1):
        placements = []
        offset = 0
        valid = True

        for step, n_slots in zip(pathway, slots_per_step):
            lo = start + offset
            hi = lo + n_slots

            # Non-GAP steps need their resource column completely free
            if step["resource"] != "GAP":
                rc = col_index(step["resource"])
                if not np.all(calendar[lo:hi, rc] == FREE):
                    valid = False
                    break
                placements.append((step["resource"], lo, hi))

            # Patient lane must be free for every step including GAPs
            if not np.all(calendar[lo:hi, pat_col] == FREE):
                valid = False
                break

            offset += n_slots

        if valid:
            return {"start_slot": start, "end_slot": start + total_slots,
                    "placements": placements}

    return None


def apply_schedule(calendar, result):
    """Paint the scheduler's result onto the calendar matrix."""
    s, e = result["start_slot"], result["end_slot"]
    calendar[s:e, col_index("Patient")] = PATIENT
    for res, lo, hi in result["placements"]:
        calendar[lo:hi, col_index(res)] = PATIENT


# Session state init
if "pathway" not in st.session_state:
    st.session_state.pathway = DEFAULT_PATHWAY.copy()
if "calendar" not in st.session_state:
    st.session_state.calendar = np.zeros((NUM_SLOTS, len(RESOURCES)), dtype=int)
if "schedule_result" not in st.session_state:
    st.session_state.schedule_result = None


# Sidebar: pathway editor
st.sidebar.title("Care Pathway")
st.sidebar.caption("Edit, add, or remove steps. Duration in minutes, rounded to 15-min slots.")

pathway_df = pd.DataFrame(st.session_state.pathway)
edited_pathway = st.sidebar.data_editor(
    pathway_df,
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "resource": st.column_config.SelectboxColumn(
            "Resource", options=PATHWAY_RESOURCE_CHOICES, required=True,
        ),
        "duration": st.column_config.NumberColumn(
            "Duration (min)", min_value=SLOT_MINUTES, step=SLOT_MINUTES, required=True,
        ),
    },
    key="pathway_editor",
)
st.session_state.pathway = sanitize_pathway(edited_pathway)

total_min = sum(s["duration"] for s in st.session_state.pathway)
st.sidebar.write(f"**Total duration:** {total_min} min ({total_min // 60}h {total_min % 60}m)")


# Sidebar: block editor
st.sidebar.divider()
st.sidebar.subheader("Add / Remove Blocks")

block_resource = st.sidebar.selectbox("Resource", RESOURCES, key="block_resource")
block_start = st.sidebar.selectbox("Start time", ALL_TIMES, key="block_start")

start_idx = time_to_slot(block_start)
end_choices = ALL_TIMES[start_idx + 1:] + ["17:00"]
block_end = st.sidebar.selectbox("End time", end_choices, key="block_end")

if st.sidebar.button("Add block", use_container_width=True):
    s = time_to_slot(block_start)
    e = NUM_SLOTS if block_end == "17:00" else time_to_slot(block_end)
    st.session_state.calendar[s:e, col_index(block_resource)] = BLOCKED
    st.rerun()

current_blocks = detect_blocks(st.session_state.calendar)

if current_blocks:
    st.sidebar.caption("**Current blocks:**")
    for i, (res, s, e) in enumerate(current_blocks):
        label = f"✕  {res}: {slot_to_time(s)} – {slot_to_time(e)}"
        if st.sidebar.button(label, key=f"rm_{i}", use_container_width=True):
            ci = col_index(res)
            for row in range(s, e):
                if st.session_state.calendar[row, ci] == BLOCKED:
                    st.session_state.calendar[row, ci] = FREE
            st.rerun()
else:
    st.sidebar.caption("No blocks set.")


# Main panel
st.title("Care Pathway Scheduler")

pathway_summary = " → ".join(
    f"{s['resource']} ({s['duration']}m)" for s in st.session_state.pathway
)
st.write(f"**Current pathway:** {pathway_summary}")

st.subheader("Legend")
spans = " ".join(
    f"<span style='background-color:{COLOR_MAP[v][1]};color:{'white' if v == BLOCKED else 'black'};"
    f"padding:4px 10px;{('border:1px solid #ccc;' if v == FREE else '')}'>{lbl}</span>"
    for v, lbl in [(FREE, "Free"), (BLOCKED, "Blocked (manual)"), (PATIENT, "Patient (scheduled)")]
)
st.markdown(spans, unsafe_allow_html=True)

st.subheader("Calendar — Monday")
styled = build_display_df(st.session_state.calendar).style.map(style_cell)
st.dataframe(styled, height=(NUM_SLOTS + 2) * 35, use_container_width=True)


# Action buttons
st.subheader("Schedule")
bcol1, bcol2, bcol3, _ = st.columns([1.2, 1, 1, 1.5])

with bcol1:
    if st.button("Schedule patient", type="primary", use_container_width=True):
        st.session_state.calendar[st.session_state.calendar == PATIENT] = FREE

        path = st.session_state.pathway
        total_path_min = sum(s["duration"] for s in path)
        total_path_slots = total_path_min // SLOT_MINUTES

        if not path:
            st.session_state.schedule_result = None
            st.error("Pathway is empty. Add at least one step.")
        elif total_path_slots > NUM_SLOTS:
            st.session_state.schedule_result = None
            st.error(f"Pathway is {total_path_min} min but the day is only "
                     f"{NUM_SLOTS * SLOT_MINUTES} min. Shorten the pathway.")
        else:
            result = find_earliest_slot(st.session_state.calendar, path)
            if result is None:
                st.session_state.schedule_result = None
                st.error("Pathway fits in the day, but no window is free "
                         "given the current blocks. Remove some blocks and try again.")
            else:
                apply_schedule(st.session_state.calendar, result)
                st.session_state.schedule_result = result
                st.rerun()

with bcol2:
    if st.button("Clear schedule", use_container_width=True):
        st.session_state.calendar[st.session_state.calendar == PATIENT] = FREE
        st.session_state.schedule_result = None
        st.rerun()

with bcol3:
    if st.button("Reset all", use_container_width=True):
        st.session_state.calendar = np.zeros((NUM_SLOTS, len(RESOURCES)), dtype=int)
        st.session_state.schedule_result = None
        st.rerun()


# Schedule trace
if st.session_state.schedule_result is not None:
    r = st.session_state.schedule_result
    st.success(f"Patient scheduled from {slot_to_time(r['start_slot'])} "
               f"to {slot_to_time(r['end_slot'])}.")
    st.write("**Step-by-step placement:**")
    for res, lo, hi in r["placements"]:
        st.write(f"- {res}: {slot_to_time(lo)} → {slot_to_time(hi)}")
# Care Pathway Scheduler

Patient scheduling tool. Takes a configurable care pathway
(sequence of resources with durations) and a day's blocked time slots, then finds
the earliest window where the full pathway fits.

## How to run

```bash
python3 -m venv venv
source venv/bin/activate
pip install streamlit numpy pandas
streamlit run app.py
```

Opens at http://localhost:8501.

## How it works

The calendar is a NumPy 2D array (36 rows x 4 columns). Rows are 15-minute slots
from 8 AM to 5 PM. Columns are Doctor, NMT, Patient, Scan. Each cell is 0 (free),
1 (manually blocked), or 2 (patient scheduled). Three values instead of two so the
UI can color them differently and the scheduler can clear patient cells without
touching manual blocks.

The scheduler (find_earliest_slot) does a sliding window search. For each candidate
start time, it walks the pathway step by step. Non-GAP steps check their resource
column with np.all on a NumPy slice. GAP steps skip the resource check but still
hold the Patient lane. First start where everything fits wins.

Complexity: O(slots x pathway_length). For 36 slots and 7 steps, about 250 operations.

## Stack

- Python 3
- Streamlit (UI)
- NumPy (calendar matrix and slice checks)
- Pandas (DataFrame bridge for Streamlit rendering)

## Features

- Editable care pathway (add/remove/reorder steps, change resource and duration)
- Single-day calendar with manual block management
- Earliest-fit scheduler with visual color distinction (dark = blocked, light = patient)
- Step-by-step placement trace
- Clear schedule (keeps blocks) and reset all

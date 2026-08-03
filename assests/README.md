# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # Windows: copy .env.example .env
# then edit .env and paste your key from https://aistudio.google.com/apikey
```

The rest of the app works fully with no key configured — only the "🤖 AI Care Assistant" tab needs `GEMINI_API_KEY` to be set.

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.

## 🖥️ Sample Output

Paste a sample of your app's CLI or Streamlit output here so a reader can see what a generated plan looks like:

```
======================================================================
TODAY'S SCHEDULE FOR SARAH
Pets: Max (Labrador Retriever) & Luna (Siberian Husky) & Cooper (Beagle)
======================================================================
05:45 — Luna Early morning jog | 60 min | Priority: high | Status: pending
06:30 — Max Morning run | 45 min | Priority: high | Status: pending
07:00 — Max Breakfast | 10 min | Priority: high | Status: pending
07:00 — Cooper Breakfast | 10 min | Priority: high | Status: pending
07:00 — Max Playtime | 20 min | Priority: high | Status: pending
12:00 — Cooper Midday walk | 20 min | Priority: medium | Status: pending
12:30 — Luna Lunch | 15 min | Priority: high | Status: pending
15:00 — Max Afternoon fetch | 30 min | Priority: medium | Status: pending
16:00 — Cooper Training session | 25 min | Priority: medium | Status: pending
18:30 — Luna Dinner | 10 min | Priority: high | Status: pending
18:30 — Luna Evening play session | 45 min | Priority: high | Status: pending

======================================================================
SCHEDULING CONFLICT WARNINGS
======================================================================
[CONFLICT] Max has multiple tasks at 2026-07-05 07:00: "Breakfast" & "Playtime"
[MULTI-PET] Max, Cooper scheduled simultaneously at 2026-07-05 07:00: Max: "Breakfast" & Cooper: "Breakfast" & Max: "Playtime"
[CONFLICT] Luna has multiple tasks at 2026-07-05 18:30: "Dinner" & "Evening play session"
======================================================================
```


## 🧪 Testing PawPal+

```bash
# Run the full test suite:
pytest

# Run with coverage:
pytest --cov
```

Sample test output:

```
Name                            Stmts   Miss  Cover
---------------------------------------------------
pawpal_system.py                  192     40    79%
tests\test_pawpal.py              292     21    93%
tests\test_recurring_tasks.py      76      7    91%
---------------------------------------------------
TOTAL                             560     68    88%
```

## 📐 Smarter Scheduling

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Task sorting | `Scheduler.viewSchedule()` | Sorts all tasks by time using `sorted(self.tasks, key=lambda task: task.time)` |
| Filtering by status | `Scheduler.getTasksByStatus(status)` | Filters tasks by completion status: "pending", "completed", or "missed" |
| Filtering by pet | `Scheduler.getTasksByPetName(pet_name)` or `Pet.getTasks()` | Returns only tasks assigned to a specific pet (case-insensitive) |
| Conflict detection | `Scheduler.detectConflicts()` | Identifies overlapping tasks: same pet at same time OR multiple pets at same time |
| Conflict display | `Scheduler.displayConflicts()` | Formats and displays conflict warnings; shows "[OK] No conflicts" if clear |
| Recurring task generation | `Task.generateNextInstance()` | Creates next instance by calculating time based on frequency (daily +1 day, weekly +1 week, etc.) |
| Recurring task auto-generation | `Scheduler.taskCompleted(taskId)` | Marks task complete AND automatically generates next instance for recurring tasks |
| Recurring task bulk generation | `Scheduler.generateDailyTasks()` | Pre-generates future instances: 365 daily, 52 weekly, 12 monthly instances |
| AI-generated care plans (RAG + Agentic) | `care_guidelines.retrieve_guidelines()`, `ai_care_assistant.generate_care_plan()` | Retrieves breed/age/activity-matched guidelines from a local JSON knowledge base, drafts tasks via a Gemini structured-output call whose durations/frequencies are grounded in those guidelines, then self-checks the draft against the existing `Scheduler.detectConflicts()` and retries (feeding conflicts back to the model) up to 3 times before flagging any that remain |

## 🤖 AI Care Assistant — how it works

The "🤖 AI Care Assistant" tab adds a genuine applied-AI feature on top of the rule-based scheduler above — it doesn't just call an LLM, it retrieves grounding data and checks its own work before showing you anything:

1. **Retrieve** — `care_guidelines.retrieve_guidelines()` matches the selected pet's species/breed/activity level/age against a small local knowledge base (`data/breed_guidelines.json`) of care guidelines, ranked most-specific first.
2. **Draft** — `ai_care_assistant.generate_care_plan()` sends the pet's profile and the retrieved guidelines to Gemini, which must ground each proposed task's duration/frequency in a specific guideline (named in a `rationale` field) via a forced structured-JSON response — no free-form prose to parse.
3. **Validate** — every proposed task is checked against a structural guardrail (`validate_task_dict()`) before it's ever turned into a real `Task` object; malformed entries are dropped and logged, never constructed.
4. **Self-check and retry** — the draft is checked against the *existing* `Scheduler.detectConflicts()`; if conflicts are found, they're fed back to Gemini and it retries (up to 3 times), then falls back to one local time-nudge pass if conflicts remain — any it couldn't resolve are flagged in the UI, not hidden.
5. **Log** — every step (retrieval hits, prompt sent, validation results, conflict-check outcome per iteration) is logged to `ai_care_assistant.log` and the console for auditability.

If `GEMINI_API_KEY` isn't set, the rest of the app keeps working normally — only this tab shows a config error with setup instructions.

## 📸 Demo Walkthrough

1. **Set up your owner profile** — In the sidebar, enter your name and contact info, then click "Initialize PawPal" to create your account.

2. **Add your pets** — Go to the "🐕 Manage Pets" tab and fill in pet details (name, type, breed, age, health info, activity level). Your pets appear in a collapsible list on the right with a delete option.

3. **Create tasks for your pets** — In the "📝 Add Task" tab, select a pet from the dropdown and enter task details: description, time, frequency (one-time/daily/weekly/monthly/yearly), priority level, and duration in minutes. Click "Add Task" to save.

4. **View today's schedule** — Go to the "📅 Today's Schedule" tab to see all tasks sorted by time. The app displays each task with pet name, description, duration, priority, and completion status. If conflicts exist, they appear at the top in an expandable warning section.

5. **Manage tasks** — In the "⚙️ Manage Tasks" tab, filter tasks by status (pending/completed/missed) and/or by pet name. For each task, you can mark it complete (which auto-generates the next recurring instance) or delete it. The count shows how many tasks match your filters.

6. **Generate an AI care plan** — Go to the "🤖 AI Care Assistant" tab, pick a pet, and click "Generate AI Care Plan." The assistant retrieves relevant care guidelines for that pet's breed/age/activity level, asks Gemini to draft a set of tasks grounded in those guidelines, and automatically checks the draft for scheduling conflicts before you add it — any conflicts it couldn't resolve are flagged, not hidden. Click "Add All to Schedule" to accept the proposed tasks.

**Screenshot**:
![Screenshot of homescreen of PawPal](image.png)
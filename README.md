# FitFindr 🛍️

FitFindr is a thrift-shopping styling agent. You describe a secondhand piece you're
after; it searches a mock listings dataset, styles the best match against your existing
wardrobe, and writes a casual, post-ready caption ("fit card") for the look.

It is built as a small **planning-loop agent**: a single `run_agent()` orchestrates three
tools in sequence, passing state through one session dict and branching when a step
returns nothing useful.

---

## Setup

```bash
pip install -r requirements.txt
```

Add your Groq API key to a `.env` file in the project root (free key at
[console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Run

```bash
python app.py
```

Open the URL printed in your terminal (usually http://localhost:7860 — check the output,
the port can differ). Submit a query and the three panels populate: **Top listing
found**, **Outfit idea**, **Your fit card**.

Run the agent from the command line instead:

```bash
python agent.py     # runs a happy-path query and the no-results branch
pytest tests/       # 10 isolation tests, one per failure mode + happy paths
```

---

## Tool Inventory

### 1. `search_listings(description, size, max_price) -> list[dict]`
- **Inputs**
  - `description` (`str`): free-text search terms, e.g. `"vintage graphic tee"`. Matched
    (case-insensitive, token overlap) against each listing's `title`, `description`, and
    `style_tags`.
  - `size` (`str | None`): desired size, e.g. `"M"`. Case-insensitive; `"M"` matches
    `"S/M"`, `"8"` matches `"US 8"`. `None` = no size filter.
  - `max_price` (`float | None`): inclusive price ceiling in USD. `None` = no price filter.
- **Output**: a `list[dict]` of full listing dicts (fields: `id`, `title`, `description`,
  `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`),
  sorted by relevance score (keyword-overlap count), highest first. Returns `[]` when
  nothing matches — never raises.
- **Purpose**: find candidate items and rank them so the loop can pick the top one.
- Uses `load_listings()` from `utils/data_loader.py` (no file I/O re-implemented).

### 2. `suggest_outfit(new_item, wardrobe) -> str`
- **Inputs**
  - `new_item` (`dict`): the selected listing dict from `search_listings`.
  - `wardrobe` (`dict`): `{"items": [...]}`, each item with `id`, `name`, `category`,
    `colors`, `style_tags`, optional `notes`.
- **Output**: a `str` styling suggestion that names specific wardrobe pieces plus a
  styling tip. If the wardrobe is empty, returns general styling advice instead.
- **Purpose**: turn a found item into a concrete outfit using what the user already owns.
- Calls the LLM (Groq `llama-3.3-70b-versatile`, temperature 0.7).

### 3. `create_fit_card(outfit, new_item) -> str`
- **Inputs**
  - `outfit` (`str`): the styling suggestion from `suggest_outfit`.
  - `new_item` (`dict`): the same selected listing dict (for `title`, `price`, `platform`).
- **Output**: a `str` — a short, casual social-media caption. If `outfit` is empty or
  whitespace-only, returns a descriptive error string instead of raising.
- **Purpose**: produce the shareable artifact the user actually posts.
- Calls the LLM (temperature 1.0, so repeated calls on the same input vary).

---

## How the Planning Loop Works

`run_agent(query, wardrobe)` in [`agent.py`](agent.py) drives a fixed sequence with **one
real decision point** — it is not "always call all three tools."

1. **Initialize** a session dict (`_new_session`).
2. **Parse** the query with regex (`_parse_query`) into `description`, `size`,
   `max_price`. (Regex, not an LLM — the query format is simple and this keeps parsing
   deterministic and free.) Stored in `session["parsed"]`.
3. **Search** — call `search_listings(...)` and store `session["search_results"]`.
   **This is the branch that makes the agent an agent:**
   - If `results == []` → write a helpful `session["error"]` (tailored to which filters
     were applied) and **return early**. `suggest_outfit` and `create_fit_card` are never
     called with empty input.
   - Otherwise → `session["selected_item"] = results[0]` (top relevance) and continue.
4. **Suggest outfit** — call `suggest_outfit(selected_item, wardrobe)`, store
   `session["outfit_suggestion"]`. The tool handles an empty wardrobe itself (general
   advice), so the loop needs no separate branch for it.
5. **Create fit card** — call `create_fit_card(outfit_suggestion, selected_item)`, store
   `session["fit_card"]`.
6. **Return** the session.

The agent's behavior therefore *differs by input*: an impossible query stops after step 3
with an error and no outfit/card; a matchable query runs all the way through.

---

## State Management

A single `session` dict is the source of truth for one interaction. Each step reads the
value the previous step wrote and writes its own output back — tools are never chained by
re-prompting the user or re-deriving values:

| Key | Type | Written by |
|-----|------|-----------|
| `query` | `str` | `_new_session` (original input) |
| `parsed` | `dict` | step 2 — `{description, size, max_price}` |
| `search_results` | `list[dict]` | step 3 |
| `selected_item` | `dict \| None` | step 3 (`results[0]`) |
| `wardrobe` | `dict` | session init |
| `outfit_suggestion` | `str \| None` | step 4 |
| `fit_card` | `str \| None` | step 5 |
| `error` | `str \| None` | set on the no-results early return |

`selected_item` flows from search → `suggest_outfit` → `create_fit_card` as the *same
object*; `outfit_suggestion` flows from `suggest_outfit` straight into `create_fit_card`.
(Verified by object-identity checks during Milestone 4 — the dict passed into
`suggest_outfit` is the exact `session["selected_item"]`.)

[`app.py`](app.py)'s `handle_query()` reads this session: on `error` it fills only the
first panel; otherwise it formats `selected_item` and returns the outfit and fit card.

---

## Error Handling (per tool)

| Tool | Failure mode | Agent response |
|------|--------------|----------------|
| `search_listings` | No listing matches | Returns `[]` (no exception). The loop sets a specific `error` and stops before styling. |
| `suggest_outfit` | Wardrobe is empty | Returns general styling advice (non-empty string) instead of naming pieces — no crash. |
| `create_fit_card` | Outfit string empty/whitespace | Returns a descriptive error string, not an exception. |

**Concrete example (from testing, Milestone 5).** Running the impossible query through the
full agent:

```bash
$ python -c "from agent import run_agent; from utils.data_loader import get_example_wardrobe; \
  s = run_agent('designer ballgown size XXS under \$5', get_example_wardrobe()); \
  print(s['error']); print('fit_card:', s['fit_card'])"

No listings found for "designer ballgown" in size XXS under $5. Try removing the size
filter, raising your max price, using broader search terms.
fit_card: None
```

The user is told *what failed and what to try*, and `fit_card` stays `None` because the
later tools were never called. More triggered failures are recorded in
[`docs/failure_modes.md`](docs/failure_modes.md), and each mode has an automated test in
[`tests/test_tools.py`](tests/test_tools.py).

---

## How I Used AI

**1. Implementing `search_listings` (Milestone 3).** I gave the AI the Tool 1 spec block
from `planning.md` (parameter names/types, the sorted-list-of-dicts return shape, and the
"return `[]`, never raise" failure mode) plus the listing field list, and asked it to
implement the function using `load_listings()`. It produced a working filter+score
function. **What I changed:** I tightened the size matching so `"M"` matches `"S/M"` and
`"8"` matches `"US 8"` (token split on `/` and spaces) rather than a plain substring test,
and made sure zero-score listings were dropped before sorting.

**2. Implementing the planning loop (Milestone 4).** I gave the AI the **Planning Loop**,
**State Management**, and **Error Handling** sections plus the ASCII **Architecture
diagram** from `planning.md`, and asked it to implement `run_agent()` against the existing
session dict. It generated the sequence and the no-results branch. **What I overrode:** I
removed an early-return branch it added for the empty-wardrobe case — that case is handled
inside `suggest_outfit` (general advice), so the loop's only conditional is on the search
result. I also made the no-results error message name the actual filters that were applied
rather than a generic string.

---

## Spec Reflection

Writing the tool specs and the agent diagram first paid off most at the wiring stage: the
single-branch design (only `search_listings` results gate the flow) came straight from the
planning loop, so the implementation matched the spec with little rework.

The spec also drifted once — I had `suggest_outfit`/`create_fit_card` returning a `dict` in
`planning.md`, but the starter stubs and `agent.py` both expect `str`. I reconciled
`planning.md` back to `str` so the document and code agree. Lesson: when a starter
contract exists, the spec has to match it, not the other way around.

---

## Project Layout

```
fitfindr/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # wardrobe format + example/empty wardrobes
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py                   # the three tools (search_listings, suggest_outfit, create_fit_card)
├── agent.py                   # run_agent() planning loop + _parse_query()
├── app.py                     # Gradio UI + handle_query()
├── tests/test_tools.py        # isolation tests, one per failure mode
├── docs/failure_modes.md      # triggered-failure record (Milestone 5)
└── planning.md                # full agent spec + diagram
```

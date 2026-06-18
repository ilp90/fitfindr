# FitFindr — Triggered Failure Modes (Milestone 5)

Each of the three tools' failure modes was deliberately triggered from the terminal
and confirmed to recover gracefully (a specific, informative response — never a
Python exception). Reproduce any of these by running the commands below.

---

## 1. `search_listings` → zero results

**Command**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
```
**Output**
```
[]
```
Returns an empty list, no exception.

**Full agent with the same impossible query**
```bash
python -c "from agent import run_agent; from utils.data_loader import get_example_wardrobe; s = run_agent('designer ballgown size XXS under \$5', get_example_wardrobe()); print(s['error']); print(s['fit_card'])"
```
**Output**
```
No listings found for "designer ballgown" in size XXS under $5. Try removing the size filter, raising your max price, using broader search terms.
None
```
The agent tells the user *what failed and what to try*, and never calls `suggest_outfit`
(`outfit_suggestion` and `fit_card` stay `None`).

---

## 2. `suggest_outfit` → empty wardrobe

**Command**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```
**Output (example — LLM text varies)**
```
I'm so excited you found this adorable Y2K Baby Tee. This butterfly print top is
perfect for creating a sweet and playful look. You can pair it with some high-waisted
jeans or a flowy skirt for a casual, cottagecore vibe... [general styling advice]
```
Returns a useful non-empty string (general styling advice) instead of crashing or
returning `""`.

---

## 3. `create_fit_card` → empty outfit string

**Command**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```
**Output**
```
Couldn't generate a fit card: no outfit suggestion was provided. Run suggest_outfit first to get a styling idea.
```
Returns a descriptive error message string, not an exception.

---

All three failure modes are also covered by automated tests in
[`tests/test_tools.py`](../tests/test_tools.py) (`test_search_empty_results`,
`test_suggest_outfit_empty_wardrobe`, `test_create_fit_card_empty_outfit`).

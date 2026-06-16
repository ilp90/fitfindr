# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset (loaded via `load_listings()` from `utils/data_loader.py`) and returns the listings that match the user's request, sorted by relevance. It scores each listing by how well its `title`, `description`, and `style_tags` match the search terms, then filters out anything over the price cap or in the wrong size. Must handle the case where nothing matches.

**Input parameters:**
- `description` (str): the free-text search terms from the user, e.g. `"vintage graphic tee"`. Matched (case-insensitive, token overlap) against each listing's `title`, `description`, and `style_tags`.
- `size` (str | None): desired size, e.g. `"M"`. When provided, only listings whose `size` field matches (after normalization — `"S/M"`, `"M"`, etc.) are kept. `None` means no size filter.
- `max_price` (float | None): upper price bound in USD. Listings with `price` greater than this are excluded. `None` means no price filter.

**What it returns:**
A `list[dict]` of matching listings, sorted by relevance score (highest first). Each dict is a full listing with the fields: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str). Returns an empty list `[]` when no listing satisfies the filters.

**What happens if it fails or returns nothing:**
If the result list is empty, the planning loop does NOT proceed to `suggest_outfit`. It writes a user-facing error message into session state suggesting concrete adjustments (loosen the size, raise `max_price`, or broaden the search terms) and returns early.

---

### Tool 2: suggest_outfit

**What it does:**
Takes the listing the agent picked plus the user's wardrobe and produces a natural-language styling suggestion, naming specific wardrobe pieces that pair well with the new item (by matching `category`, `colors`, and `style_tags`) and giving a short styling tip.

**Input parameters:**
- `new_item` (dict): the listing selected by the agent in Step 1 — a full listing dict (same fields as a `search_listings` result). Provides the `category`, `colors`, and `style_tags` to style around.
- `wardrobe` (dict): the user's closet, shaped `{"items": [ ... ]}`, where each item has `id` (str), `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), and optional `notes` (str). Loaded via `get_example_wardrobe()` (populated) or `get_empty_wardrobe()` (empty) from the data loader.

**What it returns:**
A `dict` with:
- `suggestion` (str): the natural-language styling text that references at least one wardrobe item by `name` (e.g. "Pair this with your baggy straight-leg jeans and chunky white sneakers…") plus a concrete styling tip.
- `items_used` (list[str]): the `id`s of the wardrobe items referenced in the suggestion (e.g. `["w_001", "w_007"]`), so `create_fit_card` can reference the exact pieces.

The whole dict is passed into `create_fit_card`.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the tool cannot reference real pieces. The planning loop checks for this BEFORE calling the tool: it writes a message into session state telling the user to add items to their wardrobe (and may still surface the listing from Step 1), then skips `create_fit_card`. If the wardrobe has items but no strong match is found, the tool returns a generic-but-valid suggestion rather than failing.

---

### Tool 3: create_fit_card

**What it does:**
Turns the styling suggestion and the new item into a short, casual social-media-style caption (the "fit card") the user could post — first-person, lowercase, emoji-friendly, mentioning the platform and price.

**Input parameters:**
- `outfit` (dict): the object returned by `suggest_outfit` — with `suggestion` (str) describing how to wear the item and `items_used` (list[str]) naming the wardrobe pieces. The caption draws on `outfit["suggestion"]`.
- `new_item` (dict): the same selected listing dict, used to pull concrete details for the caption (`title`, `price`, `platform`, `condition`).

**What it returns:**
A `str` — one short caption, e.g. *"thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories"*. This is the final artifact shown to the user.

**What happens if it fails or returns nothing:**
If `outfit` is missing or `outfit["suggestion"]` is empty, or `new_item` lacks required fields (`title`/`price`/`platform`), the planning loop skips this tool and still returns the listing and styling suggestion gathered so far, with a note that the caption couldn't be generated — it never returns a malformed or half-empty card.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a fixed sequence with early-exit guards keyed off session state, not free-form tool choice:

1. **Parse the query** into `description`, `size`, `max_price`. Store them in the session.
2. **Call `search_listings(description, size, max_price)`.** Check the result:
   - If `results == []` → set `session["error"] = "No listings found…"` (with adjustment suggestions) and **return early**. Do not proceed.
   - Else → set `session["selected_item"] = results[0]` (top relevance) and continue.
3. **Check the wardrobe** before styling:
   - If `wardrobe["items"] == []` → set `session["error"]` telling the user to add wardrobe items, keep `selected_item` so the listing can still be shown, and **return early** (skip steps 4–5).
   - Else → continue.
4. **Call `suggest_outfit(selected_item, wardrobe)`** → set `session["outfit_suggestion"]`.
5. **Validate before the card:** if `outfit_suggestion["suggestion"]` is non-empty and `selected_item` has `title`/`price`/`platform` → **call `create_fit_card(outfit_suggestion, selected_item)`** → set `session["fit_card"]`. Otherwise skip and note the card couldn't be generated.
6. **Done condition:** the loop ends when either an `error` was set (early return) or `fit_card` has been produced. Return the session.

Each step's behavior is decided by inspecting session state written by the previous step — the loop never calls a downstream tool with missing/empty input.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict carries state through the run; each tool reads from it and writes its output back. Tools are not chained by passing one return value straight into the next call — the loop pulls inputs out of the session, which keeps the error guards in one place.

Tracked keys:
- `query` (str), `description` (str), `size` (str | None), `max_price` (float | None) — parsed from the user's request.
- `results` (list[dict]) — raw output of `search_listings`.
- `selected_item` (dict | None) — `results[0]`, the listing chosen for styling.
- `wardrobe` (dict) — the user's closet, loaded once at session start.
- `outfit_suggestion` (dict | None) — output of `suggest_outfit`, shaped `{"suggestion": str, "items_used": list[str]}`.
- `fit_card` (str | None) — output of `create_fit_card`.
- `error` (str | None) — set on any early-exit path; its presence tells the loop to stop and tells the renderer to show the error instead of a result.

Flow: `search_listings` writes `results` → loop sets `selected_item` → `suggest_outfit` reads `selected_item` + `wardrobe`, writes `outfit_suggestion` → `create_fit_card` reads `outfit_suggestion` + `selected_item`, writes `fit_card`.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Stop the pipeline. Tell the user: "I couldn't find any vintage graphic tees under $30 in your size. Try raising your price a little, removing the size filter, or using broader terms like 'graphic tee' or 'band tee'." Do not call `suggest_outfit`. |
| suggest_outfit | Wardrobe is empty | Don't fabricate items. Still show the found listing, then say: "I found this for you, but your wardrobe is empty so I can't style it yet — add a few pieces (e.g. your go-to jeans and shoes) and I'll suggest a full look." Skip `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete | Skip card generation and return what's already gathered (listing + styling suggestion), with: "Here's the item and how to style it — I couldn't generate a caption this time, but you're all set to post." Never return a blank or half-filled card. |

---

## Architecture

```
User query ("vintage graphic tee under $30, I wear baggy jeans + chunky sneakers")
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PLANNING LOOP                                                                 │
│   parse query → session{description, size, max_price, wardrobe}               │
│                                                                               │
│   ├─► search_listings(description, size, max_price)                           │
│   │       │ results == []                                                     │
│   │       ├──► [ERROR] session.error = "No listings found, try…" ──┐          │
│   │       │                                                        │          │
│   │       │ results == [item, ...]                                 │          │
│   │       ▼                                                        │          │
│   │   session.selected_item = results[0]                           │          │
│   │       │                                                        │          │
│   │   wardrobe.items == []                                         │          │
│   │       ├──► [ERROR] session.error = "wardrobe empty, add…" ─────┤          │
│   │       │                                                        │          │
│   ├─► suggest_outfit(selected_item, wardrobe)                      │          │
│   │       │                                                        │          │
│   │   session.outfit_suggestion = {suggestion:"pair w/ baggy…",   │          │
│   │                                 items_used:["w_001","w_007"]}  │          │
│   │       │                                                        │          │
│   │   suggestion empty OR item missing title/price/platform        │          │
│   │       ├──► [SKIP card] note "couldn't generate caption" ───────┤          │
│   │       │                                                        │          │
│   └─► create_fit_card(outfit_suggestion, selected_item)            │          │
│           │                                                        │          │
│       session.fit_card = "thrifted this tee off depop… 🖤"         │          │
│           │                                                        │          │
└───────────┼────────────────────────────────────────────────────── ┘          │
            │                       error / skip paths converge here ◄──────────┘
            ▼
   Return session → render to user
   (listing + styling suggestion + fit card, OR the error message)
```

State legend: every box prefixed `session.` is a key in the shared session dict
(see State Management). Each tool reads the keys written by the step above it.

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

I'll use **Claude (Claude Code)**, one tool at a time, giving it the relevant spec block from this file as the prompt.

- **search_listings:** Input = the *Tool 1* block (inputs, return shape, failure mode) + the listing field list from the data notes. I'll ask Claude to implement it in `tools.py` using `load_listings()` from `utils/data_loader.py`, scoring by token overlap across `title`/`description`/`style_tags` and filtering by `size` and `max_price`. *Verify before trusting:* read the code to confirm it (a) filters by all three params, (b) returns full listing dicts sorted by relevance, (c) returns `[]` (not error) on no match. Then test 3 queries: a normal hit, a too-low `max_price` (expect `[]`), and a `size=None` query.
- **suggest_outfit:** Input = the *Tool 2* block + the wardrobe schema fields. Ask Claude to implement it matching `new_item` against `wardrobe["items"]` by `category`/`colors`/`style_tags` and returning a dict `{"suggestion": str, "items_used": list[str]}` that names real items. *Verify:* run it with `get_example_wardrobe()` (expect `items_used` ids that exist in the wardrobe and a suggestion naming them) and confirm the loop — not the tool — handles the empty-wardrobe case.
- **create_fit_card:** Input = the *Tool 3* block. Ask Claude to produce a short caption string from `outfit` + `new_item`. *Verify:* check it pulls `title`/`price`/`platform` and returns one casual line; test with a complete outfit.

**Milestone 4 — Planning loop and state management:**

Input = the **Planning Loop**, **State Management**, **Error Handling**, and **Architecture diagram** sections together. I'll ask Claude to implement the loop in `agent.py` driving the three finished tools, using a single `session` dict with the keys listed in State Management and the early-return guards from the diagram. *Verify:* trace the happy path from "A Complete Interaction" end-to-end, then force each error branch (no results, empty wardrobe, missing outfit) and confirm the loop returns early with the right `session.error` and never calls a downstream tool with empty input.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**In short:** FitFindr is a thrift-styling agent. When the user describes an item, `search_listings` filters the mock listings by terms, size, and max price and returns the best matches — the agent picks the top one. That item triggers `suggest_outfit`, which styles it against the user's wardrobe, and that suggestion triggers `create_fit_card`, which writes a casual caption. If `search_listings` finds nothing, the agent tells the user what to change (loosen the size, raise the price, or broaden the terms) and stops — it does not call the later tools with empty input.

**Step 1 — Search:**
The agent parses the request and calls `search_listings(description="vintage graphic tee", size=None, max_price=30.0)`. (`max_price` is a float; no size was stated, so it's left unconstrained.) The tool filters the 40 listings from `load_listings()` and returns matches sorted by relevance. The agent picks the top result — e.g. `lst_002` "Y2K Baby Tee — Butterfly Print", $18, depop, excellent condition.

**Step 2 — Suggest outfit:**
Using the result from Step 1, the agent calls `suggest_outfit(new_item=<the baby tee>, wardrobe=get_example_wardrobe())`. The wardrobe already contains baggy jeans (`w_001`) and chunky white sneakers (`w_007`), so the tool returns `{"suggestion": "Pair this with your baggy straight-leg jeans and chunky white sneakers…", "items_used": ["w_001", "w_007"]}`.

**Step 3 — Fit card:**
With the dict from Step 2, the agent calls `create_fit_card(outfit=<that dict>, new_item=<the baby tee>)`, which reads `outfit["suggestion"]` and returns a short, casual social-media-style caption for the look.

**Final output to user:**
The user sees the chosen listing (title, price, platform, condition), the styling suggestion describing how to wear it with their baggy jeans and chunky sneakers, and the fit-card caption they could post. (Error path: if Step 1 returns no listings, the user instead sees a message suggesting how to adjust their search, and Steps 2–3 never run.)

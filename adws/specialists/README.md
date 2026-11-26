# Specialists

A specialist is a prompt for a read-only Claude Code session that Ore can consult about this repository. Each one is a
Markdown file here, `<name>.md` (lower-case letters, digits, `-` and `_`), holding the system prompt.

Ore calls them through the Ore trigger's `consult` query (`adws/adw_triggers/trigger_ore.py`, Ore's
`docs/script-protocol.md` §8):

    uv run adws/adw_triggers/trigger_ore.py --ore-query consult <name> <repo>/.ore/pm/<run id>/request.json

The request holds the workspace, the goals, the items (with their checks, size, criteria, links and the last messages
of their conversation in Ore), the JSON schema of the answer and a time limit in minutes; for triage also Ore's
`workspaces`. When the user wrote on a card, it also holds their `message` (text and attached files) and the
`session_id` of the specialist's earlier session. Attached files are copied into `.ore/pm/<run id>/files/` (Office
documents get a `.txt` with their text beside them).

The trigger runs `claude -p` in the repository's root with this file as the extra system prompt, the request as the
message and the schema as `--json-schema`; with a `session_id` it continues that session (`--resume`) with the same
flags. The session can only read (Read, Glob, Grep, `git log`/`git show`/`git diff`, `gh pr list`/`gh pr view`/
`gh pr diff`/`gh pr checks`). It answers
`{"result", "session_id", "cost_usd"}` and removes the request's folder. The model is `ADW_CONSULT_MODEL` (default:
the items model).

Every answer may carry `messages` (`[{"item", "text"}]`): what the specialist says on an item's card in Ore, only when
it has something worth saying.

- `backlog.md`: closes duplicates and finds items already done in the code.
- `triage.md`: is each item development work for this repository, for another workspace, not development work, or
  several tasks to split?
- `planner.md`: the order to build in (goals, dependencies, size S/M/L), dependencies between items, and items that
  belong in one run.
- `scoper.md`: is an item clear enough to build? Testable acceptance criteria, or at most three questions for the user.

## After the build

Four more go through `consult` once the user starts building; their requests (version 3) carry the run or the card
instead of a backlog:

- `doctor.md`: the build doctor, when a run fails or sends no news for a while. The request's `run` holds its status,
  error, last message, phase, `log_tail` (the last lines of its log) and its parts. It answers a diagnosis and what to
  do: resume, retry, follow up with an instruction, or nothing.
- `pr_reviewer.md`: when a card's pull requests are ready to merge. The request's `card` holds its items with their
  criteria, its pull requests, the approved design's path, the test plan and the risks. A verdict per pull request
  (pass, or the gaps); Ore asks the run to close the gaps when the user accepts.
- `merge_planner.md`: when a card has more than one pull request to merge: the order, and notes on the ones to bring
  up to date.
- `closer.md`: when all of a card's pull requests are merged: is each item done, and what is left over (each one
  becomes a new proposed item in Ore).

Ore also asks the trigger's `revert` query (`--ore-query revert <pr number>`) when the user sends a finished card
back for review and ticks "Also open revert pull requests". Unlike the specialists it writes: in a temporary worktree
(`trees/revert-pr-<n>`) it reverts the PR's merge commit on a new branch `revert-<n>-<short sha>` from the PR's base
branch, pushes it and opens the pull request, then removes the worktree. The main checkout is never touched.

## The question round

Three more specialists work inside a run, after the user starts the groups and before anything is built (the
trigger's checks phase; Ore shows it in the Approved lane). The trigger runs them itself, not through `consult`:

- `tests.md`: the test planner, for every group: how we'll know it works. The plan goes into the issue.
- `risk.md`: the risk reviewer, for groups of size M or L: migrations, security, breaking changes, data loss. Risks
  that need the user's OK are asked as a review (gate `risk`); accepted risks go into the issue.
- `designer.md`: the designer, for groups whose screen changes are `significant`: one self-contained, clickable HTML
  prototype per version at `.ore/designs/<run id>/<group slug>/v<n>.html`, reviewed by the user (gate `design`).
  "Ask for changes" continues the designer's session with the feedback and the attached files for the next version.
  The approved one is copied into the workflow's worktree as `specs/designs/<group slug>.html`.

The test planner and the risk reviewer are read-only like the others. The designer may write only in its prototype's
folder; afterwards the trigger checks `git status` and stops the run if anything outside `.ore/` changed. The models
are `ORE_SPECIALIST_MODEL` and `ORE_DESIGNER_MODEL` (default: the run's model); `ORE_SPECIALISTS_PARALLEL` (3) sessions
run at once.

The trigger has a built-in copy of each in case the file is missing; keep them in step.

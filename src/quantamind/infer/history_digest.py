"""A model's reading of the first scan's counts -- opt-in, and it is never shown any code.

WHAT: `digest(spots, *, project, gcloud)` returns one paragraph about a `Hotspots` table, or a
      typed refusal string. `PROMPT` is the whole instruction and is checked by a unit test.
WHY:  **THE SCAN IS MODEL-FREE AND THIS MODULE IS WHY IT STAYS THAT WAY.** `docs/product/
      PITCH_DECK.md` sells the replay on one asymmetry: a prospect's history costs us CPU and
      costs a model-per-change reviewer an inference pass per change. **A narration that ran by
      default would delete that claim**, so `run_scan` calls this only when asked for a project by
      name, and the default path opens no socket at all.

      **ONLY COUNTS CROSS THE BOUNDARY -- PATHS AND NUMBERS, NEVER FILE CONTENT.** The scan already
      holds the whole clone; sending it would be trivial and is refused. `ingest/context/egress.py`
      makes the same distinction for a Jira ticket: reading something and transmitting it are two
      acts, and the second needs consent. A file PATH is still the customer's information, which is
      why the CLI says so before it sends and the help text does not hide the flag's cost.

      **THE MODEL IS ASKED TO DESCRIBE, NEVER TO DIAGNOSE.** It has not seen a line of the code, so
      any sentence about a defect would be invention. Four blind rater pools put this product's raw
      findings at 66.7-82.1% wrong when the model COULD see the diff; with only counts, a defect
      claim has nothing behind it at all. The prompt bans it, and the renderer labels whatever
      comes back.

      **A FAILURE RETURNS A SENTENCE, NEVER AN EXCEPTION AND NEVER SILENCE.** The scan's value is
      the table, which already printed. An unreachable model must not take the report down with it,
      and an empty narration would read as "the model had nothing to say".
IMPORTS: infer.prompt_once, store.touches for `Hotspots`. Leftward only.
CONSUMED BY: `serve/commands/run_scan.py`.
"""

from __future__ import annotations

from quantamind.infer.prompt_once import ask
from quantamind.store.touches import Hotspots

# Enough rows to show a shape, few enough that the prompt stays one screen.
ROWS = 10

PROMPT = """You are reading a table of commit counts from one git repository. Each row is a file
path and the number of times a commit touched it. You have NOT been shown any source code.

{table}

Total: {touches} file-touches across {tracked} files, over {days} days of history.

Write ONE paragraph, at most 80 words, describing what this DISTRIBUTION looks like -- how
concentrated the rework is, and what kind of files are carrying it, judging only by their paths.

Rules you must follow:
- Do not name a bug, a defect, or a risk. You cannot see the code and would be inventing it.
- Do not recommend a fix.
- Do not say a file is "problematic", "risky" or "bad". Say what the counts show.
- If the distribution is flat or the history is short, say so plainly; that is a real answer.
"""

UNREACHABLE = "The model could not be reached, so there is no reading of the table above: {reason}"

REFUSED = "There is nothing for a model to read: the scan found no history."


def digest(
    spots: Hotspots,
    *,
    project: str,
    gcloud: str = "gcloud",
) -> str:
    """One paragraph about the counts, or a sentence saying why there is none.

    **NEVER RAISES.** The caller has already printed the table that is the actual product of a
    scan; a narration that took the command's exit code with it would trade the half that is
    reproducible for the half that is 25.0% correct.
    """
    if not spots.touches:
        return REFUSED

    table = "\n".join(f"{path}\t{count}" for path, count in spots.files[:ROWS])
    days = max(1, (spots.last - spots.first) // 86400)
    try:
        return ask(
            PROMPT.format(table=table, touches=spots.touches, tracked=spots.tracked, days=days),
            project=project,
            gcloud=gcloud,
        ).strip()
    except Exception as exc:
        # **THE TYPE AND THE MESSAGE BOTH TRAVEL.** `infer/prompt_once` raises several failure
        # kinds and a caller reading only the message cannot tell an auth refusal from a timeout.
        return UNREACHABLE.format(reason=f"{type(exc).__name__}: {exc}")

"""Put one prose rule to the model, and turn its reply into a verdict `verify/` can use.

WHAT: `judge_with(settings)` returns a `verify.judged_rule.Ask`, or `None` when inference is off.
      The returned callable takes `(rule, path, source)` and answers `(Verdict, quote, why)`.
WHY:  **D1c'S MODEL HALF LIVES HERE AND NOT IN `verify/`, ON PURPOSE.** `AGENTS.md` rule 7 says the
      layer order is "what stops `verify` importing `infer`" — and until this row it did not, since
      `infer` is to the LEFT of `verify` and the left-only rule allows a leftward import.
      `scripts/guard/check_conventions.py:FORBIDDEN` now refuses that pair by name, so
      `verify/judged_rule.py` takes the judge as a parameter and this module supplies it. **The
      layer that adjudicates the model's claims cannot import the layer that makes them**, and a
      guard says so rather than a sentence.

      **THE REPLY IS PARSED STRICTLY AND ANYTHING ELSE IS `UNDECIDED`.** A model asked for one of
      three words will occasionally write a paragraph. Reading a paragraph as `MET` is how a
      standard silently stops being enforced, so only an exact verdict token counts and everything
      else — including a reply we merely failed to understand — comes back undecided.

      **NO SCHEMA PARSER, BECAUSE THIS IS NOT A FINDING.** `infer/gemini.py:read` enforces the
      review schema and returns `Finding`s; a rule verdict is a different shape, and putting it
      through that parser would make an unparseable reply look like a model declining to answer.
      `infer/prompt_once.ask` is the transport for exactly this reason — `serve/settle.py` uses it
      the same way.

      **THE PROMPT SHOWS THE RULE'S OWN WORDS.** `Rule.description` is what the customer wrote and
      what the developer will read beside the verdict. Paraphrasing it here would mean the model
      judged one sentence and the comment quoted another.
IMPORTS: infer.prompt_once, types.{judged,rule,settings}. Leftward and sideways-right
      only from `serve/`, which is the rightmost layer and may reach both.
CONSUMED BY: `serve/review_delivery.py`, which passes the result into `verify/rule_check.enforce`.
"""

from __future__ import annotations

from quantamind.infer.prompt_once import ask as _ask
from quantamind.types.admission.model_route import ModelRoute
from quantamind.types.settings import Settings
from quantamind.types.standards.judged import Verdict
from quantamind.types.standards.rule import Rule
from quantamind.verify.judged_rule import Ask

SOURCE_CAP = 20_000
"""Characters of the file shown to the model. A truncated file is announced in the prompt.

**A FILE CUT IN HALF WITHOUT SAYING SO INVITES A VERDICT ABOUT CODE THE MODEL NEVER SAW.** The
prompt says the text is partial, so `MET` over a truncated file is at least an honest answer to
the question that was actually asked."""

PROMPT = """A repository declares this standard for its own code:

  {description}

Below is `{path}` as this change leaves it{truncated}.

Answer with exactly one of these on the first line, and nothing else on that line:
  MET        — the file complies with the standard
  BROKEN     — the file violates the standard
  UNDECIDED  — the standard does not apply here, or you cannot tell

If and only if you answer BROKEN, the second line must be a single line copied VERBATIM from the
file showing the violation. Copy it exactly; do not summarise, reformat or invent it. A quote that
is not in the file will be discarded and your answer will be recorded as UNDECIDED.

Any remaining lines are one sentence explaining the verdict to the developer who wrote the code.

Judge only the standard above. Do not report anything else you notice.

--- {path} ---
{source}
"""

_VERDICTS = {"MET": Verdict.MET, "BROKEN": Verdict.BROKEN, "UNDECIDED": Verdict.UNDECIDED}


def parse_reply(text: str) -> tuple[Verdict, str, str]:
    """The verdict, the quote and the explanation. **Anything unrecognised is `UNDECIDED`.**

    Separated from the transport so it can be tested against real replies without a network call —
    and every malformed shape this has to survive is a test rather than a hope.
    """
    lines = [line.rstrip() for line in text.strip().splitlines()]
    if not lines:
        return Verdict.UNDECIDED, "", "empty reply"
    verdict = _VERDICTS.get(lines[0].strip().strip("*`").upper())
    if verdict is None:
        # **NOT A GUESS.** A reply that does not start with a verdict token is a reply we did not
        # understand, and reading it as MET is how enforcement stops without anyone noticing.
        return Verdict.UNDECIDED, "", "reply did not begin with a verdict"
    if verdict is not Verdict.BROKEN:
        return verdict, "", " ".join(lines[1:]).strip()
    quote = lines[1].strip() if len(lines) > 1 else ""
    return verdict, quote, " ".join(lines[2:]).strip()


def judge_with(settings: Settings, route: ModelRoute | None = None) -> Ask | None:
    """A judge bound to these settings, or `None` when no model may be called.

    **`None` IS THE CONFIGURED-OFF ANSWER AND IT IS NOT AN ERROR.** `verify/judged_rule.judge_all`
    returns nothing for it, so a deployment without inference runs the entire deterministic half
    unchanged — the half that carries the product.
    """
    if not settings.inference_enabled or not settings.inference_project:
        return None

    def ask(rule: Rule, path: str, source: str) -> tuple[Verdict, str, str]:
        shown = source[:SOURCE_CAP]
        truncated = "" if len(source) <= SOURCE_CAP else " (truncated; you are seeing the start)"
        reply = _ask(
            PROMPT.format(
                description=rule.description, path=path, source=shown, truncated=truncated
            ),
            project=settings.inference_project,
            gcloud=settings.gcloud_path,
            route=route,
        )
        return parse_reply(reply)

    return ask

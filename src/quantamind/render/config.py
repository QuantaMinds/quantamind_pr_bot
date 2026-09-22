"""The resolved configuration, printed so a misconfiguration is visible before a run, not after.

WHAT: `render_config(settings)` renders every setting this build reads, one per line.
WHY:  **THIS IS A RENDERER AND IT WAS LIVING IN `serve/cli.py`.** Nothing about turning settings
      into text belongs to the command layer, and `cli.py` had reached the file-length cap with
      thirty-five lines of formatting in it. Moving it left is the split `AGENTS.md` rule 4 asks
      for rather than raising the cap.

      **CREDENTIALS ARE REPORTED AS SET OR UNSET, NEVER PRINTED.** `config` output lands in
      terminal scrollback and CI logs. An operator needs to know whether a token is configured;
      nobody needs the token on screen to learn that.
IMPORTS: types.settings only. The leftmost thing this layer can depend on.
CONSUMED BY: `serve/cli.py` behind `quantamind config`.
"""

from __future__ import annotations

from quantamind.types.settings import Settings


def render_config(settings: Settings) -> str:
    """The resolved configuration, so a misconfiguration is visible before a run, not after."""
    lines = [
        # **D7f: THE SHAPE IS THE FIRST LINE AN OPERATOR SHOULD SEE.** It decides what this
        # instance may reach, so a wrong value is a wrong deployment rather than a wrong setting.
        f"deployment_shape           {settings.deployment_shape}",
        f"database_path              {settings.database_path}",
        f"max_requests               {settings.max_requests}",
        f"threshold_percentile       {settings.threshold_percentile}",
        f"inference_enabled          {settings.inference_enabled}",
        # Not a secret: a GCP project id identifies a billing target, it authorises nothing.
        f"inference_project          {settings.inference_project or '(unset)'}",
        # The billing service's URL is configuration, not a credential; its bearer is never here.
        f"billing_url                {settings.billing_url or '(unset: the cached plan decides)'}",
        f"gcloud_path                {settings.gcloud_path}",
        f"model                      {settings.model}",
        f"subprocess_timeout_seconds {settings.subprocess_timeout_seconds}",
        f"clone_root                 {settings.clone_root}",
        f"app_id                     {settings.app_id or '(unset)'}",
        # The PATH, never the key. `app_auth` reads the file when it signs; a credential printed
        # by a `config` command is a credential in somebody's terminal scrollback.
        f"app_key_path               {settings.app_key_path or '(unset)'}",
        # **The one line here that says whether this process writes to somebody else's project.**
        # **REPORTED AS SET OR UNSET, NEVER PRINTED.** It is a credential, and `config` output
        # lands in terminal scrollback and CI logs. The operator needs to know whether public
        # reads are rate-limited; nobody needs the token itself on screen to learn that.
        f"oauth_client_id            {settings.oauth_client_id or '(unset)'}",
        # A credential. Reported as set or unset, never printed, like the token below it.
        f"oauth_client_secret        {'set' if settings.oauth_client_secret else '(unset)'}",
        f"public_read_token          {'set' if settings.public_read_token else '(unset)'}",
        f"posting_enabled            {settings.posting_enabled}",
        # **NO STRIPE ROWS, BECAUSE THIS SERVICE HAS NO STRIPE CONFIGURATION.** A price id and
        # two return URLs lived here while it sold subscriptions itself. The billing service owns
        # that now and this one is told the result; printing an empty Stripe row would suggest a
        # value an operator should go and set.
        "",
        f"runs a model on a review:  {settings.runs_model}",
    ]
    return "\n".join(lines)

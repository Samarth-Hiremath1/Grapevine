"""Loading of local credentials from a ``.env`` file.

Experiment entry points call :func:`load_env` once at startup so a developer can
keep their API key in a gitignored ``.env`` instead of exporting it in every
shell. Values already present in the real environment win, so an explicit
``export`` still overrides the file.

Nothing here ever logs, prints, or returns a credential value -- callers only
get booleans about presence.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Environment variable holding the OpenAI credential.
OPENAI_KEY_VAR = "OPENAI_API_KEY"
#: Environment variable holding the Anthropic credential.
ANTHROPIC_KEY_VAR = "ANTHROPIC_API_KEY"


def load_env(dotenv_path: str | Path | None = None) -> bool:
    """Load ``.env`` into the process environment if python-dotenv is available.

    Args:
        dotenv_path: Explicit path to the env file. Defaults to ``.env`` in the
            repository root (the parent of this package).

    Returns:
        ``True`` if a ``.env`` file was found and loaded, ``False`` otherwise.
        A missing file is not an error: the key may legitimately come from a
        shell export or CI secret instead.
    """
    path = Path(dotenv_path) if dotenv_path else Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional dependency
        return False
    # override=False: a real exported variable takes precedence over the file.
    load_dotenv(path, override=False)
    return True


def has_key(provider: str) -> bool:
    """Return whether a credential is present for ``provider``.

    Only reports presence -- never the value.
    """
    var = ANTHROPIC_KEY_VAR if provider == "anthropic" else OPENAI_KEY_VAR
    return bool(os.environ.get(var))


def key_var_for(provider: str) -> str:
    """Return the environment variable name a provider reads its key from."""
    return ANTHROPIC_KEY_VAR if provider == "anthropic" else OPENAI_KEY_VAR

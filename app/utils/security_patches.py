from __future__ import annotations

from typing import Any

"""Runtime security hardening hooks.

Currently used to mitigate a ReDoS issue in Pygments' AdlLexer
without waiting on an upstream release.
"""


def disable_vulnerable_pygments_lexers() -> None:
    """Disable Pygments lexers known to be vulnerable to ReDoS.

    This currently targets ``pygments.lexers.archetype.AdlLexer``. If Pygments
    is not installed or that lexer is not present, this function is a no-op.
    """

    try:
        from pygments.lexer import Lexer  # type: ignore
        from pygments.lexers import archetype
    except Exception:
        # Pygments not installed or import error; nothing to do.
        return

    try:
        original_cls: type[Lexer] = archetype.AdlLexer  # type: ignore[attr-defined]
    except AttributeError:
        # AdlLexer not present in this Pygments build.
        return

    class DisabledAdlLexer(original_cls):  # type: ignore[misc]
        """Stub lexer that fails fast instead of running vulnerable regexes."""

        def get_tokens_unprocessed(self, text: str) -> Any:  # type: ignore[override]
            raise RuntimeError(
                "Pygments AdlLexer has been disabled due to a known ReDoS "
                "vulnerability. This lexer should not be used on untrusted input.",
            )

    # Replace the vulnerable class so any future imports get the safe stub.
    archetype.AdlLexer = DisabledAdlLexer  # type: ignore[assignment]

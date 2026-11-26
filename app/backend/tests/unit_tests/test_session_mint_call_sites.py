"""Guard test: nothing mints a session outside the single gated helper.

``src.services.auth_session.issue_session_for_user`` is the one place that
applies the login gates (organization active -> not suspended -> email verified
-> second factor) before handing out credentials. That is only true for as long
as nothing else calls the primitives it wraps.

This is the guard that would have caught the ``POST /user-otp/verify-email``
hole. That endpoint called ``create_access_token`` +
``create_refresh_token_with_metadata`` + ``set_refresh_cookie`` directly, with
no suspension check, no organization check and no second factor -- so a
suspended user got a working session, and a 2FA-enrolled account was fully
compromised by read access to the user's mailbox. It survived the whole SSO
hardening pass, which rewrote every login path the reviewers *knew about*,
precisely because the set of session-minting call sites was never enumerated.

So it is enumerated here. Any call to one of the primitives that is not inside
``auth_session.py`` and not on ``ALLOWED_MINT_SITES`` fails this test, with the
file:line and what to do about it.
"""

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = BACKEND_ROOT / "src"

# The primitives that, between them, hand a caller a usable session.
MINT_PRIMITIVES = frozenset(
    {
        "create_access_token",
        "create_refresh_token_with_metadata",
        "set_refresh_cookie",
    }
)

# The one module allowed to call them freely: it *is* the gate.
GATE_MODULE = "src/services/auth_session.py"


class MintSite(NamedTuple):
    """One call to a session-minting primitive found in ``src/``."""

    symbol: str
    module: str  # posix path relative to app/backend
    function: str  # enclosing def, or "<module>"
    lineno: int

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.module, self.function, self.symbol)

    @property
    def location(self) -> str:
        return f"{self.module}:{self.lineno}"


# ---------------------------------------------------------------------------
# The reviewed allowlist.
#
# An entry is (module, enclosing function, primitive) -> why this one is safe
# without going through issue_session_for_user. Adding an entry is a security
# decision: it must be a path that either re-applies the gates itself or is
# provably re-issuing credentials that were already gated. If you cannot write
# that sentence honestly, route the endpoint through issue_session_for_user
# instead.
# ---------------------------------------------------------------------------
ALLOWED_MINT_SITES: dict[tuple[str, str, str], str] = {
    (
        "src/api/auth.py",
        "refresh_endpoint",
        "create_access_token",
    ): (
        "POST /auth/refresh re-mints a short-lived access token from a refresh "
        "token that was itself issued through issue_session_for_user. It "
        "re-checks organization-active and suspension inline before minting, "
        "issues no new refresh token and sets no cookie."
    ),
    (
        "src/api/impersonation.py",
        "end_impersonation",
        "create_access_token",
    ): (
        "POST /admin/impersonate/end restores the admin's pre-impersonation "
        "access token. It mints no refresh token and sets no cookie, and it "
        "re-validates super-admin, organization-active and suspension inline. "
        "The second factor was satisfied when that admin originally logged in; "
        "this endpoint cannot present a TOTP challenge, so routing it through "
        "the helper could only refuse every 2FA-enrolled admin or skip the "
        "factor."
    ),
}


def _module_path(path: Path) -> str:
    return path.relative_to(BACKEND_ROOT).as_posix()


def _iter_mint_sites() -> Iterator[MintSite]:
    """Yield every call to a session-minting primitive anywhere under ``src/``."""
    for path in sorted(SRC_ROOT.rglob("*.py")):
        module = _module_path(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        # Map each node to its enclosing function so the allowlist can be keyed
        # on something more stable than a line number.
        enclosing: dict[int, str] = {}

        def walk(node: ast.AST, current: str) -> None:
            for child in ast.iter_child_nodes(node):
                name = current
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    name = child.name
                enclosing[id(child)] = name
                walk(child, name)

        walk(tree, "<module>")

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Matches both `create_access_token(...)` and `mod.create_access_token(...)`.
            symbol = getattr(func, "id", None) or getattr(func, "attr", None)
            if symbol not in MINT_PRIMITIVES:
                continue
            yield MintSite(
                symbol=symbol,
                module=module,
                function=enclosing.get(id(node), "<module>"),
                lineno=node.lineno,
            )


def _unreviewed_sites() -> list[MintSite]:
    return [
        site
        for site in _iter_mint_sites()
        if site.module != GATE_MODULE and site.key not in ALLOWED_MINT_SITES
    ]


def test_no_unreviewed_session_mint_sites() -> None:
    """No code outside the gate may mint a session without a reviewed reason."""
    offenders = _unreviewed_sites()
    if not offenders:
        return

    lines = [
        f"{len(offenders)} unreviewed call(s) to a session-minting primitive "
        f"outside {GATE_MODULE}:",
        "",
    ]
    for site in sorted(offenders, key=lambda s: (s.module, s.lineno)):
        lines.append(f"  {site.location}  {site.function}() -> {site.symbol}()")
    lines += [
        "",
        "Every path that turns 'we know who this user is' into 'here is a",
        "session' must go through:",
        "",
        "    from src.services.auth_session import issue_session_for_user",
        "    grant = await issue_session_for_user(",
        "        session, user=user, organization=organization,",
        "        request=request, response=response, auth_provider='email',",
        "    )",
        "",
        "That helper applies, in order: organization active -> account not",
        "suspended -> email verified (opt-in) -> second factor. Calling the",
        "primitives directly skips ALL of them -- which is exactly how",
        "POST /user-otp/verify-email ended up signing in suspended users and",
        "bypassing 2FA for anyone who could read the target's mailbox.",
        "",
        "If the call site genuinely must not use the helper (it re-issues",
        "already-gated credentials, or it applies the gates itself), add it to",
        "ALLOWED_MINT_SITES in this file with a reason that says why, and get",
        "that reason reviewed. Do not delete or weaken this test.",
        "",
        "Also add any new session-minting ENDPOINT to the list in the module",
        f"docstring of {GATE_MODULE}.",
    ]
    pytest.fail("\n".join(lines), pytrace=False)


def test_allowlist_has_no_stale_entries() -> None:
    """An allowlist entry whose call site is gone must be deleted.

    Keeps ALLOWED_MINT_SITES from decaying into a blanket exemption for files
    that have since been fixed.
    """
    found = {site.key for site in _iter_mint_sites()}
    stale = sorted(key for key in ALLOWED_MINT_SITES if key not in found)
    if not stale:
        return

    lines = [
        "These ALLOWED_MINT_SITES entries no longer match any call in src/.",
        "Delete them so the allowlist keeps shrinking:",
        "",
    ]
    lines += [
        f"  {module}::{function} -> {symbol}" for module, function, symbol in stale
    ]
    pytest.fail("\n".join(lines), pytrace=False)


def test_verify_email_routes_through_the_gate() -> None:
    """Regression pin for the specific hole this guard was written for.

    ``POST /user-otp/verify-email`` minted tokens by hand with no gates at all.
    A regression that reintroduces that is caught by
    ``test_no_unreviewed_session_mint_sites`` above, but pin the positive side
    too so the fix cannot be quietly deleted.
    """
    source = (SRC_ROOT / "api" / "user_otp.py").read_text(encoding="utf-8")
    assert "issue_session_for_user" in source, (
        "src/api/user_otp.py no longer calls issue_session_for_user. "
        "POST /user-otp/verify-email signs a user in and MUST go through the "
        "gate: without it a suspended user gets a working session and a "
        "2FA-enrolled account is compromised by mailbox access alone."
    )


def test_gate_module_documents_every_login_path() -> None:
    """The gate's docstring must name each endpoint that routes through it.

    The enumeration is the point: the SSO hardening pass fixed every path it
    had listed and missed the one it had not.
    """
    import src.services.auth_session as auth_session

    doc = auth_session.__doc__ or ""
    for endpoint in (
        "/auth/login",
        "/auth/verify-2fa",
        "/sso/{provider}/callback",
        "/auth/sso/link",
        "/user-otp/verify-email",
    ):
        assert endpoint in doc, (
            f"{endpoint} routes through issue_session_for_user but is not "
            f"listed in the {GATE_MODULE} module docstring. Keep that list "
            f"complete -- it is what a reviewer checks against."
        )

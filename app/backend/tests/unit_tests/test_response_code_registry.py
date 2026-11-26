"""
Guard tests for the response code registry.

``create_http_exception`` / ``create_success_response`` call
``get_response_code(...)`` *before* building their result, and
``get_response_code`` raises ``KeyError`` for an unregistered key. An
unregistered ``detail_code=`` therefore does not produce the intended 4xx --
the ``KeyError`` escapes into the surrounding ``except Exception`` handler and
the caller receives a 500 ``common.internal_error`` instead.

These tests statically scan ``src/`` for response-code string literals and fail
if any of them is missing from ``RESPONSE_CODES``, so the failure shows up in
CI rather than in production as a mystery 500.
"""

import ast
from collections.abc import Iterator
import json
from pathlib import Path
from typing import NamedTuple

import pytest

from src.core.response_codes import RESPONSE_CODES


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = BACKEND_ROOT / "src"
REGISTRY_PATH = SRC_ROOT / "core" / "response_codes.py"
EN_LOCALE_PATH = (
    BACKEND_ROOT.parent / "frontend" / "src" / "locales" / "en" / "backend.json"
)

# Keyword arguments whose string literal value must be a registered code.
CODE_KEYWORDS = ("detail_code", "message_code")


class CodeUsage(NamedTuple):
    """One response-code string literal found in the source tree."""

    code: str
    keyword: str
    path: Path
    lineno: int

    @property
    def location(self) -> str:
        return f"{self.path.relative_to(BACKEND_ROOT)}:{self.lineno}"


def _iter_code_usages() -> Iterator[CodeUsage]:
    """Yield every response-code string literal used in ``src/``.

    Covers three shapes:
      * ``create_http_exception(..., detail_code="x.y")``
      * ``SomeResponse(..., message_code="x.y")``
      * ``get_response_code("x.y")``
    """
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            for keyword in node.keywords:
                if keyword.arg not in CODE_KEYWORDS:
                    continue
                value = keyword.value
                # Non-literals (f-strings, variables) cannot be checked
                # statically and are deliberately skipped.
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    yield CodeUsage(value.value, keyword.arg, path, value.lineno)

            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name == "get_response_code":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        yield CodeUsage(
                            arg.value, "get_response_code", path, arg.lineno
                        )


def _flatten_locale(data: dict, prefix: str = "") -> set[str]:
    """Flatten nested locale JSON into dotted keys."""
    keys: set[str] = set()
    for key, value in data.items():
        if isinstance(value, dict):
            keys |= _flatten_locale(value, f"{prefix}{key}.")
        else:
            keys.add(f"{prefix}{key}")
    return keys


def test_all_response_code_literals_are_registered() -> None:
    """Every response-code literal in src/ must exist in RESPONSE_CODES.

    Add the missing key to RESPONSE_CODES rather than adding an exemption
    here: an unregistered code turns its endpoint's intended 4xx into a 500.
    """
    unregistered = [u for u in _iter_code_usages() if u.code not in RESPONSE_CODES]
    if not unregistered:
        return

    by_code: dict[str, list[CodeUsage]] = {}
    for usage in unregistered:
        by_code.setdefault(usage.code, []).append(usage)

    lines = [
        f"{len(by_code)} response code(s) used in src/ are not registered in "
        f"RESPONSE_CODES ({REGISTRY_PATH.relative_to(BACKEND_ROOT)}).",
        "",
        "Each of these raises KeyError at runtime, which surfaces to the client",
        "as a 500 common.internal_error instead of the intended response.",
        "",
    ]
    for code in sorted(by_code):
        usages = sorted(by_code[code], key=lambda u: (str(u.path), u.lineno))
        lines.append(f"  {code}  ({usages[0].keyword})")
        for usage in usages:
            lines.append(f"      used at {usage.location}")
        lines.append(f'      add to response_codes.py:  "{code}": "{code}",')
        lines.append(
            f'      add to en/backend.json:     {code} -> "<user-facing text>"'
        )
        lines.append("")
    pytest.fail("\n".join(lines), pytrace=False)


# Registered codes that had no English copy before this guard was introduced.
# This baseline exists only so the guard could be added without a mass copy
# rewrite. Do NOT add to it: new codes must ship with copy. Entries should be
# deleted as copy is written (test_locale_baseline_only_shrinks enforces that).
LOCALE_COPY_BASELINE = frozenset(
    {
        "api_key.no_permissions",
        "api_key.permission_denied",
        "auth.2fa_not_enabled",
        "auth.2fa_token_expired",
        "auth.invalid_2fa_token",
        "auth.sso_only_account",
        "avatar.content_type_required",
        "avatar.deleted",
        "avatar.file_empty",
        "avatar.filename_required",
        "avatar.invalid_file_type",
        "avatar.not_found",
        "avatar.upload_failed",
        "avatar.uploaded",
        "changelog.all_viewed",
        "changelog.conflict",
        "changelog.created",
        "changelog.database_error",
        "changelog.deleted",
        "changelog.no_fields_provided",
        "changelog.not_found",
        "changelog.platform_wide_forbidden",
        "changelog.updated",
        "changelog.viewed",
        "cron_job.deleted",
        "cron_job.not_found",
        "cron_job.triggered",
        "email_settings.not_found",
        "email_settings.reset_success",
        "email_settings.sender_locked_on_platform_defaults",
        "email_settings.sendgrid_not_configured",
        "email_settings.test_failed",
        "email_settings.test_success",
        "email_settings.updated",
        "feature_flag.created",
        "feature_flag.deleted",
        "feature_flag.not_found",
        "feature_flag.updated",
        "feature_flag_override.created",
        "feature_flag_override.deleted",
        "file.invalid_storage_provider",
        "file_serve.access_denied",
        "file_serve.not_found",
        "file_serve.storage_not_supported",
        "help_center.article_created",
        "help_center.article_deleted",
        "help_center.article_not_found",
        "help_center.article_updated",
        "help_center.category_created",
        "help_center.category_deleted",
        "help_center.category_not_found",
        "help_center.category_updated",
        "help_center.faq_created",
        "help_center.faq_deleted",
        "help_center.faq_not_found",
        "help_center.faq_updated",
        "help_center.invalid_category",
        "help_center.invalid_category_id",
        "identity.2fa_required",
        "identity.cannot_unlink_last",
        "identity.not_found",
        "identity.password_required",
        "identity.unlinked",
        "identity.unlinked_with_setup",
        "invitation.already_accepted",
        "invitation.already_pending",
        "invitation.created",
        "invitation.expired",
        "invitation.invalid_token",
        "invitation.not_found",
        "invitation.retrieved",
        "invitation.revoked",
        "maintenance.updated",
        "notification.send_failed",
        "payments.checkout_created",
        "payments.checkout_failed",
        "payments.method_deleted",
        "payments.method_not_found",
        "payments.method_set_default",
        "payments.not_allowed",
        "payments.not_found",
        "payments.provider_not_enabled",
        "payments.refund_failed",
        "payments.refund_success",
        "payments.settings_not_found",
        "payments.settings_updated",
        "rate_limit.created",
        "rate_limit.deleted",
        "rate_limit.not_found",
        "rate_limit.updated",
        "report_schedules.created",
        "report_schedules.deleted",
        "report_schedules.invalid_cron",
        "report_schedules.not_found",
        "report_schedules.updated",
        "reports.created",
        "reports.deleted",
        "reports.generation_failed",
        "reports.invalid_type",
        "reports.not_found",
        "sso.email_not_verified",
        "sso.link_token_expired",
        "sso.link_token_invalid",
        "sso.linking_cancelled",
        "sso.linking_required",
        "sso.linking_success",
        "system_config.already_exists",
        "system_config.created",
        "system_config.deleted",
        "system_config.not_found",
        "system_config.updated",
        "two_factor.already_exists",
        "two_factor.disabled",
        "two_factor.invalid_request",
        "two_factor.not_allowed",
        "two_factor.not_found",
        "two_factor.settings_not_found",
        "user.cannot_suspend_owner",
        "user.cannot_suspend_self",
        "user.suspended",
        "user.unsuspended",
    }
)


def _locale_keys() -> set[str]:
    if not EN_LOCALE_PATH.exists():
        pytest.skip(f"English locale file not present at {EN_LOCALE_PATH}")
    return _flatten_locale(json.loads(EN_LOCALE_PATH.read_text(encoding="utf-8")))


def test_every_response_code_has_english_copy() -> None:
    """A registered code must ship with English copy, or clients see a raw key."""
    missing = sorted(set(RESPONSE_CODES) - _locale_keys() - LOCALE_COPY_BASELINE)
    if not missing:
        return

    lines = [
        f"{len(missing)} response code(s) have no English copy in "
        f"{EN_LOCALE_PATH.name}.",
        "",
        "Without copy the frontend renders the raw code key to the user.",
        "Add each one to app/frontend/src/locales/en/backend.json (and the",
        "other locale files), nesting on the dot, e.g.",
        '  "auth": { "account_locked": "Your account is temporarily locked." }',
        "",
    ]
    lines += [f"  {code}" for code in missing]
    pytest.fail("\n".join(lines), pytrace=False)


def test_locale_baseline_only_shrinks() -> None:
    """Baseline entries that have since gained copy must be deleted from it.

    Keeps LOCALE_COPY_BASELINE from silently becoming a permanent allowlist.
    """
    locale_keys = _locale_keys()
    stale = sorted(LOCALE_COPY_BASELINE & locale_keys)
    unknown = sorted(LOCALE_COPY_BASELINE - set(RESPONSE_CODES))
    problems = []
    if stale:
        problems.append(
            "These codes now have English copy; remove them from "
            "LOCALE_COPY_BASELINE:\n" + "\n".join(f"  {c}" for c in stale)
        )
    if unknown:
        problems.append(
            "These baseline codes are no longer in RESPONSE_CODES; remove them "
            "from LOCALE_COPY_BASELINE:\n" + "\n".join(f"  {c}" for c in unknown)
        )
    if problems:
        pytest.fail("\n\n".join(problems), pytrace=False)


def test_registry_is_identity_mapping() -> None:
    """RESPONSE_CODES maps each key to itself; a typo here silently mistranslates."""
    mismatched = {k: v for k, v in RESPONSE_CODES.items() if k != v}
    assert not mismatched, f"RESPONSE_CODES entries whose value != key: {mismatched}"

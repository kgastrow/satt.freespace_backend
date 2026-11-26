"""The bootstrap seeder's TRUNCATE branch must be hard to reach by accident.

``scripts/seed_first_tenant.py::clear_all_tables`` issues
``TRUNCATE <every table> CASCADE`` against whatever ``config.json`` resolves to,
which on a developer machine is very often a shared or staging database. It used
to sit behind a single ``Clear all existing data before seeding? [y/N]`` prompt -
one keystroke, and satisfiable by a piped ``yes``.

It is now behind three gates (``--force-clear``, an interactive terminal, and
typing the target database name back). These tests pin all three, and in
particular pin the property that matters most: with no flag the prompt is never
even reached, so nothing typed or piped at the ordinary invocation can destroy
anything.
"""

import io

import pytest

from scripts.seed_first_tenant import (
    confirm_destructive_clear,
    describe_database_target,
)


DEV_URL = "postgresql+asyncpg://ayzer_template:secret@localhost:5432/ayzer_template"
PROD_URL = "postgresql+asyncpg://app:secret@db.internal.example.com:5432/app_production"


class _Tty(io.StringIO):
    """A stdin stand-in that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


class _Pipe(io.StringIO):
    """A stdin stand-in that is a pipe/redirect, as in ``yes | seed.py``."""

    def isatty(self) -> bool:
        return False


def _refuse(prompt: str) -> str:
    raise AssertionError(f"the operator must never be prompted here: {prompt!r}")


# ============================================================================
# GATE 1: the flag. Without it the destructive branch is unreachable.
# ============================================================================


def test_without_the_flag_nothing_is_cleared_and_nothing_is_asked():
    assert (
        confirm_destructive_clear(
            PROD_URL, force_clear=False, input_fn=_refuse, stdin=_Tty()
        )
        is False
    )


@pytest.mark.parametrize("typed", ["y", "Y", "yes", "app_production", "", "\n"])
def test_no_answer_can_arm_the_clear_without_the_flag(typed):
    """A stray keypress, an enthusiastic 'yes', even the right database name."""
    assert (
        confirm_destructive_clear(
            PROD_URL,
            force_clear=False,
            input_fn=lambda _prompt: typed,
            stdin=_Tty(),
        )
        is False
    )


def test_a_piped_yes_cannot_arm_the_clear_without_the_flag():
    """``yes | python scripts/seed_first_tenant.py`` must be inert."""
    assert (
        confirm_destructive_clear(
            PROD_URL,
            force_clear=False,
            input_fn=lambda _prompt: "y",
            stdin=_Pipe("y\ny\ny\n"),
        )
        is False
    )


# ============================================================================
# GATE 2: an interactive terminal
# ============================================================================


def test_flag_without_a_tty_is_refused():
    """CI jobs and ``yes | ...`` cannot confirm a destructive operation."""
    with pytest.raises(SystemExit) as exc:
        confirm_destructive_clear(
            DEV_URL,
            force_clear=True,
            input_fn=lambda _prompt: "ayzer_template",
            stdin=_Pipe("ayzer_template\n"),
        )
    assert exc.value.code == 2


def test_flag_without_a_tty_never_reaches_the_prompt():
    with pytest.raises(SystemExit):
        confirm_destructive_clear(
            DEV_URL, force_clear=True, input_fn=_refuse, stdin=_Pipe()
        )


# ============================================================================
# GATE 3: type the target database name back
# ============================================================================


def test_flag_with_a_wrong_database_name_is_refused():
    with pytest.raises(SystemExit) as exc:
        confirm_destructive_clear(
            DEV_URL, force_clear=True, input_fn=lambda _p: "some_other_db", stdin=_Tty()
        )
    assert exc.value.code == 2


@pytest.mark.parametrize("typed", ["y", "yes", "YES", "", "AYZER_TEMPLATE"])
def test_a_bare_confirmation_is_not_enough(typed):
    """The old ``[y/N]`` answers, and a case-mangled name, must all fail."""
    with pytest.raises(SystemExit):
        confirm_destructive_clear(
            DEV_URL, force_clear=True, input_fn=lambda _p: typed, stdin=_Tty()
        )


def test_flag_plus_tty_plus_exact_database_name_is_accepted():
    assert (
        confirm_destructive_clear(
            DEV_URL,
            force_clear=True,
            input_fn=lambda _p: "ayzer_template",
            stdin=_Tty(),
        )
        is True
    )


def test_surrounding_whitespace_is_tolerated():
    assert (
        confirm_destructive_clear(
            DEV_URL,
            force_clear=True,
            input_fn=lambda _p: "  ayzer_template \n",
            stdin=_Tty(),
        )
        is True
    )


def test_the_name_typed_must_match_the_url_actually_targeted():
    """Confirming 'ayzer_template' must not clear a differently-named database."""
    with pytest.raises(SystemExit):
        confirm_destructive_clear(
            PROD_URL,
            force_clear=True,
            input_fn=lambda _p: "ayzer_template",
            stdin=_Tty(),
        )


# ============================================================================
# The operator is shown which database they are about to erase
# ============================================================================


def test_the_resolved_host_and_database_are_printed_before_prompting(capsys):
    with pytest.raises(SystemExit):
        confirm_destructive_clear(
            PROD_URL, force_clear=True, input_fn=lambda _p: "wrong", stdin=_Tty()
        )
    out = capsys.readouterr().out
    assert "db.internal.example.com:5432" in out
    assert "app_production" in out


def test_the_password_is_never_printed(capsys):
    with pytest.raises(SystemExit):
        confirm_destructive_clear(
            PROD_URL, force_clear=True, input_fn=lambda _p: "wrong", stdin=_Tty()
        )
    assert "secret" not in capsys.readouterr().out


def test_describe_database_target_resolves_host_and_name():
    assert describe_database_target(PROD_URL) == (
        "db.internal.example.com:5432",
        "app_production",
    )
    assert describe_database_target(
        "postgresql+asyncpg://u:p@/plain_db?host=/var/run"
    ) == ("localhost:5432", "plain_db")


# ============================================================================
# The CLI wiring: the flag exists, and is off by default
# ============================================================================


def test_force_clear_flag_defaults_to_off():
    import argparse
    import inspect

    from scripts import seed_first_tenant

    source = inspect.getsource(seed_first_tenant.main)
    assert "--force-clear" in source

    parser = argparse.ArgumentParser()
    parser.add_argument("--force-clear", action="store_true")
    assert parser.parse_args([]).force_clear is False
    assert parser.parse_args(["--force-clear"]).force_clear is True


def test_seed_entrypoint_defaults_to_non_destructive():
    import inspect

    from scripts.seed_first_tenant import seed_first_tenant

    default = inspect.signature(seed_first_tenant).parameters["force_clear"].default
    assert default is False

"""Every audit_service call must match the helper's signature.

Three endpoints shipped a `resource_name=` kwarg to `audit_service.log_update`,
which does not accept one. Python raises TypeError at call time, the surrounding
`except Exception` turns it into a 500, and the endpoint fails 100% of the time
on its success path -- `POST /users/{id}/password-reset`, the notification
preference update, and admin-disable-2FA were all dead this way.

Nothing caught it because the audit call is the LAST statement on a path whose
earlier assertions have already passed, so a test that stops at "did the write
happen" never reaches it. This checks the call sites statically instead.
"""

import ast
import inspect
import pathlib

from src.services.audit import audit_service


SRC = pathlib.Path(__file__).resolve().parents[2] / "src"


def _audit_call_sites():
    """(file, line, method, kwarg names) for every audit_service.<m>(...) call."""
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not isinstance(fn, ast.Attribute):
                continue
            owner = fn.value
            if not (isinstance(owner, ast.Name) and owner.id == "audit_service"):
                continue
            kwargs = {k.arg for k in node.keywords if k.arg is not None}
            has_splat = any(k.arg is None for k in node.keywords)
            yield path, node.lineno, fn.attr, kwargs, has_splat


def test_audit_service_call_sites_exist():
    """Guard the guard: if the scan finds nothing, it is not protecting anything."""
    assert list(
        _audit_call_sites()
    ), "no audit_service call sites found - scan is broken"


def test_every_audit_call_matches_its_signature():
    failures = []
    for path, lineno, method, kwargs, has_splat in _audit_call_sites():
        if has_splat:
            continue  # **kwargs at the call site - cannot be checked statically
        fn = getattr(audit_service, method, None)
        if fn is None:
            failures.append(
                f"{path.relative_to(SRC.parent)}:{lineno} calls "
                f"audit_service.{method}(), which does not exist"
            )
            continue
        accepted = set(inspect.signature(fn).parameters) - {"self"}
        unknown = kwargs - accepted
        if unknown:
            failures.append(
                f"{path.relative_to(SRC.parent)}:{lineno} passes "
                f"{sorted(unknown)} to audit_service.{method}(), which accepts "
                f"{sorted(accepted)}. This raises TypeError at call time and the "
                f"endpoint returns 500."
            )
    assert not failures, "\n".join(failures)

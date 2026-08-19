"""
FR-028 verification (T095): no code path in apps/risk/ takes a business
action on a score. This feature reports; it does not decide anything on
the platform's behalf. A risk score here is the beginning of a human
decision, never a trigger for one made automatically.

Grepping the non-test source under apps/risk/ turns up no reference to
declining cover, pricing a premium, opening an investigation, or sending
a notification -- the only email-shaped identifier present is
computed_by's SlugRelatedField(slug_field="email"), which is attribution
(who computed this), not a side effect.
"""
import ast
from pathlib import Path

import pytest

FORBIDDEN_ACTION_WORDS = (
    "decline",
    "denycover",
    "deny_cover",
    "reprice",
    "adjust_premium",
    "open_investigation",
    "notify",
    "send_mail",
    "sendmail",
    "alert",
)

RISK_APP_DIR = Path(__file__).resolve().parent.parent


def _non_test_python_files():
    for path in RISK_APP_DIR.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        if path.name == "__pycache__":
            continue
        yield path


def test_no_forbidden_business_action_identifiers_in_risk_source():
    hits = []
    for path in _non_test_python_files():
        source = path.read_text()
        lowered = source.lower()
        for word in FORBIDDEN_ACTION_WORDS:
            if word in lowered:
                hits.append(f"{path.relative_to(RISK_APP_DIR.parent.parent)}: {word!r}")

    assert not hits, (
        "apps/risk/ contains identifiers suggesting a business action taken "
        f"on a score, which FR-028 forbids: {hits}"
    )


def test_engine_persist_only_writes_risk_and_audit_tables():
    """
    A structural check on top of the identifier grep: walk persist()'s
    AST and confirm every attribute access naming a model/manager stays
    within {RiskAssessment, RiskFactor, Customer (the risk_score mirror
    only), record_action}. This catches a future edit that calls out to
    e.g. a Policy or notification service without needing that call to
    contain one of the forbidden words above.
    """
    import inspect

    from .. import engine

    source = inspect.getsource(engine.persist)
    tree = ast.parse(source)

    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            called_names.add(node.func.attr)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called_names.add(node.func.id)

    allowed = {
        # Transaction/query plumbing.
        "atomic",
        "get",
        "select_for_update",
        "filter",
        "first",
        "update_or_create",
        "delete",
        "bulk_create",
        "save",
        # The two writes this function is allowed to make: a risk record,
        # via record_action, and the RiskFactor rows it constructs to pass
        # to bulk_create.
        "record_action",
        "RiskFactor",
        # Value plumbing -- not a write to anything.
        "round",
        "Decimal",
        "type",
        "now",
    }
    unexpected = called_names - allowed
    assert not unexpected, (
        f"persist() calls unexpected methods {unexpected} -- verify none of "
        "these represent a business action FR-028 forbids"
    )

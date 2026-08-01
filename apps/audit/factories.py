import factory
from factory.django import DjangoModelFactory

from apps.accounts.factories import UserFactory

from .models import AuditLog


class AuditLogFactory(DjangoModelFactory):
    class Meta:
        model = AuditLog

    actor = factory.SubFactory(UserFactory)
    actor_identifier = factory.LazyAttribute(lambda o: o.actor.email if o.actor else "")
    actor_role = factory.LazyAttribute(lambda o: o.actor.role if o.actor else "")
    action = "user.created"
    target_type = "accounts.User"
    target_id = factory.Sequence(lambda n: str(n))
    outcome = AuditLog.Outcome.SUCCEEDED
    before = None
    after = None
    context = None

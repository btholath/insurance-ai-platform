"""
Backward-compatible alias for `loaddataset`.

This command was Phase 2a's customer loader. As of Phase 2b it also loads
each row's policy, so the name is no longer accurate and `loaddataset` is
the real command. The alias is kept because the Phase 2a quickstart,
README, and operator habits all reference it, and breaking a documented
command to save one subclass would be a poor trade.

Behaviour is identical to `loaddataset` -- including creating policies.
An operator running the old name gets the Phase 2b result, which is the
intended outcome: customers without their policies is not a state this
platform wants to be in.
"""
from .loaddataset import Command as LoadDatasetCommand


class Command(LoadDatasetCommand):
    help = "Deprecated alias for loaddataset. Loads customers and their policies."

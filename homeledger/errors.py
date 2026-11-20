"""Exceptions shared across HomeLedger."""


class UserError(Exception):
    """A problem the person can fix (bad input). The message is shown on screen as-is."""


class CorruptDatabase(Exception):
    """The data file failed its integrity check."""

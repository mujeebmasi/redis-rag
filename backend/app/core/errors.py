"""
User-Facing Errors
==================
Errors whose message is safe to send to the browser.

Rule of the API:
- UserFacingError → its message is shown to the user as-is.
- Anything else  → the details are logged on the server, and the user
                   only sees a generic message.

This stops internal details (URLs, hostnames, API keys inside URLs,
stack traces) from leaking out through error messages.
"""


class UserFacingError(Exception):
    """An error with a message written for the end user."""

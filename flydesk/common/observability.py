"""
Sentry wiring with **PII scrubbing** (interview Q34).

In travel, error payloads can carry passenger names, documents, contact details.
We scrub those keys before anything leaves the process. Sentry is off unless
`SENTRY_DSN` is set, so dev/test never phone home.
"""

import logging

logger = logging.getLogger("flydesk")

# Keys whose values must never leave the app (passenger PII + provider echoes).
_PII_KEYS = frozenset(
    {
        "given_name",
        "family_name",
        "firstName",
        "lastName",
        "name",
        "email",
        "emailAddress",
        "phone_number",
        "phones",
        "born_on",
        "dateOfBirth",
        "documents",
        "passengers",
        "travelers",
    }
)
_REDACTED = "[scrubbed]"


def scrub_pii(obj):
    if isinstance(obj, dict):
        return {k: (_REDACTED if k in _PII_KEYS else scrub_pii(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_pii(v) for v in obj]
    return obj


def before_send_scrub(event, _hint):
    """Sentry before_send hook: recursively redact PII from the event."""
    return scrub_pii(event)


def init_sentry(dsn: str, environment: str) -> None:
    if not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=0.1,
        send_default_pii=False,
        before_send=before_send_scrub,
    )
    logger.info("sentry_initialised environment=%s", environment)

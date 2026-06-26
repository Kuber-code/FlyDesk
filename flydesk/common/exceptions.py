"""
Domain exceptions + a DRF exception handler that renders them as clean JSON.

Each domain error carries an HTTP status and a stable machine-readable `code`,
so the API contract stays explicit instead of leaking 500s for expected cases
(expired offer, unknown booking, upstream provider down).
"""

import logging

from pydantic import ValidationError as PydanticValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

logger = logging.getLogger("flydesk")


class FlyDeskError(Exception):
    """Base class for expected domain errors."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str | None = None):
        self.message = message or (self.__doc__ or "Internal error").strip()
        super().__init__(self.message)


class ProviderError(FlyDeskError):
    """The upstream flight provider returned an error."""

    status_code = 502
    code = "provider_error"


class ProviderTimeoutError(ProviderError):
    """The upstream flight provider timed out."""

    status_code = 504
    code = "provider_timeout"


class OfferNotFoundError(FlyDeskError):
    """The requested offer does not exist."""

    status_code = 404
    code = "offer_not_found"


class OfferExpiredError(FlyDeskError):
    """The offer is no longer valid; search again before booking."""

    status_code = 409
    code = "offer_expired"


class BookingNotFoundError(FlyDeskError):
    """No booking exists with that id."""

    status_code = 404
    code = "booking_not_found"


def drf_exception_handler(exc, context):
    """Map domain + Pydantic errors to clean JSON; defer everything else to DRF."""
    if isinstance(exc, FlyDeskError):
        logger.warning("domain_error code=%s message=%s", exc.code, exc.message)
        return Response(
            {"error": {"code": exc.code, "message": exc.message}},
            status=exc.status_code,
        )
    if isinstance(exc, PydanticValidationError):
        # Domain-invariant failures (e.g. return_date < departure_date, bad IATA)
        # are client errors, not 500s.
        return Response(
            {
                "error": {
                    "code": "validation_error",
                    "message": "request failed domain validation",
                    # include_context=False drops the raw ValueError (not JSON-safe)
                    "details": exc.errors(
                        include_url=False, include_input=False, include_context=False
                    ),
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return drf_default_handler(exc, context)

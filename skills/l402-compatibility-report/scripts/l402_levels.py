"""The shared vocabulary of the compatibility report: the six classifications,
the finding type, the server-fix table, and the JSON report's version.

``l402_analyze`` (read-only check), ``l402_evidence`` (paid check), and
``l402_report`` (rendering) all import from here, so the paid check never
imports the analyzer. The six names match references/l402-verification-levels.md
exactly; a test pins them to it.

The JSON report is the contract for anything that reads a report (a readiness
gate reads JSON, never the Markdown). ``REPORT_VERSION`` changes only when a
field a reader relies on changes meaning or disappears.
"""
from __future__ import annotations

from dataclasses import dataclass

REPORT_VERSION = 1

CHALLENGE_COMPATIBLE = "CHALLENGE_COMPATIBLE"
PAYMENT_COMPATIBLE = "PAYMENT_COMPATIBLE"
FULFILLMENT_VERIFIED = "FULFILLMENT_VERIFIED"
MARKETPLACE_READY = "MARKETPLACE_READY"
INCOMPATIBLE = "INCOMPATIBLE"
INCONCLUSIVE = "INCONCLUSIVE"
CLASSIFICATIONS = (
    CHALLENGE_COMPATIBLE,
    PAYMENT_COMPATIBLE,
    FULFILLMENT_VERIFIED,
    MARKETPLACE_READY,
    INCOMPATIBLE,
    INCONCLUSIVE,
)

# Statuses that say "not now" rather than "never": the check can't decide.
TRANSIENT_STATUSES = (408, 425, 429)

FIXES = {
    "unpaid_2xx": "Place the L402 middleware before resource delivery, so an unpaid request gets 402.",
    "unpaid_401": "Let requests reach the L402 check before ordinary authentication where paid access is intended.",
    "validation_before_challenge": "Issue the 402 before validating paid-only parameters, or provide a probe-safe route.",
    "unsupported_media_before_challenge": (
        "Issue the 402 before content-type or body validation, or provide a fixed-price, "
        "single-call route for marketplace listing."
    ),
    "unexpected_status": "Return 402 Payment Required with an L402 challenge for an unpaid request.",
    "missing_www_authenticate": 'Emit the canonical challenge header: WWW-Authenticate: L402 macaroon="...", invoice="...".',
    "malformed_challenge": (
        "Quote auth-param values as RFC 7235 quoted-strings, escape quotes and backslashes, "
        "and separate parameters with commas."
    ),
    "duplicate_params": "Send each auth-param once per challenge.",
    "no_l402_challenge": "Add an L402 challenge beside the other schemes; Payment and x402 are separate schemes.",
    "missing_token": "Include both required challenge components: the macaroon and the invoice.",
    "missing_invoice": "Include both required challenge components: the macaroon and the invoice.",
    "invalid_invoice": "Return a valid BOLT11 invoice in the invoice parameter.",
    "amountless_invoice": "Use a priced invoice; marketplaces and bounded wallets refuse amountless invoices.",
    "expired_invoice": "Increase the invoice expiry to a safe quote window.",
    "short_lived_invoice": "Increase the invoice expiry to a safe quote window.",
    "non_mainnet_invoice": "Use a mainnet invoice for a public listing.",
    "body_price_mismatch": "Make the invoice authoritative and correct the price the body declares.",
    "payment_hash_unbound": "Bind the macaroon to the invoice: its identifier must carry the invoice payment hash.",
    "redirect_into_blocked_range": "Serve the paid resource from a public address; never redirect into a private range.",
    "redirect_downgrade": "Never redirect from https to http; keep the paid resource on https.",
    "redirect_not_https": "Serve the resource over https; public endpoints must use https.",
    "multiple_l402_challenges": "Send one L402 challenge per response.",
    "redirect_refused": "Redirect only to a public https URL without credentials, or serve the 402 from the listed URL.",
    "redirect_body_not_resent": "Serve the 402 at the listed URL rather than redirecting a request with a body to another origin.",
    "redirect_limit": "Remove the redirect loop and serve the 402 from a stable URL.",
    "unpaid_body_secret": "Remove the credential from the response body and rotate it.",
    "no_host_root_metadata": "Publish openapi.json or llms.txt at the host root; Amazap's prefill reads only those.",
    "slow_challenge": "Return the 402 within 8 seconds; Amazap's listing probe waits 8 seconds.",
    "preimage_mismatch": "Validate the preimage encoding and SHA-256 it against the invoice payment hash.",
    "paid_retry_402": (
        "Inspect authorization serialization and token/resource binding: the paid retry got another 402."
    ),
    "paid_retry_rejected": (
        "Inspect authorization serialization and token/resource binding: the paid retry was rejected."
    ),
    "ambiguous_fulfillment": (
        "Preserve the payment hash and add deterministic claim or status recovery; never blindly repay."
    ),
}


@dataclass
class Finding:
    code: str
    severity: str  # error, warning, info
    section: str  # transport, challenge, invoice, binding, marketplace, security, paid
    message: str

    @property
    def fix(self) -> str | None:
        return FIXES.get(self.code)

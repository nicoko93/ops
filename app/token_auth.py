"""Bearer token authentication using Google ID tokens (OIDC).

Validates JWT tokens issued by Google, checking signature, issuer,
and hosted domain (hd) claim. Same pattern as another-service validation.
"""

import functools
from flask import request, jsonify, current_app
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Reusable transport for JWKS fetching (connection pooling)
_transport = google_requests.Request()


def verify_google_token(token: str) -> dict | None:
    """Validate a Google ID token and return claims, or None on failure."""
    try:
        claims = id_token.verify_token(token, _transport)
    except Exception:
        return None

    # Check issuer
    if claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
        return None

    # Check hosted domain
    allowed_domain = current_app.config.get("GOOGLE_ALLOWED_DOMAIN")
    if allowed_domain:
        domains = [d.strip().lower() for d in str(allowed_domain).split(",") if d.strip()]
        if domains and claims.get("hd", "").lower() not in domains:
            return None

    return claims


def require_bearer_token(f):
    """Decorator that requires a valid Google Bearer token."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing Bearer token"}), 401
        token = auth[7:]
        claims = verify_google_token(token)
        if claims is None:
            return jsonify({"error": "Invalid or expired token"}), 401
        return f(*args, **kwargs)
    return wrapped

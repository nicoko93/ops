# app/auth.py
from functools import wraps
from flask import current_app, session, redirect, url_for, request
from authlib.integrations.flask_client import OAuth

# Shared OAuth instance
oauth = OAuth()

def init_oauth(app):
    """Registers the Google provider (OIDC)."""
    oauth.init_app(app)
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=app.config.get("GOOGLE_CLIENT_ID"),
        client_secret=app.config.get("GOOGLE_CLIENT_SECRET"),
        client_kwargs={"scope": "openid email profile"},
    )

def domain_allowed(email: str) -> bool:
    """
    If GOOGLE_ALLOWED_DOMAIN is empty -> allow all.
    Otherwise, allow only if the email domain is in the list (comma-separated).
    """
    allowed = current_app.config.get("GOOGLE_ALLOWED_DOMAIN")
    if not allowed:
        return True
    domains = [d.strip().lower() for d in str(allowed).split(",") if d.strip()]
    domain = email.split("@")[-1].lower()
    return domain in domains

def login_required(view):
    """Redirect to /login if the user is not authenticated."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            session["next"] = request.url
            return redirect(url_for("ui.login"))  # endpoint of the ui blueprint
        return view(*args, **kwargs)
    return wrapped

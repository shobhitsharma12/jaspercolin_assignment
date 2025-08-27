from typing import Optional, Set
import os
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from jwt import decode as jwt_decode, InvalidTokenError, PyJWKClient

# ------------------------------------------------------------------------------
# Configuration (set via env or hardcode for testing)
# ------------------------------------------------------------------------------
KEYCLOAK_BASE_URL = os.getenv("KEYCLOAK_BASE_URL", "https://keycloak.example.com")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "myrealm")
CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "my-client-id")

ISSUER = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}"
JWKS_URL = f"{ISSUER}/protocol/openid-connect/certs"

# ------------------------------------------------------------------------------
# App & JWKS client
# ------------------------------------------------------------------------------
app = FastAPI(title="Keycloak JWT + RBAC Demo")
jwk_client = PyJWKClient(JWKS_URL)

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    """Extracts 'Bearer <token>' from the Authorization header."""
    if not authorization_header:
        return None
    parts = authorization_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None

def verify_keycloak_jwt(token: str) -> dict:
    """
    Verifies the JWT against Keycloak JWKS:
    - Signature (RS256)
    - Exp (expiration)
    - Issuer
    - Audience (client id)
    Returns decoded claims if valid; raises InvalidTokenError otherwise.
    """
    signing_key = jwk_client.get_signing_key_from_jwt(token).key
    claims = jwt_decode(
        token,
        signing_key,
        algorithms=["RS256"],
        audience=CLIENT_ID,   # validate aud
        issuer=ISSUER,        # validate iss
        options={"require": ["exp", "iat", "iss", "aud"]},
    )
    return claims

def has_admin_role(claims: dict) -> bool:
    """
    Checks Keycloak realm role 'admin' in realm_access.roles.
    Example payload snippet:
    "realm_access": { "roles": ["admin", "user"] }
    """
    roles: Set[str] = set(
        (claims.get("realm_access") or {}).get("roles") or []
    )
    return "admin" in roles

# ------------------------------------------------------------------------------
# Middleware for RBAC enforcement on selected paths
# ------------------------------------------------------------------------------
class AdminRoleMiddleware(BaseHTTPMiddleware):
    """
    Enforces that requests to the protected paths include a valid JWT with the
    'admin' role in realm_access.roles.
    """
    def __init__(self, app, protected_paths: Set[str]):
        super().__init__(app)
        self.protected_paths = protected_paths

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.protected_paths:
            # 1) Extract token
            token = extract_bearer_token(request.headers.get("Authorization"))
            if not token:
                return PlainTextResponse(
                    "Forbidden: missing bearer token", status_code=status.HTTP_403_FORBIDDEN
                )

            # 2) Verify token
            try:
                claims = verify_keycloak_jwt(token)
            except InvalidTokenError:
                return PlainTextResponse(
                    "Forbidden: invalid token", status_code=status.HTTP_403_FORBIDDEN
                )

            # 3) Check admin role
            if not has_admin_role(claims):
                return PlainTextResponse(
                    "Forbidden: admin role required", status_code=status.HTTP_403_FORBIDDEN
                )

            # Optionally expose claims to downstream handlers
            request.state.token_claims = claims

        return await call_next(request)

# Protect exactly this endpoint with admin-only middleware
app.add_middleware(AdminRoleMiddleware, protected_paths={"/rbac-secure"})

# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------

@app.get("/validate", response_class=PlainTextResponse)
async def validate_endpoint(request: Request):
    """
    Returns "Access Granted" if the Keycloak JWT is valid, else "Access Denied".
    """
    token = extract_bearer_token(request.headers.get("Authorization"))
    if not token:
        return PlainTextResponse("Access Denied", status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        _ = verify_keycloak_jwt(token)
        return PlainTextResponse("Access Granted")
    except InvalidTokenError:
        return PlainTextResponse("Access Denied", status_code=status.HTTP_401_UNAUTHORIZED)

@app.get("/rbac-secure", response_class=PlainTextResponse)
async def rbac_secure(request: Request):
    """
    Admin-only endpoint enforced by the AdminRoleMiddleware.
    If the middleware passes, the user has a valid token and 'admin' role.
    """
    return PlainTextResponse("Welcome, admin! 🎉")

# Optional: a public ping
@app.get("/ping", response_class=PlainTextResponse)
async def ping():
    return PlainTextResponse("pong")

# ------------------------------------------------------------------------------
# Run (dev): uvicorn main:app --reload
# ------------------------------------------------------------------------------


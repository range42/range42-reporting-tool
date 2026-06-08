"""Token verification boundaries (shape reservation — no impl yet).

Two distinct token families exist, with different trust models:

1. **App JWT (outbound, ours).** Signed HS256 with ``JWT_SECRET``. We mint these
   for our own sessions and we are the *sole* verifier — the same symmetric
   secret signs and verifies, so it must never leave the backend. No key
   rotation/JWKS infrastructure is needed for these in v1.

2. **OIDC provider tokens (inbound, theirs).** Issued by the external identity
   provider during login. These are validated against the **provider's** JWKS
   (asymmetric: the provider holds the private key, we fetch its public keys
   from the JWKS endpoint advertised at ``OIDC_ISSUER_URL``). We never hold an
   asymmetric private key — there is no asymmetric key management on our side
   for v1.

Implementations (mint/verify app JWTs, JWKS fetch + cache + verify) land in WP2.
"""

# HS256: the only algorithm we use to sign/verify our own app JWTs.
APP_JWT_ALGORITHM = "HS256"

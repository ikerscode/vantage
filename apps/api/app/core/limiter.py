from slowapi import Limiter
from slowapi.util import get_remote_address

# BRIEF v2: closes SECURITY_FIXES_REPORT.md's one explicitly-flagged
# remaining gap ("Rate limiting (SlowAPI) — Not done... follow-up for
# whoever exposes this beyond a single workstation").
#
# Keyed by remote address like any slowapi deployment, but worth being
# honest about what that means here: every real deployment of this app
# binds every port to 127.0.0.1 (SEC-03) or, for the packaged desktop app,
# routes through a single container-runtime NAT path — so in practice
# every request shares one effective source address, and this limiter
# behaves as a global cap rather than a per-attacker one. That's still
# real value, not theater: it bounds how fast a compromised/runaway local
# process (a buggy frontend build, a compromised sibling container) can
# hammer the dev-token endpoint or spawn expensive Celery jobs via
# /api/analyses, which the loopback binding alone doesn't limit.
limiter = Limiter(key_func=get_remote_address)

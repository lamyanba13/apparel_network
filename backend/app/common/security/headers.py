from app.common.enums import Environment


def build_security_headers(environment: Environment) -> dict[str, str]:
    """Build the baseline browser security headers for one environment."""
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        ),
    }
    if environment is Environment.PRODUCTION:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers

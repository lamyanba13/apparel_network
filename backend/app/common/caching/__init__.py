"""Provider-neutral HTTP conditional-request helpers."""

from app.common.caching.etags import generate_etag, if_none_match_matches

__all__ = ["generate_etag", "if_none_match_matches"]

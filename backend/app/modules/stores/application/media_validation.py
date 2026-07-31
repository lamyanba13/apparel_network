from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
import warnings
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import PurePath

from PIL import Image, UnidentifiedImageError

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.stores.application.media_schemas import (
    StoreMediaUpload,
    ValidatedStoreMedia,
)
from app.modules.stores.domain import StoreMediaType

_MIME_EXTENSIONS = {
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/png": frozenset({".png"}),
    "image/webp": frozenset({".webp"}),
    "image/avif": frozenset({".avif"}),
}
_FORMAT_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "AVIF": "image/avif",
}
_CANONICAL_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/avif": ".avif",
}
_SIZE_LIMITS = {
    StoreMediaType.LOGO: 5 * 1024 * 1024,
    StoreMediaType.BANNER: 10 * 1024 * 1024,
    StoreMediaType.GALLERY: 15 * 1024 * 1024,
}
_SAFE_FILENAME_CHARACTER = re.compile(r"[^A-Za-z0-9._ -]+")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_PIXELS = 40_000_000


class StoreMediaValidationService:
    """Validate image bytes and derive trusted metadata."""

    def maximum_size(self, media_type: StoreMediaType) -> int:
        return _SIZE_LIMITS[media_type]

    def validate(
        self,
        media_type: StoreMediaType,
        upload: StoreMediaUpload,
    ) -> ValidatedStoreMedia:
        filename = self.sanitize_filename(upload.filename)
        declared_mime = upload.declared_mime_type.lower().strip()
        if declared_mime not in _MIME_EXTENSIONS:
            raise _validation("file", "The declared image type is not supported.")
        extension = PurePath(filename).suffix.lower()
        if extension not in _MIME_EXTENSIONS[declared_mime]:
            raise _validation(
                "file",
                "Filename extension does not match the declared image type.",
            )
        size = len(upload.data)
        if size <= 0:
            raise _validation("file", "The image file cannot be empty.")
        if size > self.maximum_size(media_type):
            raise _validation(
                "file",
                f"The {media_type.value} image exceeds its size limit.",
            )

        magic_mime = _mime_from_magic(upload.data)
        if magic_mime != declared_mime:
            raise _validation(
                "file",
                "Image signature does not match the declared image type.",
            )
        width, height, orientation, decoded_mime = _decode_image(upload.data)
        if decoded_mime != declared_mime:
            raise _validation(
                "file",
                "Decoded image format does not match the declared image type.",
            )
        if width * height > _MAX_PIXELS:
            raise _validation("file", "The decoded image dimensions are too large.")

        checksum = hashlib.sha256(upload.data).hexdigest()
        if upload.declared_checksum_sha256 is not None:
            declared_checksum = upload.declared_checksum_sha256.lower().strip()
            if not _SHA256.fullmatch(declared_checksum) or not hmac.compare_digest(
                checksum,
                declared_checksum,
            ):
                raise _validation("checksum_sha256", "Image checksum does not match.")
        if upload.display_order < 0:
            raise _validation(
                "display_order",
                "Display order must be zero or greater.",
            )
        return ValidatedStoreMedia(
            original_filename=filename,
            extension=_CANONICAL_EXTENSION[decoded_mime],
            mime_type=decoded_mime,
            data=upload.data,
            file_size=size,
            width=width,
            height=height,
            orientation=orientation,
            aspect_ratio=(Decimal(width) / Decimal(height)).quantize(
                Decimal("0.000001"),
                rounding=ROUND_HALF_UP,
            ),
            checksum_sha256=checksum,
            display_order=upload.display_order,
            is_public=upload.is_public,
        )

    def sanitize_filename(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).replace("\\", "/")
        basename = PurePath(normalized).name
        safe = _SAFE_FILENAME_CHARACTER.sub("_", basename)
        safe = " ".join(safe.split()).strip(" .")
        if not safe:
            raise _validation("file", "A valid original filename is required.")
        if len(safe) > 255:
            suffix = PurePath(safe).suffix
            safe = f"{PurePath(safe).stem[: 255 - len(suffix)]}{suffix}"
        return safe


def _mime_from_magic(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 16 and data[4:8] == b"ftyp":
        brands = data[8:32]
        if b"avif" in brands or b"avis" in brands:
            return "image/avif"
    return None


def _decode_image(data: bytes) -> tuple[int, int, int, str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                decoded_mime = _FORMAT_MIME.get(image.format or "")
                width, height = image.size
                image.verify()
            with Image.open(BytesIO(data)) as decoded:
                orientation_value = decoded.getexif().get(274, 1)
                orientation = (
                    orientation_value
                    if isinstance(orientation_value, int)
                    and 1 <= orientation_value <= 8
                    else 1
                )
                decoded.load()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as error:
        raise _validation("file", "The image content is invalid or unsafe.") from error
    if decoded_mime is None or width <= 0 or height <= 0:
        raise _validation("file", "The decoded image format is not supported.")
    return width, height, orientation, decoded_mime


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Store media validation failed",
        detail="The uploaded Store image is invalid.",
        status_code=422,
        errors=[
            FieldError(
                field=field,
                code="invalid_store_media",
                message=message,
            )
        ],
    )

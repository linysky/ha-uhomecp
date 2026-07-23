"""Captcha OCR recognition using ddddocr."""

import base64
import logging

_LOGGER = logging.getLogger(__name__)

_ocr_instance = None


def _get_ocr():
    """Get or create ddddocr instance (lazy load)."""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            import ddddocr
            _ocr_instance = ddddocr.DdddOcr(show_ad=False)
            _LOGGER.info("ddddocr initialized successfully")
        except ImportError:
            _LOGGER.warning("ddddocr not installed, captcha auto-recognition disabled")
            return None
        except Exception as err:
            _LOGGER.error("Failed to initialize ddddocr: %s", err)
            return None
    return _ocr_instance


def recognize_captcha(img_base64: str) -> str | None:
    """Recognize captcha from base64 encoded image.

    Args:
        img_base64: Base64 encoded captcha image (JPEG/PNG)

    Returns:
        Recognized text (4 chars) or None if recognition failed
    """
    ocr = _get_ocr()
    if ocr is None:
        return None

    try:
        img_bytes = base64.b64decode(img_base64)
        result = ocr.classification(img_bytes)

        if result and len(result) == 4 and result.isalnum():
            _LOGGER.info("Captcha recognized: %s", result)
            return result

        _LOGGER.warning("Captcha recognition invalid: %s", result)
        return None
    except Exception as err:
        _LOGGER.error("Captcha recognition failed: %s", err)
        return None


def is_available() -> bool:
    """Check if captcha OCR is available."""
    return _get_ocr() is not None

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import tiktoken; if not available, use approximate fallback.
try:
    import tiktoken

    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    logger.warning(
        "tiktoken is not installed. Using approximate token counting. "
        "Install tiktoken for accurate counts: pip install tiktoken"
    )

# Cached tiktoken encoders
_encoders: dict = {}

# Model name to encoding mapping (prefix-based matching)
_ENCODING_MAP = {
    "o200k_base": ["gpt-4o", "gpt-4o-mini"],
    "cl100k_base": ["gpt-4", "gpt-3.5-turbo", "text-embedding-3", "text-embedding-ada"],
}


def _resolve_encoding(model: str) -> str:
    """Resolve a model name to the tiktoken encoding name."""
    model_lower = model.lower()

    if "gpt-4o" in model_lower:
        return "o200k_base"
    if "gpt-4" in model_lower or "gpt-3.5" in model_lower:
        return "cl100k_base"
    if "text-embedding" in model_lower:
        return "cl100k_base"

    # Default: most common modern encoding
    return "cl100k_base"


def _get_encoder(encoding_name: str):
    """Get or create a tiktoken encoder."""
    if encoding_name not in _encoders:
        if not _TIKTOKEN_AVAILABLE:
            return None
        try:
            _encoders[encoding_name] = tiktoken.get_encoding(encoding_name)
        except Exception as e:
            logger.warning(f"Failed to load tiktoken encoding {encoding_name}: {e}")
            return None
    return _encoders.get(encoding_name)


def _approximate_token_count(text: str) -> int:
    """Approximate token count without tiktoken.

    Uses a hybrid heuristic that is more accurate than len(text) // 4
    for mixed-language content (especially CJK).

    Heuristic:
      - ASCII / Latin chars: ~4 chars per token
      - CJK characters: ~1.5 chars per token
      - Other Unicode: ~3 chars per token
    """
    if not text:
        return 0

    cjk_chars = 0
    ascii_chars = 0
    other_chars = 0

    for ch in text:
        code = ord(ch)
        # CJK Unified Ideographs + Extensions + Symbols + Fullwidth + Hiragana + Katakana + Hangul
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
            or 0x3000 <= code <= 0x303F
            or 0xFF00 <= code <= 0xFFEF
            or 0x3040 <= code <= 0x309F
            or 0x30A0 <= code <= 0x30FF
            or 0xAC00 <= code <= 0xD7AF
        ):
            cjk_chars += 1
        elif code < 128:
            ascii_chars += 1
        else:
            other_chars += 1

    token_estimate = ascii_chars / 4.0 + cjk_chars / 1.5 + other_chars / 3.0
    return max(1, int(token_estimate))


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens for a string.

    Args:
        text: The text to count tokens for.
        model: Model name used to select the correct tokenizer.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0

    if _TIKTOKEN_AVAILABLE:
        encoding_name = _resolve_encoding(model)
        encoder = _get_encoder(encoding_name)
        if encoder is not None:
            try:
                return len(encoder.encode(text))
            except Exception as e:
                logger.debug(f"tiktoken encode failed: {e}")

    return _approximate_token_count(text)


def count_message_tokens(messages: list, model: str = "gpt-4") -> int:
    """Count tokens for a list of chat messages (OpenAI format).

    Includes per-message overhead (~4 tokens) and assistant priming (~3 tokens).
    """
    if not messages:
        return 0

    total = 0
    for msg in messages:
        # Message formatting overhead (role labels, delimiters)
        total += 4
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content, model)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        total += count_tokens(item.get("text", ""), model)
                    elif item.get("type") in ("image_url", "image"):
                        # Low-res image approximation (OpenAI standard)
                        total += 85

    # Priming tokens for the assistant reply
    total += 3
    return total

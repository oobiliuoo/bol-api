"""Request parameter sanitization for different providers."""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Valid effort values for different providers
VALID_EFFORT_VALUES = {
    "low", "medium", "high", "max"
}

# Effort value mapping (unsupported -> supported)
EFFORT_MAPPING = {
    "xhigh": "max",
    "ultra": "max",
    "extreme": "max",
    "minimal": "low",
    "normal": "medium",
}


def sanitize_effort(body: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize effort parameter in request body.

    Some providers don't support all effort values (e.g., 'xhigh').
    This function maps unsupported values to valid ones.

    Args:
        body: The request body dictionary

    Returns:
        Sanitized request body
    """
    if not isinstance(body, dict):
        return body

    # Check for effort in various locations
    # 1. Top-level effort (OpenAI style)
    if "effort" in body:
        effort = body["effort"]
        if isinstance(effort, str) and effort.lower() not in VALID_EFFORT_VALUES:
            mapped = EFFORT_MAPPING.get(effort.lower(), "high")
            logger.info(f"Mapping effort '{effort}' -> '{mapped}'")
            body["effort"] = mapped

    # 2. output_config.effort (some providers like Volcengine)
    if "output_config" in body and isinstance(body["output_config"], dict):
        config = body["output_config"]
        if "effort" in config:
            effort = config["effort"]
            if isinstance(effort, str) and effort.lower() not in VALID_EFFORT_VALUES:
                mapped = EFFORT_MAPPING.get(effort.lower(), "high")
                logger.info(f"Mapping output_config.effort '{effort}' -> '{mapped}'")
                config["effort"] = mapped

    return body


def sanitize_request(body: Dict[str, Any], provider_type: str = None) -> Dict[str, Any]:
    """Sanitize request body for a specific provider.

    Args:
        body: The request body dictionary
        provider_type: The provider type (e.g., "openai", "anthropic", "custom")

    Returns:
        Sanitized request body
    """
    if not isinstance(body, dict):
        return body

    # Apply effort sanitization for all providers
    body = sanitize_effort(body)

    return body

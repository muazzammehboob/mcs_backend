"""Static model capability table.

Implements consolidated spec §13 and §18: a hand-curated lookup for model
input/output modalities, maintained manually as new models ship.

This avoids relying on Gemini's models.list metadata, which is inconsistent
across model generations for declaring supported modalities.
"""

from __future__ import annotations

# model name pattern -> {input_modalities, output_modalities}
_CAPABILITY_TABLE: list[tuple[str, list[str], list[str]]] = [
    (
        "gemini-2.5-flash",
        ["text", "image", "audio", "video"],
        ["text"],
    ),
    (
        "gemini-2.5-pro",
        ["text", "image", "audio", "video"],
        ["text"],
    ),
    # Future 3.x models (placeholder entries)
    (
        "gemini-3",
        ["text", "image", "audio", "video"],
        ["text"],
    ),
]


def get_modalities(model_name: str) -> tuple[list[str], list[str]] | None:
    """Return (input_modalities, output_modalities) for a model.

    Args:
        model_name: The model name (e.g., "gemini-2.5-flash").

    Returns:
        Tuple of (input_modalities, output_modalities), or None if unknown.
    """
    lower = model_name.lower()
    for pattern, inp, out in _CAPABILITY_TABLE:
        if pattern in lower:
            return (inp, out)
    return None

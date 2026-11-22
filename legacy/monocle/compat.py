"""Compatibility patches for Python 3.14 and Pydantic."""
import sys
import typing

# Patch for Python 3.14a7 compatibility with Pydantic
# Python 3.14 removed the `prefer_fwd_module` parameter from typing._eval_type()
# This patch wraps the call to handle both old and new signatures.

_original_eval_type = typing._eval_type  # type: ignore[attr-defined]


def _eval_type_compat(value, globalns, localns, type_params=None, **kwargs):  # type: ignore[no-untyped-def]
    """Wrapper for typing._eval_type that handles Python 3.14 compatibility."""
    # Try calling with all parameters first (Python 3.13 and earlier)
    try:
        return _original_eval_type(value, globalns, localns, type_params, **kwargs)
    except TypeError as e:
        # If we get "unexpected keyword argument 'prefer_fwd_module'", it's Python 3.14+
        if "prefer_fwd_module" in str(e):
            # Call without the problematic kwargs for Python 3.14+
            return _original_eval_type(value, globalns, localns, type_params)
        raise


# Apply the patch at import time
if sys.version_info >= (3, 14):
    typing._eval_type = _eval_type_compat  # type: ignore[attr-defined]

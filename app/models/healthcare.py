"""Compatibility module for healthcare models.

Model definitions are split by domain in `app.models.domains`.
This module re-exports all healthcare models to keep existing imports stable.
"""

from app.models.domains import *  # noqa: F403

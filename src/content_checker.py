"""Placeholder interfaces for future content issue checks."""

from __future__ import annotations

import pandas as pd

from .models import IssueResult


def check_content_issues(df: pd.DataFrame) -> list[IssueResult]:
    """Return content issues after future duplicate and naming checks are added."""

    return []


"""Placeholder interfaces for future synonym coverage checks."""

from __future__ import annotations

import pandas as pd

from .models import IssueResult


def check_synonym_issues(df: pd.DataFrame) -> list[IssueResult]:
    """Return synonym issues after future coverage rules are added."""

    return []


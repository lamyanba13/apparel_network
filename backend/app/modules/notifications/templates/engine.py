from __future__ import annotations

from collections.abc import Mapping
from string import Template


def render_template(value: str, variables: Mapping[str, object]) -> str:
    return Template(value).substitute(
        {key: str(item) for key, item in variables.items()}
    )

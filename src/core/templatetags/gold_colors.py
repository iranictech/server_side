"""Journal-specific global CSS color overrides for Gold."""

import re

from django import template
from django.utils.html import format_html, format_html_join

from core.gold_theme_colors import GOLD_COLOR_TOKENS
from core.models import SettingValue

register = template.Library()

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")

COLOR_NAMES = {
    f"gold_color_{name}": token
    for name, token, label, default in GOLD_COLOR_TOKENS
}


@register.simple_tag
def gold_color_overrides(journal):
    if journal is None:
        return ""

    rows = SettingValue.objects.filter(
        journal=journal,
        setting__group__name="styling",
        setting__name__in=COLOR_NAMES,
    ).values_list("setting__name", "value")

    colors = []

    for name, value in rows:
        if name not in COLOR_NAMES or not value:
            continue

        value = value.strip()

        if HEX_COLOR.fullmatch(value):
            colors.append((COLOR_NAMES[name], value.upper()))

    if not colors:
        return ""

    declarations = format_html_join(
        "",
        "  {}: {};\n",
        colors,
    )

    return format_html(
        '<style id="gold-journal-color-overrides">'
        ':root {{{}}}'
        '</style>',
        declarations,
    )

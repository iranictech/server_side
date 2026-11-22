"""Register Gold theme color settings in Janeway."""

from django.db import transaction

from core.gold_theme_colors import GOLD_COLOR_TOKENS
from core.models import Role, Setting, SettingGroup, SettingValue


@transaction.atomic
def register_gold_color_settings():
    group, _ = SettingGroup.objects.get_or_create(
        name="styling"
    )

    registered = []

    roles = list(
        Role.objects.filter(
            slug__in=["editor", "journal-manager"]
        )
    )

    if {role.slug for role in roles} != {
        "editor",
        "journal-manager",
    }:
        raise ValueError(
            "Required Gold styling roles are missing."
        )

    for name, token, label, default in GOLD_COLOR_TOKENS:
        setting_name = f"gold_color_{name}"

        setting, created = Setting.objects.get_or_create(
            group=group,
            name=setting_name,
            defaults={
                "types": "char",
                "pretty_name": label,
                "description": f"Gold global CSS token: {token}",
                "is_translatable": False,
            },
        )

        if not created and (
            setting.types != "char"
            or setting.is_translatable
        ):
            raise ValueError(
                f"Incompatible existing setting: {setting_name}"
            )

        SettingValue.objects.get_or_create(
            setting=setting,
            journal=None,
            defaults={"value": ""},
        )

        setting.editable_by.add(*roles)

        registered.append(setting_name)

    return registered

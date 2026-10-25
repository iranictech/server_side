from django.db import transaction
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from core import models
from utils import setting_handler


MANAGED_PERMISSIONS = ("sections", "licenses")


@require_POST
def update_role_permissions(request, slug):
    if not request.user.is_authenticated:
        raise PermissionDenied

    if not request.journal:
        raise PermissionDenied

    if not (request.user.is_staff or request.user.is_journal_manager(request.journal)):
        raise PermissionDenied

    role = get_object_or_404(models.Role, slug=slug)

    if role.slug != "editor-in-chief":
        raise PermissionDenied

    submitted_permissions = {
        name: request.POST.get(name, "") for name in MANAGED_PERMISSIONS
    }

    if any(value not in ("", "on") for value in submitted_permissions.values()):
        raise PermissionDenied

    with transaction.atomic():
        for permission_name in MANAGED_PERMISSIONS:
            submitted = submitted_permissions[permission_name]

            current = setting_handler.get_setting(
                setting_group_name="permission",
                setting_name=permission_name,
                journal=request.journal,
            )

            allowed_roles = set(current.processed_value or [])

            if submitted == "on":
                allowed_roles.add(role.slug)
            else:
                allowed_roles.discard(role.slug)

            setting_handler.save_setting(
                "permission",
                permission_name,
                request.journal,
                sorted(allowed_roles),
            )

    messages.success(request, "Role permissions updated.")
    return redirect(reverse("core_manager_role", kwargs={"slug": slug}))


def get_role_permission_context(request, role):
    can_manage = (
        request.user.is_authenticated
        and (request.user.is_staff or request.user.is_journal_manager(request.journal))
        and role.slug == "editor-in-chief"
    )

    permissions = []

    if can_manage:
        labels = {
            "sections": "Manage Sections",
            "licenses": "Manage Licenses",
        }

        for name in MANAGED_PERMISSIONS:
            setting = setting_handler.get_setting(
                setting_group_name="permission",
                setting_name=name,
                journal=request.journal,
            )

            permissions.append(
                {
                    "name": name,
                    "label": labels[name],
                    "enabled": role.slug in (setting.processed_value or []),
                }
            )

    return {
        "can_manage_role_permissions": can_manage,
        "role_permissions": permissions,
    }

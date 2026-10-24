from django.contrib import admin

from .models import AbstractIndexing


@admin.register(AbstractIndexing)
class AbstractIndexingAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "journal",
        "ordering",
        "is_active",
    )

    list_filter = (
        "journal",
        "is_active",
    )

    search_fields = (
        "name",
        "description",
        "journal__name",
    )

    ordering = (
        "journal",
        "ordering",
    )
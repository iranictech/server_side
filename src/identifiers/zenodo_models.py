from django.db import models
from django.db.models import Q


class ZenodoDeposit(models.Model):

    class Status(models.TextChoices):
        READY = "ready", "Ready"
        CREATING = "creating", "Creating"
        DRAFT = "draft", "Draft"
        UPLOADING = "uploading", "Uploading"
        UPLOADED = "uploaded", "Uploaded"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"
        UNKNOWN = "unknown", "Unknown"

    article = models.ForeignKey(
        "submission.Article",
        on_delete=models.PROTECT,
        related_name="zenodo_deposits",
    )

    is_sandbox = models.BooleanField(default=True)

    deposition_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    reserved_doi = models.CharField(
        max_length=300,
        blank=True,
    )

    published_doi = models.CharField(
        max_length=300,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.READY,
    )

    record_url = models.URLField(
        max_length=500,
        blank=True,
    )

    metadata_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )

    last_error = models.TextField(
        blank=True,
    )

    upload_filename = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    upload_size = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    upload_checksum = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["article", "is_sandbox"],
                name="unique_zenodo_article_env",
            ),
            models.UniqueConstraint(
                fields=["deposition_id", "is_sandbox"],
                condition=Q(deposition_id__isnull=False),
                name="unique_zenodo_remote_id",
            ),
        ]

    def __str__(self):
        return (
            f"Article {self.article_id} | "
            f"Zenodo {self.deposition_id} | "
            f"{self.status}"
        )

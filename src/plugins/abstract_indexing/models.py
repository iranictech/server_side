from django.db import models


class AbstractIndexing(models.Model):
    journal = models.ForeignKey(
        "journal.Journal",
        on_delete=models.CASCADE,
        related_name="abstract_indexings",
    )

    image = models.ImageField(
        upload_to="abstract_indexing/",
        blank=True,
        null=True,
    )

    name = models.CharField(
        max_length=255,
    )

    url = models.URLField(
        max_length=500,
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    ordering = models.PositiveIntegerField(
        default=0,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["ordering", "name"]
        verbose_name = "Abstract Indexing"
        verbose_name_plural = "Abstract Indexings"

    def __str__(self):
        return self.name
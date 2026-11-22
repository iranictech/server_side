from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("review", "0025_reviewassignmentanswerfile"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReviewerCOIAssessment",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("cleared", "No apparent conflict after editorial review"),
                            ("conflict", "Conflict identified"),
                            ("uncertain", "Further review required"),
                        ],
                        max_length=12,
                    ),
                ),
                ("rationale", models.TextField()),
                (
                    "recorded_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        editable=False,
                    ),
                ),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reviewer_coi_assessments",
                        to="submission.article",
                    ),
                ),
                (
                    "assessed_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="coi_assessments_recorded",
                        to="core.account",
                    ),
                ),
                (
                    "reviewer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reviewer_coi_assessments",
                        to="core.account",
                    ),
                ),
            ],
            options={
                "ordering": ("-recorded_at", "-pk"),
            },
        ),
    ]

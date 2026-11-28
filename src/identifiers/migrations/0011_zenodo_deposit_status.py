from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "identifiers",
            "0010_zenododeposit",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="zenododeposit",
            name="status",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("ready", "Ready"),
                    ("creating", "Creating"),
                    ("draft", "Draft"),
                    ("uploaded", "Uploaded"),
                    ("published", "Published"),
                    ("failed", "Failed"),
                    ("unknown", "Unknown"),
                ],
                default="ready",
            ),
        ),
    ]

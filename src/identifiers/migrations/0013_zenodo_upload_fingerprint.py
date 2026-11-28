from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identifiers", "0012_zenodo_uploading_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="zenododeposit",
            name="upload_filename",
            field=models.CharField(
                max_length=255,
                blank=True,
                default="",
            ),
        ),
        migrations.AddField(
            model_name="zenododeposit",
            name="upload_size",
            field=models.PositiveBigIntegerField(
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="zenododeposit",
            name="upload_checksum",
            field=models.CharField(
                max_length=64,
                blank=True,
                default="",
            ),
        ),
    ]

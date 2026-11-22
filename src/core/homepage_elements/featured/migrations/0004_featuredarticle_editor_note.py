from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("featured", "0003_alter_featuredarticle_added_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="featuredarticle",
            name="editor_note",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Editor's note for this featured article.",
            ),
        ),
    ]

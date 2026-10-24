import core.model_utils
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("journal", "0067_issue_cached_display_title_es_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name='journal',
            name='journal_footer_text',
            field=core.model_utils.JanewayBleachField(blank=True, help_text='Text that will appear in the footer of this journal.', null=True, verbose_name='Journal footer text'),
        ),
        migrations.AddField(
            model_name='journal',
            name='footer_brand',
            field=core.model_utils.JanewayBleachField(blank=True, help_text='Content for the first footer column.', null=True, verbose_name='Footer - Brand'),
        ),
        migrations.AddField(
            model_name='journal',
            name='footer_contact',
            field=core.model_utils.JanewayBleachField(blank=True, help_text='Content for the fourth footer column.', null=True, verbose_name='Footer - Contact'),
        ),
        migrations.AddField(
            model_name='journal',
            name='footer_guides',
            field=core.model_utils.JanewayBleachField(blank=True, help_text='Content for the third footer column.', null=True, verbose_name='Footer - Guides & Policies'),
        ),
        migrations.AddField(
            model_name='journal',
            name='footer_useful_links',
            field=core.model_utils.JanewayBleachField(blank=True, help_text='Content for the second footer column.', null=True, verbose_name='Footer - Useful Links'),
        ),
    ]

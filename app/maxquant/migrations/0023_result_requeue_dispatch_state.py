from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("maxquant", "0022_result_process_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="result",
            name="processing_attempt",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="result",
            name="requeue_dispatch_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

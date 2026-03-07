from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("maxquant", "0021_alter_maxquantexecutable_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="result",
            name="maxquant_pgid",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="result",
            name="maxquant_pid",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="result",
            name="rawtools_metrics_pgid",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="result",
            name="rawtools_metrics_pid",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="result",
            name="rawtools_qc_pgid",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="result",
            name="rawtools_qc_pid",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]

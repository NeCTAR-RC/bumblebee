# Generated by Django 3.2.7 on 2022-02-22 06:12

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('vm_manager', '0010_populate_expirations'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cloudresource',
            name='expires',
        ),
        migrations.RemoveField(
            model_name='resize',
            name='expires',
        ),
        migrations.AlterField(
            model_name='cloudresource',
            name='expiration',
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='expiration_for',
                to='vm_manager.resourceexpiration'),
        ),
        migrations.AlterField(
            model_name='resize',
            name='expiration',
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='expiration_for',
                to='vm_manager.resizeexpiration'),
        ),
    ]

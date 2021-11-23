# Generated by Django 3.2.7 on 2021-11-23 05:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('researcher_workspace', '0003_add_terms_agreed'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='ARO',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='admin_comments',
            field=models.TextField(blank=True, null=True, verbose_name='Admin comments (not visible to users)'),
        ),
    ]

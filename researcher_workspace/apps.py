from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate
from health_check.plugins import plugin_dir
from prometheus_client import REGISTRY


migration_executed = False
monitoring_initialised = False


def post_migration_callback(sender, **kwargs):
    global migration_executed
    migration_executed = True


def connection_callback(sender, connection, **kwargs):
    global monitoring_initialised
    # Check to see if we are not running a unittest temp db
    if not connection.settings_dict['NAME'] == 'file:memorydb_default?mode=memory&cache=shared':
        if not monitoring_initialised:
            from researcher_workspace import metrics
            import sys
            # NOTE(yoctozepto): It should not try to access the database when running the migrations.
            if not ('makemigrations' in sys.argv
                    or 'showmigrations' in sys.argv
                    or 'migrate' in sys.argv):
                REGISTRY.register(metrics.BumblebeeMetricsCollector())
            monitoring_initialised = True


class ResearcherWorkspaceConfig(AppConfig):
    name = 'researcher_workspace'

    def ready(self):
        import researcher_workspace.signals  # noqa

        global migration_executed
        post_migrate.connect(post_migration_callback, sender=self)

        if not migration_executed:
            connection_created.connect(connection_callback)

        from researcher_workspace.health import DesktopStatus
        plugin_dir.register(DesktopStatus)

from django.apps import AppConfig


class ResearcherWorkspaceConfig(AppConfig):
    name = 'researcher_workspace'

    def ready(self):
        import researcher_workspace.signals  # noqa

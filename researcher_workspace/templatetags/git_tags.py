from django import template
from git import Repo

register = template.Library()

project_root = '.'


@register.simple_tag
def current_commit(path=project_root):
    repo = Repo(path)
    commit = repo.commit()
    repo.__del__()
    return commit.hexsha


@register.simple_tag
def current_commit_short(path=project_root):
    return current_commit(path)[:8]

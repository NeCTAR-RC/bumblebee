#from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from researcher_workspace.models import Profile, User


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

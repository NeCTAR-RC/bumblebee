from django.db import models

from .fields import GuacamoleConnectionGroupTypeField
from .fields import GuacamoleObjectPermissionTypeField
from .fields import GuacamoleSystemPermissionTypeField

connection_group_type = (
    ('ORGANIZATIONAL', 'ORGANIZATIONAL'),
    ('BALANCING', 'BALANCING'))

object_permission_type = (
    ('READ', 'READ'),
    ('UPDATE', 'UPDATE'),
    ('DELETE', 'DELETE'),
    ('ADMINISTER', 'ADMINISTER'))

system_permission_type = (
    ('CREATE_CONNECTION', 'CREATE_CONNECTION'),
    ('CREATE_CONNECTION_GROUP', 'CREATE_CONNECTION_GROUP'),
    ('CREATE_USER', 'CREATE_USER'),
    ('ADMINISTER', 'ADMINISTER'))

entity_type = (
    ('USER', 'USER'),
    ('USER_GROUP', 'USER_GROUP'))


class GuacamoleEntity(models.Model):
    entity_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=128)
    type = models.CharField(max_length=10)

    class Meta:
        managed = False
        db_table = 'guacamole_entity'
        unique_together = (('type', 'name'),)


class GuacamoleUser(models.Model):
    user_id = models.AutoField(primary_key=True)
    entity = models.OneToOneField(
        GuacamoleEntity,
        on_delete=models.CASCADE,)
    password_hash = models.CharField(max_length=32)
    password_salt = models.CharField(max_length=32, blank=True, null=True)
    password_date = models.DateTimeField(auto_now_add=True, blank=True)
    disabled = models.BooleanField(default=False)
    expired = models.BooleanField(default=False)
    access_window_start = models.TimeField(blank=True, null=True)
    access_window_end = models.TimeField(blank=True, null=True)
    valid_from = models.DateField(blank=True, null=True)
    valid_until = models.DateField(blank=True, null=True)
    timezone = models.CharField(max_length=64, blank=True, null=True)
    full_name = models.CharField(max_length=256, blank=True, null=True)
    email_address = models.CharField(max_length=256, blank=True, null=True)
    organization = models.CharField(max_length=256, blank=True, null=True)
    organizational_role = models.CharField(
        max_length=256, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'guacamole_user'


class GuacamoleConnectionGroup(models.Model):
    connection_group_id = models.AutoField(primary_key=True)
    parent_id = models.IntegerField(blank=True, null=True)
    # parent = models.ForeignKey(
    #    'self',
    #    on_delete=models.CASCADE,
    #    blank=True, null=True)
    connection_group_name = models.CharField(max_length=128)
    type = GuacamoleConnectionGroupTypeField(
        choices=connection_group_type,
        default='ORGANIZATIONAL')
    max_connections = models.IntegerField(blank=True, null=True)
    max_connections_per_user = models.IntegerField(blank=True, null=True)
    enable_session_affinity = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'guacamole_connection_group'
        unique_together = (('connection_group_name', 'parent_id'),)


class GuacamoleConnection(models.Model):
    connection_id = models.AutoField(primary_key=True)
    connection_name = models.CharField(max_length=128)
    parent_id = models.IntegerField(blank=True, null=True)
    # parent = models.ForeignKey(GuacamoleConnectionGroup,
    #    on_delete=models.CASCADE,
    #    blank=True, null=True)
    protocol = models.CharField(max_length=32, default='rdp')
    proxy_port = models.IntegerField(blank=True, null=True)
    proxy_hostname = models.CharField(max_length=512, blank=True, null=True)
    proxy_encryption_method = models.CharField(
        max_length=4, blank=True, null=True)
    max_connections = models.IntegerField(blank=True, null=True)
    max_connections_per_user = models.IntegerField(blank=True, null=True)
    connection_weight = models.IntegerField(blank=True, null=True)
    failover_only = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'guacamole_connection'
        unique_together = (('connection_name', 'parent_id'),)


class GuacamoleConnectionAttribute(models.Model):
    connection = models.OneToOneField(
        GuacamoleConnection,
        on_delete=models.CASCADE,
        primary_key=True)
    attribute_name = models.CharField(max_length=128)
    attribute_value = models.CharField(max_length=4096)

    class Meta:
        managed = False
        db_table = 'guacamole_connection_attribute'
        unique_together = (('connection', 'attribute_name'),)


class GuacamoleConnectionGroupAttribute(models.Model):
    connection_group = models.OneToOneField(
        GuacamoleConnectionGroup,
        on_delete=models.CASCADE,
        primary_key=True)
    attribute_name = models.CharField(max_length=128)
    attribute_value = models.CharField(max_length=4096)

    class Meta:
        managed = False
        db_table = 'guacamole_connection_group_attribute'
        unique_together = (('connection_group', 'attribute_name'),)


class GuacamoleConnectionGroupPermission(models.Model):
    entity = models.OneToOneField(
        GuacamoleEntity,
        on_delete=models.CASCADE,
        primary_key=True)
    connection_group = models.ForeignKey(
        GuacamoleConnectionGroup,
        on_delete=models.CASCADE,
        blank=True, null=True)
    permission = GuacamoleObjectPermissionTypeField(
        choices=object_permission_type,
        default='READ')

    class Meta:
        managed = False
        db_table = 'guacamole_connection_group_permission'
        unique_together = (('entity', 'connection_group', 'permission'),)


class GuacamoleSharingProfile(models.Model):
    sharing_profile_id = models.AutoField(primary_key=True)
    sharing_profile_name = models.CharField(max_length=128)
    primary_connection = models.ForeignKey(
        GuacamoleConnection,
        on_delete=models.CASCADE,
        blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'guacamole_sharing_profile'
        unique_together = (('sharing_profile_name', 'primary_connection'),)


class GuacamoleConnectionHistory(models.Model):
    history_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        GuacamoleUser,
        on_delete=models.CASCADE,
        blank=True, null=True)
    username = models.CharField(max_length=128)
    remote_host = models.CharField(max_length=256, blank=True, null=True)
    connection = models.ForeignKey(
        GuacamoleConnection,
        on_delete=models.CASCADE,
        blank=True, null=True)
    connection_name = models.CharField(max_length=128)
    sharing_profile = models.ForeignKey(
        GuacamoleSharingProfile,
        on_delete=models.CASCADE,
        blank=True, null=True)
    sharing_profile_name = models.CharField(
        max_length=128, blank=True, null=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'guacamole_connection_history'


class GuacamoleConnectionParameter(models.Model):
    connection = models.OneToOneField(
        GuacamoleConnection,
        on_delete=models.CASCADE,
        primary_key=True)
    parameter_name = models.CharField(max_length=128)
    parameter_value = models.CharField(max_length=4096)

    class Meta:
        managed = False
        db_table = 'guacamole_connection_parameter'
        unique_together = (('connection', 'parameter_name'),)


class GuacamoleConnectionPermission(models.Model):
    entity = models.OneToOneField(
        GuacamoleEntity,
        on_delete=models.CASCADE,
        primary_key=True)
    connection = models.ForeignKey(
        GuacamoleConnection,
        on_delete=models.CASCADE,
        blank=True, null=True)
    permission = GuacamoleObjectPermissionTypeField(
        choices=object_permission_type,
        default='READ')

    class Meta:
        managed = False
        db_table = 'guacamole_connection_permission'
        unique_together = (('entity', 'connection', 'permission'),)


class GuacamoleSharingProfileAttribute(models.Model):
    sharing_profile = models.OneToOneField(
        GuacamoleSharingProfile,
        on_delete=models.CASCADE,
        primary_key=True)
    attribute_name = models.CharField(max_length=128)
    attribute_value = models.CharField(max_length=4096)

    class Meta:
        managed = False
        db_table = 'guacamole_sharing_profile_attribute'
        unique_together = (('sharing_profile', 'attribute_name'),)


class GuacamoleSharingProfileParameter(models.Model):
    sharing_profile = models.OneToOneField(
        GuacamoleSharingProfile,
        on_delete=models.CASCADE,
        primary_key=True)
    parameter_name = models.CharField(max_length=128)
    parameter_value = models.CharField(max_length=4096)

    class Meta:
        managed = False
        db_table = 'guacamole_sharing_profile_parameter'
        unique_together = (('sharing_profile', 'parameter_name'),)


class GuacamoleSharingProfilePermission(models.Model):
    entity = models.OneToOneField(
        GuacamoleEntity,
        on_delete=models.CASCADE,
        primary_key=True)
    sharing_profile = models.ForeignKey(
        GuacamoleSharingProfile,
        on_delete=models.CASCADE,
        blank=True, null=True)
    permission = GuacamoleObjectPermissionTypeField(
        choices=object_permission_type,
        default='READ')

    class Meta:
        managed = False
        db_table = 'guacamole_sharing_profile_permission'
        unique_together = (('entity', 'sharing_profile', 'permission'),)


class GuacamoleSystemPermission(models.Model):
    entity = models.OneToOneField(
        GuacamoleEntity,
        on_delete=models.CASCADE,
        primary_key=True)
    permission = GuacamoleSystemPermissionTypeField(
        choices=system_permission_type)

    class Meta:
        managed = False
        db_table = 'guacamole_system_permission'
        unique_together = (('entity', 'permission'),)


class GuacamoleUserAttribute(models.Model):
    user = models.OneToOneField(
        GuacamoleUser,
        on_delete=models.CASCADE,
        primary_key=True)
    attribute_name = models.CharField(max_length=128)
    attribute_value = models.CharField(max_length=4096)

    class Meta:
        managed = False
        db_table = 'guacamole_user_attribute'
        unique_together = (('user', 'attribute_name'),)


class GuacamoleUserGroup(models.Model):
    user_group_id = models.AutoField(primary_key=True)
    entity = models.OneToOneField(
        GuacamoleEntity,
        on_delete=models.CASCADE,
        blank=True, null=True)
    disabled = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'guacamole_user_group'


class GuacamoleUserGroupAttribute(models.Model):
    user_group = models.OneToOneField(GuacamoleUserGroup, on_delete=models.CASCADE, primary_key=True)
    attribute_name = models.CharField(max_length=128)
    attribute_value = models.CharField(max_length=4096)

    class Meta:
        managed = False
        db_table = 'guacamole_user_group_attribute'
        unique_together = (('user_group', 'attribute_name'),)


class GuacamoleUserGroupMember(models.Model):
    user_group = models.OneToOneField(GuacamoleUserGroup,
        on_delete=models.CASCADE, primary_key=True)
    member_entity = models.ForeignKey(GuacamoleEntity,
        on_delete=models.CASCADE, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'guacamole_user_group_member'
        unique_together = (('user_group', 'member_entity'),)


class GuacamoleUserGroupPermission(models.Model):
    entity = models.OneToOneField(GuacamoleEntity,
            on_delete=models.CASCADE, primary_key=True)
    affected_user_group = models.ForeignKey(GuacamoleUserGroup,
            on_delete=models.CASCADE,
            blank=True, null=True)
    permission = GuacamoleObjectPermissionTypeField(
        choices=object_permission_type,
        default='READ')

    class Meta:
        managed = False
        db_table = 'guacamole_user_group_permission'
        unique_together = (('entity', 'affected_user_group', 'permission'),)


class GuacamoleUserHistory(models.Model):
    history_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(GuacamoleUser, on_delete=models.CASCADE,
        blank=True, null=True)
    username = models.CharField(max_length=128)
    remote_host = models.CharField(max_length=256, blank=True, null=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'guacamole_user_history'


class GuacamoleUserPasswordHistory(models.Model):
    password_history_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(GuacamoleUser, on_delete=models.CASCADE,
        blank=True, null=True)
    password_hash = models.CharField(max_length=32)
    password_salt = models.CharField(max_length=32, blank=True, null=True)
    password_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'guacamole_user_password_history'


class GuacamoleUserPermission(models.Model):
    entity = models.OneToOneField(GuacamoleEntity,
        on_delete=models.CASCADE, primary_key=True)
    affected_user = models.ForeignKey(GuacamoleUser,
        on_delete=models.CASCADE,
        blank=True, null=True)
    permission = GuacamoleObjectPermissionTypeField(
        choices=object_permission_type,
        default='READ')

    class Meta:
        managed = False
        db_table = 'guacamole_user_permission'
        unique_together = (('entity', 'affected_user', 'permission'),)

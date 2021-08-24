from django.db import models


class EnumField(models.Field):
    description = "enumerated type"

    def __init__(self, *args, **kwargs):
        self.enum = kwargs['enum']
        del kwargs['enum']
        super(EnumField, self).__init__(*args, **kwargs)

    def db_type(self, connection):
        return self.enum


class GuacamoleConnectionGroupTypeField(EnumField):
    description = 'enumerated type for connection groups'

    def __init__(self, *args, **kwargs):
        self.enum = 'guacamole_connection_group_type'
        kwargs['enum'] = self.enum
        super(GuacamoleConnectionGroupTypeField,
              self).__init__(*args, **kwargs)


class GuacamoleObjectPermissionTypeField(EnumField):
    description = 'enumerated type for object permissions'

    def __init__(self, *args, **kwargs):
        self.enum = 'guacamole_object_permission_type'
        kwargs['enum'] = self.enum
        super(GuacamoleObjectPermissionTypeField,
              self).__init__(*args, **kwargs)


class GuacamoleSystemPermissionTypeField(EnumField):
    description = 'enumerated type for system permissions'

    def __init__(self, *args, **kwargs):
        self.enum = 'guacamole_system_permission_type'
        kwargs['enum'] = self.enum
        super(GuacamoleSystemPermissionTypeField,
              self).__init__(*args, **kwargs)

class GuacamoleEntityTypeField(EnumField):
    description = 'enumerated type for entity'

    def __init__(self, *args, **kwargs):
        self.enum = 'guacamole_entity_type'
        kwargs['enum'] = self.enum
        super(GuacamoleEntityTypeField,
              self).__init__(*args, **kwargs)

import base64
import hashlib
import random

from .models import GuacamoleUser, GuacamoleEntity, GuacamoleConnection
from .models import GuacamoleConnectionParameter, GuacamoleConnectionPermission

from researcher_workspace.settings import GUACAMOLE_URL


def get_direct_url(conn):
    # Guacamole uses a special format for generating direct URLs to connections
    # https://sourceforge.net/p/guacamole/discussion/1110834/thread/fb609070
    # 
    # The connection hash is a base64 encoded string build from three
    # components, each separated by a NULL character (U+0000)
    #   - The connection identifier (id?)
    #   - The type (c for connections)
    #   - The identifier of the auth provider storing the conn data (mysql)

    components = [str(conn.connection_id), 'c', 'mysql']
    joined_components = '\x00'.join(components).encode('utf-8')
    hash_str = base64.b64encode(joined_components).decode('utf-8')
    return f'{GUACAMOLE_URL}/#/client/{hash_str}'

def quick_rdp_conn(username, password, hostname):
    """
    Make a GuacamoleConnection with the passed parameters; return said
    Connection.
    """

    conn = GuacamoleConnection.objects.create(
        connection_name=hostname + ':' + username,
        protocol='rdp')

    # We don't need to save the GuacConnParams as they will CASCADE on_delete
    GuacamoleConnectionParameter.objects.create(
        connection=conn,
        parameter_name='username',
        parameter_value=username)

    #GuacamoleConnectionParameter.objects.create(
    #    connection=conn,
    #    parameter_name='password',
    #    parameter_value=password)

    #GuacamoleConnectionParameter.objects.create(
    #    connection=conn,
    #    parameter_name='hostname',
    #    parameter_value=hostname)

    return conn


def quick_guac_user(username, password):
    """
    Make a GuacamoleUser with the passed parameters; return said GuacamoleUser.
    Hash password, and salt with random data.
    """
    # MMmm, salt.  Must be 32 bytes.  We must hash with the uppercase,
    # hexadecimal, string representation of the binary.
    salt = bytearray(random.getrandbits(8) for _ in range(32))
    salt_hex = ''.join('{:02X}'.format(x) for x in salt)

    # "The salt is appended to the password prior to hashing."
    # http://guac-dev.org/doc/gug/jdbc-auth.html#jdbc-auth-schema-users
    message = (password + salt_hex).encode()
    password_hash = hashlib.sha256(message).digest()

    entity = GuacamoleEntity.objects.create(
        name=username,
        type='USER')

    return GuacamoleUser.objects.create(
        entity=entity,
        password_salt=salt,
        password_hash=password_hash)


def quick_rdp(guac_username, guac_password, username, password, hostname):
    """
    Make a GuacamoleUser and a GuacamoleConnection (RDP) and put them together
    in a GuacamoleConnectionPermission.  Return said
    GuacamoleConnectionPermission.
    """

    conn = quick_rdp_conn(
        username=username,
        password=password,
        hostname=hostname)

    guac_user = quick_guac_user(
        username=guac_username,
        password=guac_password)

    return GuacamoleConnectionPermission.objects.create(
        entity=guac_user.entity,
        connection=conn)


def quick_rdp_destroy(guac_username, username, hostname, cleanup_user=True,
                      cleanup_connection=True):
    """
    Remove permissions for this guac user to the guac Connection(s) matching
    these parameters.  May be multiple settings on the same Connection, and/or
    mulitple Connections.  By default, clean up users and Connections that are
    no longer referenced in the Permissions table.
    """

    # Will only get one; username is unique
    user = GuacamoleUser.objects.get(username=guac_username)

    # May be many connections, filter on parameters
    connections = GuacamoleConnection.objects.filter(
        parameters__parameter_name="hostname",
        parameters__parameter_value=hostname).filter(
            parameters__parameter_name="username",
            parameters__parameter_value=username)

    # Take first pass to remove any ConnectionPermission
    for connection in connections:
        GuacamoleConnectionPermission.objects.filter(
            user=user,
            connection=connection).delete()

    # Look again in GuacConnectionPermission.  If we (user or connection) are
    # not found, no one else is using the connection or this user only had the
    # one connection.  Clean up.
    if cleanup_user:
        if GuacamoleConnectionPermission.objects.filter(
                user=user).count() == 0:
            user.delete()

    if cleanup_connection:
        for connection in connections:
            if GuacamoleConnectionPermission.objects.filter(
                    connection=connection).count() == 0:
                connection.delete()

from novaclient.v2 import servers as nova_servers

LINUX = "linux"

SCRIPT_ERROR = 0
SCRIPT_OKAY = 1

ERROR = -1

# These are Openstack Nova server status values that the
# python client library doesn't define constants for.
ACTIVE = "ACTIVE"
BUILD = "BUILD"
REBOOT = "REBOOT"
REBUILD = "REBUILD"
RESCUE = "RESCUE"
RESIZE = "RESIZE"
SHUTDOWN = "SHUTOFF"
VERIFY_RESIZE = "VERIFY_RESIZE"
MISSING = "MISSING"
# (There are more ...)

# These are Openstack Cinder status values that the
# python client library doesn't define constants for.
VOLUME_AVAILABLE = "available"
VOLUME_IN_USE = "in-use"
VOLUME_CREATING = "creating"
VOLUME_MAINTENANCE = "maintenance"

BACKUP_AVAILABLE = "available"
BACKUP_CREATING = "creating"
# (There are more ...)

NO_VM = VM_DELETED = "No_VM"
VM_WAITING = VM_CREATING = VM_RESIZING = "VM_Waiting"
VM_OKAY = "VM_Okay"
VM_SUPERSIZED = "VM_Supersized"
VM_SHELVED = "VM_Shelved"
VM_ERROR = "VM_Error"
VM_MISSING = "VM_Missing"
VM_SHUTDOWN = "VM_Shutdown"

ALL_VM_STATES = frozenset([NO_VM, VM_WAITING, VM_OKAY, VM_SUPERSIZED,
                           VM_SHELVED, VM_ERROR, VM_MISSING, VM_SHUTDOWN])

REBOOT_SOFT = nova_servers.REBOOT_SOFT
REBOOT_HARD = nova_servers.REBOOT_HARD

CLOUD_INIT_FINISHED = "finished"
CLOUD_INIT_STARTED = "started"

# Workflow outcomes.  These are returned by function calls that
# (may) start workflows involving rqworker.  We will progressively
# switch to these (replacing True / False or other responses) starting
# with the workflows performed by the expirers.
#
# Workflow completed
WF_SUCCESS = 'succeeded'
# Workflow continues
WF_CONTINUE = 'continue'
# Workflow failed - retryable
WF_RETRY = 'failed_retryable'
# Workflow failed - non-retryable
WF_FAIL = 'failed'

# Button names
REBOOT_BUTTON = "REBOOT_BUTTON"
SHELVE_BUTTON = "SHELVE_BUTTON"
UNSHELVE_BUTTON = "UNSHELVE_BUTTON"
DELETE_BUTTON = "DELETE_BUTTON"
BOOST_BUTTON = "BOOST_BUTTON"
DOWNSIZE_BUTTON = "DOWNSIZE_BUTTON"
EXTEND_BUTTON = "EXTEND_BUTTON"
EXTEND_BOOST_BUTTON = "EXTEND_BOOST_BUTTON"

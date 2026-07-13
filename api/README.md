# Bumblebee REST API

A read-only REST API for querying Bumblebee data, intended for admin
scripts, reporting jobs and other machine consumers. It is modelled
loosely on the [JupyterHub REST API](https://jupyterhub.readthedocs.io/en/stable/reference/rest-api.html)
and built with Django REST Framework.

All endpoints live under `/api/v1/`. The API is versioned by URL
prefix; breaking changes will be introduced under a new prefix.

An OpenAPI schema is available at `/api/v1/schema/` and an
interactive Swagger UI at `/api/v1/schema/swagger/`.


## Authentication

Every endpoint requires authentication and staff-level access. The
default permission policy is deny-by-default (`IsAdminUser`): a
request must authenticate as either a staff user or a service token,
or it receives a 401/403.

Three mechanisms are supported, tried in this order:

### Service tokens

For cron jobs and other machine consumers where a real user account
is not appropriate. Service tokens are not tied to a user account,
so they are unaffected by anything that happens to a person's account
and do not appear in user listings.

Create one with:

    ./manage.py create_service_token reporting-cron

The key (prefixed `svc-`) is printed once at creation time and stored
in the database only as a SHA-256 hash. If a key is lost there is no
way to recover it: deactivate the token and create a new one.

Tokens can be audited (name, key prefix, created, last used) and
revoked (deactivated or deleted) in the Django admin under
*Service tokens*. Adding tokens through the admin is deliberately
disabled because the key can only be shown at creation.

Use one name per consumer (for example `reporting-cron`,
`usage-dashboard`) so that tokens can be revoked independently and
usage is attributable.

Requests authenticate with the standard DRF header form:

    Authorization: Token svc-<key>

The key's `svc-` prefix is how the API recognises a service token;
requests carrying other credentials fall through to the mechanisms
below.

### User tokens

Standard Django REST Framework tokens, tied to a staff user account.
Suitable for interactive or ad-hoc use where actions should be
attributable to a person:

    ./manage.py drf_create_token <username>

The user must have `is_staff` set, and requests use the same
`Authorization: Token <key>` header. User tokens are managed in the
Django admin under *Auth tokens*. Note that unlike service tokens,
DRF stores user token keys in plaintext.

### Session authentication

A staff user with a normal browser login session can use the
browsable API and Swagger UI directly. This is intended for
exploration and debugging.


## Endpoints

### `GET /api/v1/users/`

Paginated list of user accounts.

Filtering:

| Parameter | Example |
|-----------|---------|
| `is_staff`, `is_superuser`, `is_active` | `?is_staff=true` |
| `terms_version` | `?terms_version=1` |
| `last_login__gte`, `last_login__lte`, `last_login__isnull` | `?last_login__gte=2026-01-01` |
| `date_joined__gte`, `date_joined__lte` | `?date_joined__gte=2026-01-01` |
| `search` (matches username, email, first/last name) | `?search=jane` |
| `ordering` (`username`, `date_joined`, `last_login`; `-` for descending) | `?ordering=-last_login` |

Note that `last_login` only updates when a user authenticates, so it
is a "last login" rather than a true "last activity" measure.

### `GET /api/v1/users/<username>/`

A single user, including a `desktops` summary of their current
desktops. Usernames are email addresses, so encode them in the URL,
for example `/api/v1/users/jane.doe%40example.edu.au/`.

### `GET /api/v1/desktops/`

Paginated list of users' current desktops: the latest state record
for each user and desktop type, excluding desktops that no longer
exist. The state is reported from the Bumblebee database and never
queries OpenStack.

Status values are those used by `vm_manager` (`VM_Okay`,
`VM_Shelved`, `VM_Supersized`, `VM_Waiting`, `VM_Error`, ...). A
shelved desktop's instance has been deleted, but the desktop still
exists and is reported with status `VM_Shelved`.

Filtering:

| Parameter | Example |
|-----------|---------|
| `desktop_type` | `?desktop_type=neurodesktop` |
| `status` | `?status=VM_Shelved` |
| `user` (username) | `?user=jane.doe%40example.edu.au` |
| `zone` | `?zone=QRIScloud` |
| `created_after`, `created_before` | `?created_after=2026-01-01` |
| `ordering` (`created`, `user__username`, `operating_system`, `status`) | `?ordering=-created` |

## Pagination

List responses use a standard envelope:

    {
        "count": 123,
        "next": "https://.../api/v1/users/?page=2",
        "previous": null,
        "results": [ ... ]
    }

Follow the `next` URL until it is null. Page size defaults to 50 and
can be raised with `?page_size=`, capped at 200.


## Examples with curl

Create a token and keep the key somewhere safe:

    ./manage.py create_service_token reporting-cron

Set it in the environment for the examples below:

    export TOKEN=svc-...
    export API=https://bumblebee.example.org/api/v1

List all users:

    curl -H "Authorization: Token $TOKEN" "$API/users/"

Staff users, most recent login first:

    curl -H "Authorization: Token $TOKEN" \
        "$API/users/?is_staff=true&ordering=-last_login"

Users who have logged in since the start of 2026:

    curl -H "Authorization: Token $TOKEN" \
        "$API/users/?last_login__gte=2026-01-01"

A single user. Usernames are email addresses, so URL-encode the `@`:

    curl -H "Authorization: Token $TOKEN" \
        "$API/users/jane.doe%40example.edu.au/"

All desktops currently running or shelved:

    curl -H "Authorization: Token $TOKEN" "$API/desktops/"

Which users have a neurodesktop shelved:

    curl -H "Authorization: Token $TOKEN" \
        "$API/desktops/?desktop_type=neurodesktop&status=VM_Shelved"

Download the OpenAPI schema:

    curl -H "Authorization: Token $TOKEN" "$API/schema/"

Responses are JSON; pipe through `jq` or `python3 -m json.tool` for
readable output.


## Example client

```python
import requests

BUMBLEBEE_API_URL = "https://bumblebee.example.org/api/v1"
BUMBLEBEE_API_TOKEN = "svc-..."


def bumblebee_api(path, **params):
    """Fetch all items from a paginated Bumblebee list endpoint."""
    url = BUMBLEBEE_API_URL.rstrip("/") + path
    headers = {"Authorization": f"Token {BUMBLEBEE_API_TOKEN}"}
    items = []
    while url:
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        items.extend(data["results"])
        url = data["next"]  # a complete URL, including the query string
        params = None
    return items


shelved = bumblebee_api("/desktops/", status="VM_Shelved")
recent_users = bumblebee_api("/users/", last_login__gte="2026-01-01")
```

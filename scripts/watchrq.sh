#!/bin/bash

#
# This script uses inotiftwait (from inotify-tools package) to watch for
# changes to the manage.py script, which is a symptom of the Django
# development server restarting from StatReloader.
#
# This will restart the bumblebee-rq-* services for you automatically
# when the Django development server reloads and watches the journal
#

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

journalctl --user -f -u 'bumblebee-rq*' &

while inotifywait -e close_nowrite $SCRIPT_DIR/../manage.py; do
    systemctl --user restart 'bumblebee-rq*'
    sleep 2
done

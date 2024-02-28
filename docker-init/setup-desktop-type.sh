#!/bin/sh

#
# If you're using our demo image, this will create the initial
# desktop type object for you in the database.
#
# You may need to edit the file first to set the correct flavor
# names for your environment. We've assumed m1.small and m1.medium
# are available.
#
# Also, make sure the docker stack is already running or you'll get
# a database connection error
#

FILE=initial_desktop_type.yaml

if [ -f $FILE ]; then
    docker-compose run --rm --no-deps -v $(pwd)/$FILE:/$FILE bumblebee django-admin loaddata /$FILE
else
	echo "$FILE not found"
fi

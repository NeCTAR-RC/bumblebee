#!/bin/bash -e

if [ -n "$DJANGO_MIGRATE" ]; then
  echo "** Starting Django migrate **"
  django-admin migrate
else
  echo "** Skipping Django migrate **"
fi

if [ -n "$DJANGO_COLLECT_STATIC" ]; then
  echo "** Starting Django collectstatic **"
  django-admin collectstatic --noinput
  echo "** Completed Django collectstatic **"

  echo "** Starting Django compress **"
  django-admin compress --force
  echo "** Completed Django collectstatic **"
else
  echo "** Skipping Django collectstatic/compress **"
fi

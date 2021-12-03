#!/bin/bash -e

if [ -n "$DJANGO_MIGRATE" ]; then
  echo "** Starting Django migrate **"
  django-admin migrate
else
  echo "** Skipping Django migrate **"
fi

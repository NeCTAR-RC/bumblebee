#!/bin/bash

if [ -f /vault/secrets/secret_envs ]; then
    echo "** Loading secrets from /vault/secrets/secret_envs **"
    . /vault/secrets/secret_envs
else
    echo "** Secrets not found! **"
fi

echo "** Starting rqscheduler **"
django-admin rqscheduler -i5

#!/bin/bash
[ -f /vault/secrets/secret_envs ] && . /vault/secrets/secret_envs
/usr/sbin/apache2ctl -D FOREGROUND

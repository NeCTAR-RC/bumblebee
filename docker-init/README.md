# 

# Keycloak initial config

This is to record the steps required to build the demo Bumblebee Keycloak realm, users and clients

```
docker run -d --name keycloak-setup -p 8180:8180 -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=admin quay.io/keycloak/keycloak:24.0 start-dev --http-port=8180

docker exec -it keycloak-setup /bin/bash

# Go to http://localhost:8180/ and make any Keycloak realm/user/client changes
# Log in
/opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8180/ --realm master --user admin --password admin
# Create realm
/opt/keycloak/bin/kcadm.sh create realms -b '{ "enabled": "true", "id": "bumblebee", "realm": "bumblebee"}'
# Create groups
/opt/keycloak/bin/kcadm.sh create realms/bumblebee/groups -b '{"name":"admin"}'
/opt/keycloak/bin/kcadm.sh create realms/bumblebee/groups -b '{"name":"staff"}'
# Create users
/opt/keycloak/bin/kcadm.sh create realms/bumblebee/users -b '{"enabled":true, "username":"admin","emailVerified": true, "email": "admin@example.com", "firstName": "Bumblebee", "lastName": "Admin", "groups": ["/admin"] }'
/opt/keycloak/bin/kcadm.sh set-password -r bumblebee --username admin --new-password password
/opt/keycloak/bin/kcadm.sh create realms/bumblebee/users -b '{"enabled":true, "username":"user","emailVerified": true, "email": "user@example.com", "firstName": "Bumblebee", "lastName":"User", "groups": [] }'
/opt/keycloak/bin/kcadm.sh set-password -r bumblebee --username user --new-password password
# Create Bumblebee client
BUMBLEBEECLIENT=$(/opt/keycloak/bin/kcadm.sh create realms/bumblebee/clients -i -b '{"enabled":true, "clientId":"bumblebee", "name": "Bumblebee", "protocol":"openid-connect", "clientAuthenticatorType": "client-secret", "secret": "00000000-0000-0000-0000-000000000000", "rootUrl" : "http://bumblebe:8080/", "redirectUris": ["/oidc/callback" ], "publicClient": false }')
/opt/keycloak/bin/kcadm.sh create realms/bumblebee/clients/${BUMBLEBEECLIENT}/roles -s name=admin
/opt/keycloak/bin/kcadm.sh create realms/bumblebee/clients/${BUMBLEBEECLIENT}/roles -s name=staff
/opt/keycloak/bin/kcadm.sh create realms/bumblebee/clients/${BUMBLEBEECLIENT}/protocol-mappers/models -i -b '{ "protocol":"openid-connect", "name": "groups", "protocolMapper": "oidc-group-membership-mapper", "config": { "full.path": false, "id.token.claim": true, "access.token.claim": true, "claim.name": "groups", "userinfo.token.claim": true } }'
# Create Guacamole client
GUACCLIENT=$(/opt/keycloak/bin/kcadm.sh create realms/bumblebee/clients -i -b '{"enabled":true, "clientId":"guacamole", "name": "Guacamole", "protocol":"openid-connect", "clientAuthenticatorType": "client-secret", "rootUrl" : "http://guacamole:9000/guacamole", "redirectUris" : [ "http://guacamole:9000/guacamole/*" ], "consentRequired" : false, "standardFlowEnabled" : false, "implicitFlowEnabled" : true, "directAccessGrantsEnabled" : false, "serviceAccountsEnabled" : false, "publicClient" : true }')

docker stop keycloak-setup
docker commit keycloak-setup keycloak-export
docker run -it --entrypoint sh keycloak-export

# In the container
/opt/keycloak/bin/kc.sh export --users realm_file --realm bumblebee --dir /tmp/export

CONTAINER=$(docker ps -a | awk '/keycloak-export/ {print $1}')

docker cp $CONTAINER:/tmp/export/bumblebee-realm.json .
docker rm -f $CONTAINER keycloak-setup
docker rmi keycloak-export
```

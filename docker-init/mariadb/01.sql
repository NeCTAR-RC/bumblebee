CREATE DATABASE `bumblebee`;
CREATE DATABASE `keycloak`;

CREATE USER 'keycloak'@'%' IDENTIFIED BY 'keycloak';
GRANT ALL PRIVILEGES ON keycloak.* TO 'keycloak'@'%';
FLUSH PRIVILEGES;

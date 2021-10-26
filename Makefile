NAME     := nectar/bumblebee
TAG      := $(shell git rev-parse --verify --short HEAD)
IMG      := ${NAME}:${TAG}
LATEST   := ${NAME}:latest
REGISTRY := registry.rc.nectar.org.au/${LATEST}


build:
	@docker build -t ${IMG} .
	@docker tag ${IMG} ${LATEST}
	@docker tag ${IMG} ${REGISTRY}

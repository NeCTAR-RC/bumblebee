PROJECT=bumblebee
REPO=registry.rc.nectar.org.au/nectar


DESCRIBE=$(shell git describe --tags --always)
IMAGE_TAG := $(if $(TAG),$(TAG),$(DESCRIBE))
IMAGE=$(REPO)/$(PROJECT):$(IMAGE_TAG)
BUILDER=docker
BUILDER_ARGS=

export DOCKER_BUILDKIT:=1

build:
	echo "Derived image tag: $(DESCRIBE)"
	echo "Actual image tag: $(IMAGE_TAG)"
	$(BUILDER) build $(BUILDER_ARGS) -t $(IMAGE) .

push:
	$(BUILDER) push $(IMAGE)

.PHONY: build push

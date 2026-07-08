DOCKER_IMAGE_NAME := sam-pipeline
DOCKER_IMAGE_TAG  ?= latest
SSH_PRIVATE_KEY   ?= $(HOME)/.ssh/id_rsa

.PHONY: install install-dev lint format type-check test docker-build docker-shell

install:
	python3 -m pip install .

install-dev:
	python3 -m pip install -e .[dev]

lint:
	python3 -m ruff check .
	python3 -m ruff format --check .

format:
	python3 -m ruff check --fix .
	python3 -m ruff format .

type-check:
	python3 -m mypy

test:
	python3 -m pytest

all: lint type-check test

docker-build:
	DOCKER_BUILDKIT=1 docker build \
		--build-arg DOCKER_IMAGE_TAG=$(DOCKER_IMAGE_TAG) \
		--tag $(DOCKER_IMAGE_NAME):$(DOCKER_IMAGE_TAG) \
		.

docker-shell:
	docker run -it --rm --entrypoint /bin/bash $(DOCKER_IMAGE_NAME):$(DOCKER_IMAGE_TAG)

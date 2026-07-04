DOCKER_IMAGE_NAME := sam-pipeline
DOCKER_IMAGE_TAG  ?= latest
SSH_PRIVATE_KEY   ?= $(HOME)/.ssh/id_rsa

.PHONY: install install-dev lint format type-check test docker-build docker-shell

install:
	pip install .

install-dev:
	pip install -e .[dev]

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

type-check:
	mypy

test:
	python -m pytest

all: lint type-check test

docker-build:
	DOCKER_BUILDKIT=1 docker build \
		--build-arg DOCKER_IMAGE_TAG=$(DOCKER_IMAGE_TAG) \
		--tag $(DOCKER_IMAGE_NAME):$(DOCKER_IMAGE_TAG) \
		.

docker-shell:
	docker run -it --rm --entrypoint /bin/bash $(DOCKER_IMAGE_NAME):$(DOCKER_IMAGE_TAG)

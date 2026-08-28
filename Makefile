.PHONY: install-tools install-requirements syntax validate test lint verify ping check apply benchmark-api

ANSIBLE_PLAYBOOK ?= ansible-playbook
ANSIBLE_GALAXY ?= ansible-galaxy
PYTHON ?= python3
ANSIBLE_ARGS ?=

install-tools:
	pipx install ansible-lint || pipx upgrade ansible-lint
	pipx install yamllint || pipx upgrade yamllint

install-requirements:
	$(ANSIBLE_GALAXY) collection install -r requirements.yml --force

syntax:
	$(ANSIBLE_PLAYBOOK) --syntax-check playbooks/setup.yml
	$(ANSIBLE_PLAYBOOK) --syntax-check playbooks/ping.yml

validate:
	$(ANSIBLE_PLAYBOOK) tests/validate_project.yml

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

lint:
	yamllint .
	ansible-lint

verify: syntax validate test lint

ping:
	$(ANSIBLE_PLAYBOOK) playbooks/ping.yml $(ANSIBLE_ARGS)

check:
	$(ANSIBLE_PLAYBOOK) --check --diff playbooks/setup.yml $(ANSIBLE_ARGS)

apply:
	$(ANSIBLE_PLAYBOOK) playbooks/setup.yml $(ANSIBLE_ARGS)

benchmark-api:
	$(PYTHON) scripts/benchmark_api.py

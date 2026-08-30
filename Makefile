.PHONY: install-tools install-requirements syntax validate lint verify ping check apply test-api benchmark-api benchmark-restore

ANSIBLE_PLAYBOOK ?= ansible-playbook
ANSIBLE_GALAXY ?= ansible-galaxy
ANSIBLE_ARGS ?=
BENCHMARK_ARGS ?=

install-tools:
	pipx install ansible-lint || pipx upgrade ansible-lint
	pipx install yamllint || pipx upgrade yamllint

install-requirements:
	$(ANSIBLE_GALAXY) collection install -r requirements.yml --force

syntax:
	$(ANSIBLE_PLAYBOOK) --syntax-check playbooks/setup.yml
	$(ANSIBLE_PLAYBOOK) --syntax-check playbooks/ping.yml
	$(ANSIBLE_PLAYBOOK) --syntax-check playbooks/test_api.yml
	$(ANSIBLE_PLAYBOOK) --syntax-check playbooks/benchmark.yml
	$(ANSIBLE_PLAYBOOK) --syntax-check playbooks/benchmark_restore.yml

validate:
	$(ANSIBLE_PLAYBOOK) tests/validate_project.yml

lint:
	yamllint .
	ansible-lint

verify: syntax validate lint

ping:
	$(ANSIBLE_PLAYBOOK) playbooks/ping.yml $(ANSIBLE_ARGS)

check:
	$(ANSIBLE_PLAYBOOK) --check --diff playbooks/setup.yml $(ANSIBLE_ARGS)

apply:
	$(ANSIBLE_PLAYBOOK) playbooks/setup.yml $(ANSIBLE_ARGS)

benchmark-api:
	$(ANSIBLE_PLAYBOOK) playbooks/benchmark.yml $(BENCHMARK_ARGS)

benchmark-restore:
	$(ANSIBLE_PLAYBOOK) playbooks/benchmark_restore.yml $(ANSIBLE_ARGS)

test-api:
	$(ANSIBLE_PLAYBOOK) playbooks/test_api.yml $(ANSIBLE_ARGS)

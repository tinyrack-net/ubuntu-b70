.PHONY: install-tools install-requirements syntax validate lint verify models require-model ping check apply test-api benchmark-api benchmark-restore

ANSIBLE_PLAYBOOK ?= ansible-playbook
ANSIBLE_GALAXY ?= ansible-galaxy
ANSIBLE_ARGS ?=
BENCHMARK_ARGS ?=
MODEL ?=
PROFILE_ARG = -e vllm_model_profile=$(MODEL)

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

models:
	@for profile in profiles/*/manifest.yml; do \
		slug=$$(sed -n 's/^slug: //p' "$$profile"); \
		served=$$(sed -n 's/^served_model_name: //p' "$$profile"); \
		printf '%-20s %s\n' "$$slug" "$$served"; \
	done

require-model:
	@test -n "$(MODEL)" || { echo 'MODEL is required (run: make models)' >&2; exit 2; }
	@printf '%s' "$(MODEL)" | grep -Eq '^[a-z0-9][a-z0-9.-]*$$' || { echo 'invalid MODEL slug' >&2; exit 2; }
	@test -f "profiles/$(MODEL)/manifest.yml" -a -f "profiles/$(MODEL)/compose.yml" || { echo 'unknown MODEL: $(MODEL)' >&2; exit 2; }

ping:
	$(ANSIBLE_PLAYBOOK) playbooks/ping.yml $(ANSIBLE_ARGS)

check: require-model
	$(ANSIBLE_PLAYBOOK) --check --diff playbooks/setup.yml $(PROFILE_ARG) $(ANSIBLE_ARGS)

apply: require-model
	$(MAKE) verify
	$(MAKE) ping
	$(MAKE) check MODEL=$(MODEL) ANSIBLE_ARGS='$(ANSIBLE_ARGS)'
	$(ANSIBLE_PLAYBOOK) playbooks/setup.yml $(PROFILE_ARG) $(ANSIBLE_ARGS)
	$(MAKE) test-api MODEL=$(MODEL) ANSIBLE_ARGS='$(ANSIBLE_ARGS)'

benchmark-api: require-model
	$(ANSIBLE_PLAYBOOK) playbooks/benchmark.yml $(PROFILE_ARG) $(BENCHMARK_ARGS)

benchmark-restore:
	$(ANSIBLE_PLAYBOOK) playbooks/benchmark_restore.yml $(ANSIBLE_ARGS)

test-api: require-model
	$(ANSIBLE_PLAYBOOK) playbooks/test_api.yml $(PROFILE_ARG) $(ANSIBLE_ARGS)

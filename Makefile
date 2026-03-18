ifeq ($(shell command -v docker-compose >/dev/null 2>&1 && echo yes),yes)
COMPOSE ?= docker-compose
else
COMPOSE ?= docker compose
endif

ifeq ($(shell id -u),0)
SUDO :=
else
SUDO ?= sudo
endif

PYTHON ?= /opt/conda/bin/python
RUN_WEB = $(SUDO) $(COMPOSE) run --rm web
RUN_WEB_LOCAL = $(SUDO) $(COMPOSE) -f docker-compose-develop.yml run --rm web

.PHONY: help \
	init init-local update \
	devel devel-build serve down test \
	rebuild-dashboard-qc-cache rebuild-dashboard-qc-cache-local \
	bootstrap-demo bootstrap-demo-local \
	manage migrate migrations migrate-local migrations-local \
	build build-local collectstatic collectstatic-local createsuperuser createsuperuser-local \
	schema showenv versions get-test-data reset_migrations \
	run

help:
	@printf "%s\n" \
	"Start here:" \
	"  make init                           First-time setup using the published image" \
	"  make init-local                     First-time setup using the local dev image" \
	"" \
	"Daily use:" \
	"  make devel                          Start the development stack on http://127.0.0.1:8000" \
	"  make devel-build                    Rebuild and start the development stack" \
	"  make serve                          Start the production-style stack on http://localhost:8080" \
	"  make down                           Stop development and production stacks" \
	"  make test                           Run the test suite in the test container" \
	"" \
	"Maintenance:" \
	"  make update                         Pull, rebuild, and migrate" \
	"  make bootstrap-demo-local           Seed the demo workspace in the dev stack" \
	"  make rebuild-dashboard-qc-cache-local ARGS=\"--project project-1\"" \
	"" \
	"Admin / Django:" \
	"  make manage CMD=\"showmigrations\"" \
	"  make migrations-local ARGS=maxquant" \
	"  make migrate-local" \
	"  make createsuperuser-local"

# First-time setup and updates
init:
	$(SUDO) $(COMPOSE) -f docker-compose.yml pull
	make migrations
	make migrations ARGS=user
	make migrations ARGS=maxquant
	make migrations ARGS=api
	make migrations ARGS=project
	make migrations ARGS=dashboards
	make migrate
	make createsuperuser
	make collectstatic
	make bootstrap-demo

init-local:
	make build-local
	make migrations-local
	make migrations-local ARGS=user
	make migrations-local ARGS=maxquant
	make migrations-local ARGS=api
	make migrations-local ARGS=project
	make migrations-local ARGS=dashboards
	make migrate-local
	make createsuperuser-local
	make collectstatic-local
	make bootstrap-demo-local

update:
	git pull --recurse-submodules
	make build
	make migrations
	make migrate

# Primary day-to-day workflow
devel:
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml down
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml up -d
	@echo "Waiting for dev server on http://127.0.0.1:8000 ..."
	@elapsed=0; i=0; \
	spinner='|/-\\'; \
	until curl -sf http://127.0.0.1:8000/ >/dev/null; do \
		c=$$(printf "%s" "$$spinner" | cut -c $$((i % 4 + 1))); \
		printf "\rStarting dev server... [%s] %ss elapsed" "$$c" "$$elapsed"; \
		sleep 2; \
		elapsed=$$((elapsed + 2)); \
		i=$$((i + 1)); \
	done; \
	printf "\rStarting dev server... [OK] %ss elapsed\n" "$$elapsed"
	@echo "Server is responding"
	@xdg-open http://127.0.0.1:8000 2>/dev/null || open http://127.0.0.1:8000 2>/dev/null || true
	@echo "Tailing web logs (Ctrl+C to stop logs; stack keeps running)..."
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml logs -f web celery

devel-build:
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml down
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml up -d --build
	@echo "Waiting for dev server on http://127.0.0.1:8000 ..."
	@elapsed=0; i=0; \
	spinner='|/-\\'; \
	until curl -sf http://127.0.0.1:8000/ >/dev/null; do \
		c=$$(printf "%s" "$$spinner" | cut -c $$((i % 4 + 1))); \
		printf "\rStarting dev server... [%s] %ss elapsed" "$$c" "$$elapsed"; \
		sleep 2; \
		elapsed=$$((elapsed + 2)); \
		i=$$((i + 1)); \
	done; \
	printf "\rStarting dev server... [OK] %ss elapsed\n" "$$elapsed"
	@echo "Server is responding"
	@xdg-open http://127.0.0.1:8000 2>/dev/null || open http://127.0.0.1:8000 2>/dev/null || true
	@echo "Tailing web logs (Ctrl+C to stop logs; stack keeps running)..."
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml logs -f web celery

serve:
	$(SUDO) $(COMPOSE) -f docker-compose.yml down
	$(SUDO) $(COMPOSE) -f docker-compose.yml up -d
	@echo "Waiting for server on http://localhost:8080 ..."
	@until curl -sf http://localhost:8080/ >/dev/null; do \
		sleep 2; \
	done
	@echo "Server is responding"
	@xdg-open http://localhost:8080 2>/dev/null || open http://localhost:8080 2>/dev/null || true
	@echo "Tailing web logs (Ctrl+C to stop logs; stack keeps running)..."
	$(SUDO) $(COMPOSE) -f docker-compose.yml logs -f web celery

down:
	$(SUDO) $(COMPOSE) down
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml down

test:
	$(SUDO) $(COMPOSE) -f docker-compose-test.yml run --rm web $(PYTHON) -m pytest

# Maintenance
bootstrap-demo:
	$(RUN_WEB) $(PYTHON) manage.py bootstrap_demo --user $${DEMO_USER:-user@email.com} --with-results

bootstrap-demo-local:
	$(RUN_WEB_LOCAL) $(PYTHON) manage.py bootstrap_demo --user $${DEMO_USER:-user@email.com} --with-results

rebuild-dashboard-qc-cache:
	$(RUN_WEB) $(PYTHON) manage.py rebuild_dashboard_qc_cache $(ARGS)

rebuild-dashboard-qc-cache-local:
	$(RUN_WEB_LOCAL) $(PYTHON) manage.py rebuild_dashboard_qc_cache $(ARGS)

# Examples:
# make rebuild-dashboard-qc-cache-local
# make rebuild-dashboard-qc-cache-local ARGS="--project project-1"
# make rebuild-dashboard-qc-cache-local ARGS="--project project-1 --pipeline pipeline-1"

# Django / admin tasks
manage:
	$(RUN_WEB) $(PYTHON) manage.py $(CMD)

migrate:
	$(RUN_WEB) $(PYTHON) manage.py migrate

migrations:
	$(RUN_WEB) $(PYTHON) manage.py makemigrations $(ARGS)

migrate-local:
	$(RUN_WEB_LOCAL) $(PYTHON) manage.py migrate

migrations-local:
	$(RUN_WEB_LOCAL) $(PYTHON) manage.py makemigrations $(ARGS)

createsuperuser:
	$(RUN_WEB) $(PYTHON) manage.py createsuperuser

createsuperuser-local:
	$(RUN_WEB_LOCAL) $(PYTHON) manage.py createsuperuser

collectstatic:
	$(RUN_WEB) $(PYTHON) manage.py collectstatic --noinput

collectstatic-local:
	$(RUN_WEB_LOCAL) $(PYTHON) manage.py collectstatic --noinput

# Build / inspection / maintenance
build:
	$(SUDO) $(COMPOSE) build

build-local:
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml build

schema:
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml run --rm web $(PYTHON) manage.py graph_models --arrow-shape normal -o schema.png -a

showenv:
	$(RUN_WEB) pip list

versions:
	$(SUDO) $(COMPOSE) run web conda env export -n base

reset_migrations:
	sudo find . -path "*/migrations/*.pyc" -delete
	sudo find . -path "*/migrations/*.py" -not -name "__init__.py" -delete

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

migrate: 
	$(SUDO) $(COMPOSE) run web python manage.py migrate

migrations: 
	$(SUDO) $(COMPOSE) run web python manage.py makemigrations $(ARGS)

run:
	$(SUDO) $(COMPOSE) down && $(SUDO) $(COMPOSE) up

serve:
	$(SUDO) $(COMPOSE) -f docker-compose.yml down
	$(SUDO) $(COMPOSE) -f docker-compose.yml up -d
	@echo "Waiting for server on http://localhost:8080 ..."
	@until curl -sf http://localhost:8080/ >/dev/null; do \
		sleep 2; \
	done
	@echo "server is responding"
	@xdg-open http://localhost:8080 2>/dev/null || open http://localhost:8080 2>/dev/null || true
	@echo "Tailing web logs (Ctrl+C to stop logs; stack keeps running)..."
	$(SUDO) $(COMPOSE) -f docker-compose.yml logs -f web celery

devel:
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml down
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml up -d
	@echo "Waiting for dev server on http://localhost:8000 ..."
	@until curl -sf http://localhost:8000/ >/dev/null; do \
		sleep 2; \
	done
	@echo "server is responding"
	@xdg-open http://localhost:8000 2>/dev/null || open http://localhost:8000 2>/dev/null || true
	@echo "Tailing web logs (Ctrl+C to stop logs; stack keeps running)..."
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml logs -f web celery

devel-build:
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml down
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml up -d --build
	@echo "Waiting for dev server on http://localhost:8000 ..."
	@until curl -sf http://localhost:8000/ >/dev/null; do \
		sleep 2; \
	done
	@echo "server is responding"
	@xdg-open http://localhost:8000 2>/dev/null || open http://localhost:8000 2>/dev/null || true
	@echo "Tailing web logs (Ctrl+C to stop logs; stack keeps running)..."
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml logs -f web celery

build:
	$(SUDO) $(COMPOSE) build

createsuperuser:
	$(SUDO) $(COMPOSE) run web python manage.py createsuperuser

collectstatic:
	$(SUDO) $(COMPOSE) run web python manage.py collectstatic

showenv:
	$(SUDO) $(COMPOSE) run web pip list

manage:
	$(SUDO) $(COMPOSE) run web python manage.py $(CMD)

reset_migrations:
	sudo find . -path "*/migrations/*.pyc"  -delete
	sudo find . -path "*/migrations/*.py" -not -name "__init__.py" -delete

init:
	make build
	make migrations
	make migrations ARGS=user
	make migrations ARGS=maxquant
	make migrations ARGS=api
	make migrations ARGS=project
	make migrations ARGS=dashboards
	make migrate
	make createsuperuser
	make collectstatic

update:
	git pull --recurse-submodules
	make build
	make migrations
	make migrate

down:
	$(SUDO) $(COMPOSE) down
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml down

test: 
	$(SUDO) $(COMPOSE) -f docker-compose-test.yml run web python manage.py test --noinput

get-test-data:
	gdown --folder https://drive.google.com/drive/folders/1kdQUXbr6DTBNLFBXLYrR_RLoXDFwCh_N?usp=sharing --output app/tests/data/D01

doc:
	mkdocs gh-deploy

schema:
	$(SUDO) $(COMPOSE) -f docker-compose-develop.yml run web python manage.py graph_models --arrow-shape normal -o schema.png -a 

versions:
	$(SUDO) $(COMPOSE) run web conda env export -n base

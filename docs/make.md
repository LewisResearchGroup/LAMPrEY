The Docker Compose setup starts the web application, PostgreSQL, Redis, and a Celery worker.

`make build` builds the Docker images.

`make migrations` creates Django migrations.

`make migrate` applies Django migrations.

`make createsuperuser` creates a Django superuser.

`make devel` starts the development stack on port `8000`.

`make serve` starts the production stack on port `8080`.

`make init` performs the full first-time setup.

`make init-local` performs the same setup using a local Docker build from `docker-compose-develop.yml`. Use it if the published image is unavailable.

`make down` stops both development and production stacks.

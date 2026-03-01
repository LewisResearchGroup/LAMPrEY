# Installation

## 1. Prerequisites

The supported setup is Docker-based. Install:

- Docker Engine
- Docker Compose, either as `docker-compose` or `docker compose`
- `make`
- `curl`
- `openssl`

The repository Makefile supports both Compose command styles. If your Docker setup requires elevated privileges, run the `make` targets with a user that can use `sudo`; otherwise they run without it. Docker installation instructions can be found in [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/).

## 2. Clone the repository

```bash
git clone --recursive git@github.com:LewisResearchGroup/ProteomicsQC.git ProteomicsQC
cd ProteomicsQC
```

This repository uses git submodules, so `--recursive` is required.

## 3. Generate the configuration

```bash
./scripts/generate_config.sh
```

This creates `.env` and the local data directories under `./data/`.

!!! note "Review the `.env` file"

    The generated file contains the required defaults:

    ```dotenv
    # OMICS PIPELINES CONFIG

    ## HOMEPAGE SETTINGS
    HOME_TITLE='Proteomics Pipelines'
    HOSTNAME=localhost
    ALLOWED_HOSTS=localhost
    CSRF_TRUSTED_ORIGINS=http://localhost
    OMICS_URL=http://localhost:8000

    ## STORAGE
    DATALAKE=./data/datalake
    COMPUTE=./data/compute
    MEDIA=./data/media
    STATIC=./data/static
    DB=./data/db

    ## EMAIL SETTINGS
    EMAIL_HOST=smtp.gmail.com
    EMAIL_USE_TLS=True
    EMAIL_USE_SSL=False
    EMAIL_PORT=587
    EMAIL_HOST_USER=''
    EMAIL_HOST_PASSWORD=''
    DEFAULT_FROM_EMAIL=''

    ## CELERY
    CONCURRENCY=8
    RESOURCE_RETRY_SECONDS=60
    MIN_FREE_MEM_GB_MAXQUANT=8
    MAX_LOAD_PER_CPU_MAXQUANT=0.85
    MIN_FREE_MEM_GB_RAWTOOLS=2
    MAX_LOAD_PER_CPU_RAWTOOLS=0.90

    ## RESULT STATUS (web UI responsiveness vs strictness)
    RESULT_STATUS_INSPECT_TIMEOUT_SECONDS=10.0
    RESULT_STATUS_PENDING_STALLED_WARNING_SECONDS=7200
    RESULT_STATUS_DONE_MTIME_SKEW_SECONDS=300
    RESULT_STATUS_MAXQUANT_STALE_SECONDS=21600
    RESULT_STATUS_RAWTOOLS_STALE_SECONDS=3600
    RESULT_STATUS_ACTIVITY_FALLBACK_SECONDS=300
    RESULT_STATUS_INSPECT_MAX_VISIBLE_RUNS=25
    RESULT_STATUS_INSPECT_MAX_ACTIVE_RUNS=12

    ## USERID
    UID=1000:1000

    ## SECURITY KEYS
    SECRET_KEY=...
    ```

Update these values before exposing the service outside your machine:

- `ALLOWED_HOSTS`: comma-separated hostnames or IPs Django should serve
- `CSRF_TRUSTED_ORIGINS`: full origins such as `https://proteomics.example.org`
- `OMICS_URL`: the base URL users actually open, for example `http://localhost:8080` in local production mode or your public `https://...` URL
- Email settings if you want outbound email
- Storage paths if you want data outside `./data`

The queue is resource-aware. Before each task starts, the Celery worker checks host load and available memory. If thresholds are exceeded, the task is deferred and retried after `RESOURCE_RETRY_SECONDS`.

For large pipelines, tune result-status responsiveness via:

- `RESULT_STATUS_INSPECT_MAX_VISIBLE_RUNS`
- `RESULT_STATUS_INSPECT_MAX_ACTIVE_RUNS`

Lower values reduce expensive queue inspection and keep the UI responsive on large run lists.

## 4. First-time run

Run:

```bash
make init
```

`make init` performs the full first-run setup:

- builds the Docker images
- creates and applies Django migrations
- prompts you to create a superuser
- runs `collectstatic`

This is the command to use on a clean installation.

## 5. Start the application

For development:

```bash
make devel
```

This starts the Django development server on [http://localhost:8000](http://localhost:8000).

For production-style local serving:

```bash
make serve
```

This starts the production stack on [http://localhost:8080](http://localhost:8080).

After startup, log in at [http://localhost:8000/admin](http://localhost:8000/admin) for development or [http://localhost:8080/admin](http://localhost:8080/admin) for production.

To stop the containers:

```bash
make down
```

## 6. Production notes

### Exposing the service
`make serve` publishes the application on port `8080`. If you want to expose it on a real domain, place a reverse proxy such as NGINX in front of it and forward external traffic on ports `80` or `443` to port `8080`.

In production, Django does not serve static files directly. `make init` already runs `collectstatic` for the first deployment. Run `make collectstatic` again after static asset changes before restarting the production stack.

### Rebuild versus restart

`make devel` reuses the existing development image. Use it for normal development when only application code changes.

If you change `requirements.txt`, `dockerfiles/Dockerfile`, or dependency pins that affect the runtime environment, rebuild the development image:

```bash
make devel-build
```

This forces Docker to rebuild the image so installed packages match the repository state.

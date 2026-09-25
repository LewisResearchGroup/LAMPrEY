# Deployment and Runtime Considerations

This section summarizes the operational characteristics of LAMPrEY for manuscript or reviewer-facing descriptions. It is intentionally higher level than the installation guide, while retaining the details needed to evaluate installation, configuration, scalability, runtime behavior, and failure handling in a large-scale proteomics setting.

## Installation

LAMPrEY is distributed as a Docker-based application so that the web server, database, queue broker, and worker environment can be reproduced across laboratory servers. A standard installation requires Docker Engine, Docker Compose, `git-lfs`, and `make`. Git LFS is used because the repository includes the default MaxQuant executable bundle. First-run setup is automated through `make init`, which pulls the published container image, applies database migrations, creates the first administrative account, collects static assets, and seeds demonstration data. If the published image is not accessible, `make init-local` performs the same initialization using a locally built image.

The production-style stack runs on port `8080` and is intended to sit behind an institutional reverse proxy such as NGINX, with HTTPS termination at the proxy. Persistent data are mounted outside the container under host-controlled paths, which allows application containers to be recreated without losing uploads, search outputs, or database state.

## Configuration

Configuration is generated into a local `.env` file by `scripts/generate_config.sh`. The main deployment settings include the public hostname, allowed Django hosts, CSRF-trusted origins, application URL, email settings, and persistent storage locations. The default storage layout separates the input datalake, compute workspace, media files, static assets, and PostgreSQL data directory.

For pipeline reproducibility, each project/pipeline stores its configuration files, including `mqpar.xml` and FASTA input, alongside the uploaded RAW files and generated outputs. The default MaxQuant version is configurable, and LAMPrEY selects the runtime automatically: older MaxQuant executables are run through `mono`, while newer .NET-based versions can be run through `dotnet`. This can be overridden through environment variables when a deployment has site-specific runtime requirements.

## Scalability

LAMPrEY separates interactive web requests from compute-heavy proteomics processing. The web application handles authentication, project access, uploads, run management, API requests, and dashboard rendering. MaxQuant, RawTools, and picked-group FDR jobs are submitted to Celery workers through Redis and execute asynchronously. This architecture allows multiple RAW files to be queued without blocking the user interface.

Scalability is controlled through worker concurrency and resource-aware scheduling. The `CONCURRENCY` setting controls the number of Celery worker slots. Before launching MaxQuant or RawTools, the worker checks available memory and normalized CPU load. If the server is under pressure, the task is deferred and retried after `RESOURCE_RETRY_SECONDS` instead of starting another expensive process. Separate thresholds are available for MaxQuant and RawTools because their memory and CPU profiles differ.

The dashboard is designed for repeated cohort-level review rather than repeated parsing of raw output tables on every page load. Per-run QC data are cached as JSON, pipeline-level dashboard scopes are cached separately, and protein-group data are materialized into Parquet files for faster downstream reads. Cache invalidation is based on source file modification times, so updated MaxQuant, RawTools, or picked-group FDR outputs are reflected without requiring manual data rebuilding. A management command is available to rebuild dashboard QC caches explicitly when needed.

For large run lists, queue-status inspection is adaptive. Small pages use stricter Celery worker inspection, while larger pages reduce broker inspection in the request/response path. This keeps the pipeline page responsive when many runs are visible or many jobs have already been submitted.

## Runtime Performance

Runtime is dominated by the external search and QC tools rather than by the Django application. In practice, MaxQuant execution time depends on RAW file size, acquisition method, database size, mqpar settings, CPU availability, storage throughput, and worker concurrency. RawTools stages are typically lighter, but still run asynchronously so that uploads and review workflows remain responsive.

The repository includes seeded demonstration outputs for three runs. These include MaxQuant `time.txt` files of approximately 18.5-19.5 minutes, along with expected MaxQuant and RawTools output artifacts. These demo files are useful for validating application behavior and documentation examples, but they should not be interpreted as a formal benchmark for new instruments or large cohorts. For publication, the more defensible performance claim is that LAMPrEY preserves interactivity by decoupling user-facing workflows from batch processing, limiting work started under high resource pressure, caching dashboard-ready summaries, and using Parquet for repeated protein-level access.

## Failure Handling

LAMPrEY records task identifiers, submission times, process IDs, and process group IDs for each processing stage. Each run is evaluated stage-by-stage with explicit statuses for queued, running, done, failed, canceled, and missing output. Status evaluation combines Celery task state, expected output markers, error files, and recent filesystem activity. This avoids treating transient queue or broker states as data loss and helps identify genuinely stalled or incomplete runs.

External commands are launched through a cancel-aware process runner. If a user cancels a run, the worker checks for the cancellation request during execution, terminates the process group with `SIGTERM`, escalates to `SIGKILL` after a grace period if needed, and clears the stored process-tracking fields. The run table exposes requeue, cancel, and delete actions according to user permissions.

Errors are persisted in stage-specific log files, including `maxquant.err`, `rawtools_metrics.err`, and `rawtools_qc.err`. The run detail page extracts compact error summaries from these files so users can distinguish configuration problems, tool failures, canceled jobs, and missing outputs. MaxQuant parse failures are also written back to the stage error log. For picked-group FDR, LAMPrEY writes a manifest for each run attempt, records included and excluded inputs, stores generated artifacts, and updates pipeline-level status and error summaries if the task fails.

Access control is project scoped. Non-administrative users can only view projects assigned to them and can only mutate their own runs. The authenticated API follows the same project and run ownership rules, supporting automation without bypassing web-application permissions.

## Suggested Manuscript Wording

LAMPrEY was deployed as a containerized Django application with PostgreSQL for metadata storage, Redis/Celery for asynchronous job orchestration, and host-mounted persistent storage for input data, compute outputs, media, and static assets. Installation is automated through Docker Compose and a generated environment file that captures hostnames, storage locations, email settings, worker concurrency, resource thresholds, and result-status tuning. Each pipeline stores its analysis configuration, including MaxQuant parameters and FASTA files, with the corresponding project data to support reproducible processing.

For large-scale deployment, user-facing web/API operations are decoupled from compute-intensive proteomics processing. RAW-file submissions create queued MaxQuant and RawTools tasks, while workers launch external tools only when memory and CPU-load thresholds are satisfied. Cohort-level review is accelerated by cached run-level QC summaries, cached pipeline-level dashboard scopes, and Parquet materialization of protein-group data. Runtime therefore scales primarily with the underlying search/QC tools and the configured worker resources, while the web interface remains responsive during batch processing.

Failure handling is implemented at the run and stage level. LAMPrEY tracks Celery task IDs, process IDs, process groups, submission times, expected output markers, error logs, and recent filesystem activity to distinguish queued, running, completed, failed, canceled, and incomplete runs. Canceled external processes are terminated at the process-group level, failures are preserved in stage-specific logs and summarized in the interface, and runs can be requeued after correction of configuration or resource problems. Project-scoped authentication and API permissions preserve the same access boundaries for interactive and scripted use.

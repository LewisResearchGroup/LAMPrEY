# Demo data

LAMPrEY ships with a seeded demo so a fresh installation is immediately usable after installation.

The demo is created by the `bootstrap_demo` management command, which is invoked automatically during first-time setup.

![](img/demo_home.png)

## What the demo includes

- a demo project with a seeded pipeline named `TMT QC Demo`
- bundled pipeline configuration from `app/seed/demo/`
- three pre-generated demo runs
- minimal MaxQuant, RawTools metrics, and RawTools QC outputs required for the UI and dashboard

The bundled assets are intentionally small. They are meant to support onboarding and interface exploration, not to act as a full raw-data archive.

## What the demo is for

Use the demo to:

- verify that the installation completed successfully
- understand the overall architecture before configuring your own environment
- move through the main application sections with safe seeded data
- open the dashboard and inspect seeded QC behavior without uploading anything

## Explore the demo

After first-time setup, the demo is the easiest way to understand the application without creating any new resources.

Use it as a guided tour, not as the full explanation of each component.

For the detailed behavior of each area, use the linked documentation pages rather than treating this page as the full reference.

### Projects page

Start from the project list and open the seeded demo project.

For the full description of the project and pipeline workflow, see [Main](main.md).

![](img/demo_projects.png)

### Pipeline page

Inside the demo project, open the `TMT QC Demo` pipeline to see the seeded runs and the standard pipeline workflow.

For the full description of this operational view, see [Main](main.md).

![](img/demo_pipelines.png)

### Upload page

The demo pipeline also shows the upload area, but it is intentionally disabled because the seeded pipeline is read-only.

For pipeline configuration and upload setup, see [Admin panel](how-to-access-the-admin-panel.md) and [Main](main.md).

![](img/demo_uploads.png)

### Results pages

Open any seeded run from the pipeline table to inspect the run-level outputs.

For run-level navigation and result pages, see [Main](main.md). For cross-run analytical views, see [Dashboard](dashboard.md).

![](img/demo_results.png)

## Use the demo with the architecture in mind

The demo is most useful as a lightweight tour of the platform structure:

- **Admin panel**: configures users, projects, pipelines, and pipeline inputs
- **Main**: handles projects, pipelines, uploads, and run-level results
- **Dashboard**: compares and reviews runs across a pipeline

Use these pages for the detailed documentation:

- [Admin panel](how-to-access-the-admin-panel.md)
- [Main](main.md)
- [Dashboard](dashboard.md)

## Important limitations

The seeded demo pipeline is read-only.

- uploads are blocked on the demo pipeline
- demo runs cannot be requeued as normal uploaded runs
- to process your own `.raw` files, create or use a non-demo pipeline

This is intentional. The demo exists to provide a stable first-run experience and to avoid mutating the shipped example dataset.

## Rebuild or refresh the demo

If you want to seed the demo again manually, run:

<div class="termy">

```console
$ make bootstrap-demo

// Or use the development-stack variant
$ make bootstrap-demo-local
```

</div>

Both commands call Django's `bootstrap_demo` management command with `--with-results`, so the seeded runs include ready-to-browse result data.

## Demo storage

The source assets live in `app/seed/demo/` and include:

- `config/`: demo `mqpar.xml` and `fasta.faa`
- `runs/demo_01..demo_03/maxquant/`: minimal MaxQuant outputs
- `runs/demo_01..demo_03/rawtools/`: RawTools metrics and chromatograms
- `runs/demo_01..demo_03/rawtools_qc/`: RawTools QC outputs
- `manifest.json`: the ordered list of seeded demo runs and displayed raw-file names

For implementation details, see `app/seed/demo/README.md`.

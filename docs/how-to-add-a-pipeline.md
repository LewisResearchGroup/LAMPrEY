# How to create a new pipeline?

A pipeline defines the processing steps for raw data files. Each pipeline belongs to a project and can be configured with specific parameters and input files for [Maxquant](https://maxquant.org/) and [RawTools](https://github.com/kevinkovalchik/RawTools). To add a new pipeline, you need to have at least one project set up in the system. If you haven't created a project yet, please refer to [Create a project](how-to-add-a-project.md) before proceeding.

![](img/admin-panel.png)

Click on the `+ Add` button beside `Pipelines` to open the pipeline creation form:

![](img/admin-add-pipeline.png)

Fill in the editable fields and upload the required configuration:

1. Select the MaxQuant version. If no explicit version is selected, the default bundled version (2.4.12.0) is used.
2. Add a `FASTA` file with the target protein sequences.
3. Add an `mqpar.xml` file generated with MaxQuant. If no explicit mqpar.xml is submitted, the default mqpar.xml file for bundled version (2.4.12.0) is used. For template requirements such as the single-RAW assumption and placeholder handling, see [How to prepare `mqpar.xml`](how-to-prepare-mqpar.md).
4. Provide command-line parameters for [RawTools](https://github.com/kevinkovalchik/RawTools). Read [RawTools help](https://github.com/kevinkovalchik/RawTools/wiki/Run-RawTools-for-parsing-and-quantification-for-Linux) for the supported arguments.

## Using a different MaxQuant version

The pipeline form only lets you choose from MaxQuant executables that are already installed on the server. The bundled `2.4.12.0` version is available automatically, but any other version must be added first by a server operator.

LAMPrEY scans the compute storage root recursively for files matching:

- `*MaxQuantCmd.exe`
- `*MaxQuantCmd.dll`

In the standard containerized deployment, that means the executable must live somewhere under:

- `/compute/`

In the default local development setup from `.env`, that maps to:

- `./data/compute/`

The recommended layout is:

```text
/compute/software/MaxQuant/MaxQuant_v_<version>/MaxQuantCmd.exe
```

or for newer .NET builds:

```text
/compute/software/MaxQuant/MaxQuant_v_<version>/bin/MaxQuantCmd.dll
```

Example of the default bundled version:

```text
/compute/software/MaxQuant/MaxQuant_v_2.4.12.0/MaxQuantCmd.exe
/compute/software/MaxQuant/MaxQuant_v_2.4.12.0/bin/MaxQuantCmd.dll
```

Current behavior:

1. Install or extract the desired MaxQuant release on the server so that its `MaxQuantCmd.exe` or `MaxQuantCmd.dll` exists somewhere under `/compute/` (or `./data/compute/` in a local non-container setup).
2. Re-open the pipeline form. The executable should now appear in the **MaxQuant version** dropdown.
3. Select that version and upload an `mqpar.xml` generated with the same MaxQuant release.

If the version does not appear in the dropdown, it is not installed in a location LAMPrEY scans yet.

For runtime details, see [MaxQuant](maxquant.md): versions earlier than `2.6` run through `mono`, while versions `2.6` and newer run through `dotnet`.

After saving the pipeline:

- project members can upload `.raw` files to it from the pipeline page or via the API
- each uploaded file creates an independent run, even when the displayed filename matches a previous upload
- the seeded demo pipeline is read-only and blocks new uploads

# How to prepare `mqpar.xml` for a pipeline?

LAMPrEY can use a custom `mqpar.xml`, but the file must follow a few rules so the server can turn it into a reusable single-run template.

If you do not upload a custom file, the application uses the bundled `mqpar_2.4.12.0.xml` template built to work with MaxQuant v2.4.12.0 automatically.

## Recommended workflow

1. Open MaxQuant locally.
2. Configure the search with one representative `.raw` file.
3. Set the FASTA file and all other search parameters as desired.
4. Export `mqpar.xml`.
5. Check that the file contains only one raw-file entry and one experiment entry.
6. Upload it when creating the pipeline in LAMPrEY.

## When to avoid a custom file

Use the bundled default template when:

- you are using the recommended bundled MaxQuant version
- you do not need custom search settings
- you want the lowest-friction setup path


## Core requirement

Create the `mqpar.xml` in MaxQuant with exactly one representative `.raw` file loaded.

LAMPrEY rewrites that single-run template at runtime for each uploaded file. The code path expects one raw-file entry only.

## Required placeholders

The uploaded template must be convertible into this pattern:

```xml
<fastaFiles>
  <FastaFileInfo>
    <fastaFilePath>__FASTA__</fastaFilePath>
  </FastaFileInfo>
</fastaFiles>
...
<filePaths>
  <string>__RAW__</string>
</filePaths>
...
<experiments>
  <string>__LABEL__</string>
</experiments>
```

What each placeholder means:

- `__FASTA__`: LAMPrEY replaces __FASTA__ with the pipeline FASTA file path
- `__RAW__`: LAMPrEY replaces __RAW__ with the current uploaded raw file path
- `__LABEL__`: LAMPrEY replaces __LABEL__ with the run label used for the sample

When you upload a normal single-run `mqpar.xml`, LAMPrEY converts the FASTA entry, the raw-file entry, and the experiment entry into these placeholders automatically.

## Important constraints

### 1. Use a single RAW file

Do not export an `mqpar.xml` with multiple raw-file entries.

LAMPrEY's template conversion checks the file and expects exactly one `<string>...raw</string>` entry in `<filePaths>`.

### 2. Do not hard-code the production FASTA path

The FASTA path must be replaceable by the pipeline FASTA file. In the bundled example, this is:

```xml
<fastaFilePath>__FASTA__</fastaFilePath>
```

### 3. Keep the file-path section simple

The bundled example uses:

```xml
<filePaths>
  <string>__RAW__</string>
</filePaths>
```

That is the expected single-file pattern for a LAMPrEY pipeline template.

### 4. Keep experiment labels template-friendly

The bundled example uses:

```xml
<experiments>
  <string>__LABEL__</string>
</experiments>
```

LAMPrEY converts the single experiment entry into `__LABEL__`, then replaces that value per run so the generated MaxQuant run uses the correct label.

## Example from `mqpar_2.4.12.0.xml`

The repository example at `mqpar_2.4.12.0.xml` already shows the required structure:

- `<fastaFilePath>__FASTA__</fastaFilePath>`
- `<string>__RAW__</string>` inside `<filePaths>`
- `<string>__LABEL__</string>` inside `<experiments>`
- a single fraction entry
- a single parameter-group index

These sections are what make the file usable as a reusable pipeline template instead of a one-off local MaxQuant run file.

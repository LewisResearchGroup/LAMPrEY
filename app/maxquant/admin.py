from django import forms
from django.contrib import admin, messages
from django.conf import settings
from pathlib import Path

from .models import (
    Pipeline,
    RawFile,
    Result,
)
from .defaults import ensure_bundled_maxquant_installed


def _read_upload_head(upload, size=4096):
    if not upload:
        return ""

    try:
        position = upload.tell()
    except (AttributeError, OSError):
        position = None

    try:
        chunk = upload.read(size)
    finally:
        if position is not None:
            upload.seek(position)

    if isinstance(chunk, bytes):
        return chunk.decode("utf-8", errors="ignore")
    return chunk or ""


def _read_path_head(path, size=4096):
    candidate = Path(path)
    if not candidate.is_file():
        return ""

    with candidate.open("rb") as handle:
        chunk = handle.read(size)

    return chunk.decode("utf-8", errors="ignore")


def _first_nonempty_line(text):
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _looks_like_mqpar(text):
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "<?xml",
            "<maxquantparams",
            "<fastafiles>",
            "<filepaths>",
            "<experiments>",
        )
    )


def _looks_like_fasta(text):
    first_line = _first_nonempty_line(text)
    if not first_line.startswith(">"):
        return False
    return len(first_line) > 1


def _mqpar_warning_message(text):
    if not text:
        return None
    if _looks_like_fasta(text):
        return (
            "MQPAR upload warning: this file looks like a FASTA file, not an mqpar.xml file. "
            "The pipeline was saved, but MaxQuant may fail unless you replace the mqpar upload."
        )
    if not _looks_like_mqpar(text):
        return (
            "MQPAR upload warning: this file does not look like a valid mqpar.xml file. "
            "The pipeline was saved, but MaxQuant may fail unless you replace the mqpar upload."
        )
    if "<maxquantparams" not in text.lower():
        return (
            "MQPAR upload warning: this XML file does not look like an mqpar.xml file with a "
            "<MaxQuantParams> root element. The pipeline was saved, but MaxQuant may fail unless "
            "you replace the mqpar upload."
        )
    return None


def _fasta_warning_message(text):
    if not text:
        return None
    if _looks_like_mqpar(text):
        return (
            "FASTA upload warning: this file looks like an mqpar.xml file, not a FASTA file. "
            "The pipeline was saved, but downstream runs may fail unless you replace the FASTA upload."
        )
    if not _looks_like_fasta(text):
        return (
            "FASTA upload warning: this file does not look like a FASTA file. Expected the first "
            "non-empty line to start with '>'. The pipeline was saved, but downstream runs may fail "
            "unless you replace the FASTA upload."
        )
    return None


def _pipeline_file_warnings(pipeline):
    warnings = []

    mqpar_warning = _mqpar_warning_message(_read_path_head(pipeline.mqpar_path))
    if mqpar_warning:
        warnings.append(mqpar_warning)

    fasta_warning = _fasta_warning_message(_read_path_head(pipeline.fasta_path))
    if fasta_warning:
        warnings.append(fasta_warning)

    return warnings


class PipelineAdminForm(forms.ModelForm):
    class Meta:
        model = Pipeline
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.upload_warnings = []

    def clean(self):
        cleaned_data = super().clean()
        self.upload_warnings = []
        fasta_file = cleaned_data.get("fasta_file")
        has_existing_fasta = bool(
            self.instance and self.instance.pk and self.instance.fasta_path.is_file()
        )

        if not fasta_file and not has_existing_fasta:
            self.add_error(
                "fasta_file",
                (
                    "A FASTA file is required to create a runnable pipeline. "
                    "Browsers clear selected file inputs after validation errors, "
                    "so if another field fails validation you must choose the FASTA file again."
                ),
            )

        mqpar_file = cleaned_data.get("mqpar_file")
        if mqpar_file:
            mqpar_warning = _mqpar_warning_message(_read_upload_head(mqpar_file))
            if mqpar_warning:
                self.upload_warnings.append(mqpar_warning)

        if fasta_file:
            fasta_warning = _fasta_warning_message(_read_upload_head(fasta_file))
            if fasta_warning:
                self.upload_warnings.append(fasta_warning)

        return cleaned_data


class RawFileAdmin(admin.ModelAdmin):
    model = RawFile

    exclude = ("md5sum", "slug")
    list_per_page = 20

    list_display = (
        "display_name",
        "owner",
        "project",
        "pipeline",
        "use_downstream",
        "flagged",
        "path",
        "created",
    )

    sortable_by = (
        "created",
        "pipeline",
        "orig_file",
        "use_downstream",
        "flagged",
        "created_by",
    )

    list_filter = ()

    search_fields = ("orig_file", "pipeline__name", "pipeline__project__name", "created_by__email")

    group_by = "pipeline"

    ordering = ("-created",)

    actions = (
        "allow_use_downstream",
        "prevent_use_downstream",
        "flag_selected",
        "unflag_selected",
        "save_and_run",
    )

    class Media:
        css = {"all": ("css/admin-shared-changelist.css",)}

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related("pipeline__project", "created_by")

    @admin.display(ordering="pipeline__project__name", description="Project")
    def project(self, obj):
        return obj.pipeline.project

    @admin.display(ordering="orig_file", description="Name")
    def display_name(self, obj):
        return f"{obj.logical_name} ({obj.display_ref})"

    @admin.display(ordering="created_by__email", description="User")
    def owner(self, obj):
        return obj.created_by

    def regroup_by(self):
        return "pipeline"

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ["path", "pipeline", "created", "orig_file"]
        else:
            return ["path", "created"]

    def prevent_use_downstream(modeladmin, request, queryset):
        queryset.update(use_downstream=False)

    def allow_use_downstream(modeladmin, request, queryset):
        queryset.update(use_downstream=True)

    @admin.action(description="Flag selected raw files")
    def flag_selected(modeladmin, request, queryset):
        queryset.update(flagged=True)

    @admin.action(description="Unflag selected raw files")
    def unflag_selected(modeladmin, request, queryset):
        queryset.update(flagged=False)

    def save_and_run(modeladmin, request, queryset):
        for raw_file in queryset:
            raw_file.save()


class PipelineAdmin(admin.ModelAdmin):
    form = PipelineAdminForm

    ordering = ("name",)

    list_filter = ()

    list_display = ("name", "project", "created", "created_by")
    search_fields = ("name", "project__name", "created_by__email", "description")

    sortable_by = ("name", "created", "pipeline")

    fieldsets = (
        (None, {"fields": ("project", "name", "created", "created_by", "description")}),
        (
            "MaxQuant",
            {
                "fields": (
                    "maxquant_executable",
                    "mqpar_file",
                    "download_mqpar",
                    "fasta_file",
                    "download_fasta",
                )
            },
        ),
        ("RawTools", {"fields": ("rawtools_args",)}),
        ("Info", {"fields": ("slug", "uuid", "path", "fasta_path", "mqpar_path")}),
    )

    def _default_pipeline_name(self):
        index = 1
        while True:
            candidate = f"Pipeline {index}"
            if not Pipeline.objects.filter(name=candidate).exists():
                return candidate
            index += 1

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)

        ensure_bundled_maxquant_installed()

        if not initial.get("maxquant_executable"):
            initial["maxquant_executable"] = settings.DEFAULT_MAXQUANT_EXECUTABLE

        if not initial.get("name"):
            initial["name"] = self._default_pipeline_name()

        if not initial.get("description"):
            initial["description"] = (
                "Describe the pipeline purpose, processing settings, and sample scope."
            )

        return initial

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "maxquant_executable":
            ensure_bundled_maxquant_installed()
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)

        if db_field.name == "project" and hasattr(formfield.widget, "can_add_related"):
            formfield.widget.can_add_related = False
            formfield.widget.can_change_related = False
            formfield.widget.can_delete_related = False
            formfield.widget.can_view_related = False

        if db_field.name == "maxquant_executable":
            choices = []
            for value, label in formfield.choices:
                if value == settings.DEFAULT_MAXQUANT_EXECUTABLE:
                    label = settings.DEFAULT_MAXQUANT_LABEL
                choices.append((value, label))
            formfield.choices = choices
            formfield.help_text = (
                "Bundled MaxQuant 2.4.12.0 is installed automatically and recommended. "
                "Choose a different installed executable only if needed."
            )

        if db_field.name == "mqpar_file":
            formfield.help_text = (
                "Leave this empty to use the bundled mqpar_2.4.12.0.xml template that matches "
                "the recommended MaxQuant version. Upload a file only to override it. "
                "The form performs a basic content check and warns if the upload does not look "
                "like a MaxQuant parameter XML file."
            )

        if db_field.name == "fasta_file":
            formfield.help_text = (
                "Required. If the form fails validation for any reason, browsers clear file "
                "inputs, so you must select the FASTA file again before saving. "
                "The form also checks that the uploaded file looks like a FASTA file."
            )

        return formfield

    def get_fieldsets(self, request, obj=None):
        if obj is not None:
            return super().get_fieldsets(request, obj)

        return (
            (None, {"fields": ("project", "name", "created", "created_by", "description")}),
            (
                "MaxQuant",
                {
                    "fields": (
                        "maxquant_executable",
                        "mqpar_file",
                        "fasta_file",
                    )
                },
            ),
            ("RawTools", {"fields": ("rawtools_args",)}),
            ("Info", {"fields": ("slug", "uuid", "path", "fasta_path", "mqpar_path")}),
        )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return (
                "created",
                "created_by",
                "slug",
                "uuid",
                "path",
                "fasta_path",
                "mqpar_path",
                "download_fasta",
                "download_mqpar",
                "project",
            )
        else:
            return (
                "created",
                "created_by",
                "slug",
                "uuid",
                "path",
                "fasta_path",
                "mqpar_path",
                "download_fasta",
                "download_mqpar",
            )

    class Media:
        css = {"all": ("css/admin-shared-changelist.css",)}

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        for warning in getattr(form, "upload_warnings", ()):
            self.message_user(request, warning, level=messages.WARNING)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)

        if request.method == "GET":
            obj = self.get_object(request, object_id)
            if obj is not None:
                for warning in _pipeline_file_warnings(obj):
                    self.message_user(request, warning, level=messages.WARNING)

        return response


class ResultAdmin(admin.ModelAdmin):
    list_per_page = 20

    readonly_fields = (
        "raw_file",
        "created",
        "created_by",
        "path",
        "link",
        "run_dir",
        "raw_fn",
        "mqpar_fn",
        "fasta_fn",
        "pipeline",
        "parquet_path",
        "create_protein_quant",
        "n_files_maxquant",
        "n_files_rawtools_metrics",
        "n_files_rawtools_qc",
        "maxquant_execution_time",
        "project",
        "maxquant_errors",
        "rawtools_qc_errors",
        "rawtools_metrics_errors",
        "download_raw",
    )

    list_display = (
        "display_name",
        "owner",
        "project",
        "pipeline",
        "n_files_maxquant",
        "n_files_rawtools_metrics",
        "n_files_rawtools_qc",
        "status_protein_quant_parquet",
        "maxquant_execution_time",
        "created",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "project",
                    "pipeline",
                    "created",
                    "raw_file",
                    "created_by",
                    "link",
                    "download_raw",
                )
            },
        ),
        ("Paths", {"fields": ("raw_fn", "mqpar_fn", "fasta_fn", "run_dir", "path")}),
        (
            "Info",
            {
                "fields": (
                    "n_files_maxquant",
                    "maxquant_execution_time",
                    "n_files_rawtools_metrics",
                    "n_files_rawtools_qc",
                )
            },
        ),
        (
            "Errors",
            {
                "fields": (
                    "maxquant_errors",
                    "rawtools_qc_errors",
                    "rawtools_metrics_errors",
                )
            },
        ),
    )

    ordering = ("-created",)

    list_filter = ()

    search_fields = (
        "raw_file__orig_file",
        "raw_file__pipeline__name",
        "raw_file__pipeline__project__name",
        "created_by__email",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related("raw_file__pipeline__project", "created_by")

    def download_raw(self, obj):
        return obj.raw_file.download

    def project(self, obj):
        return obj.raw_file.pipeline.project

    @admin.display(ordering="raw_file__orig_file", description="Name")
    def display_name(self, obj):
        return f"{obj.raw_file.logical_name} ({obj.raw_file.display_ref})"

    @admin.display(ordering="created_by__email", description="User")
    def owner(self, obj):
        return obj.created_by

    def regroup_by(self):
        return ("project", "pipeline")

    def rerun_maxquant(modeladmin, request, queryset):
        for mq_run in queryset:
            mq_run.run_maxquant(rerun=True)

    def rerun_rawtools(modeladmin, request, queryset):
        for mq_run in queryset:
            mq_run.run_rawtools_metrics(rerun=True)
            mq_run.run_rawtools_qc(rerun=True)

    def rerun_rawtools_qc(modeladmin, request, queryset):
        for mq_run in queryset:
            mq_run.run_rawtools_qc(rerun=True)

    def rerun_rawtools_metrics(modeladmin, request, queryset):
        for mq_run in queryset:
            mq_run.run_rawtools_metrics(rerun=True)

    def start_maxquant(modeladmin, request, queryset):
        for mq_run in queryset:
            mq_run.run_maxquant(rerun=False)

    def start_rawtools(modeladmin, request, queryset):
        for mq_run in queryset:
            mq_run.run_rawtools_qc(rerun=False)
            mq_run.run_rawtools_metrics(rerun=False)

    def start_all(modeladmin, request, queryset):
        for mq_run in queryset:
            mq_run.run_maxquant(rerun=False)
            mq_run.run_rawtools_qc(rerun=False)
            mq_run.run_rawtools_metrics(rerun=False)

    actions = [
        start_all,
        start_maxquant,
        start_rawtools,
        rerun_maxquant,
        rerun_rawtools,
        rerun_rawtools_qc,
        rerun_rawtools_metrics,
    ]

    class Media:
        css = {"all": ("css/admin-shared-changelist.css",)}


class MaxQuantExecutableAdmin(admin.ModelAdmin):

    fieldsets = ((None, {"fields": ("created", "filename", "description")}),)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ("created", "filename")
        else:
            return ("created",)


admin.site.register(Pipeline, PipelineAdmin)
#admin.site.register(MaxQuantExecutable, MaxQuantExecutableAdmin)
admin.site.register(RawFile, RawFileAdmin)
admin.site.register(Result, ResultAdmin)

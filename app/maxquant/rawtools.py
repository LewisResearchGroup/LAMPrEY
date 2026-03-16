import re
import shlex

from django.core.exceptions import ValidationError
from django.db import models


DEFAULT_RAWTOOLS_ARGS = "-p -x -u -l -m -chro 12TB"
RAWTOOLS_BOOLEAN_FLAGS = {"-p", "-q", "-x", "-u", "-l", "-m"}
RAWTOOLS_VALUE_FLAGS = {"-r", "-chro"}
RAWTOOLS_ALLOWED_FLAGS = RAWTOOLS_BOOLEAN_FLAGS | RAWTOOLS_VALUE_FLAGS
RAWTOOLS_VALUE_RE = re.compile(r"^[A-Za-z0-9._:+-]+(?: [A-Za-z0-9._:+-]+)*$")


def parse_rawtools_args(rawtools_args):
    if rawtools_args in (None, ""):
        return []
    try:
        tokens = shlex.split(rawtools_args, posix=True)
    except ValueError as exc:
        raise ValidationError(f"Invalid RawTools arguments: {exc}") from exc

    normalized = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token not in RAWTOOLS_ALLOWED_FLAGS:
            raise ValidationError(
                f"Unsupported RawTools argument '{token}'. Allowed flags: "
                f"{', '.join(sorted(RAWTOOLS_ALLOWED_FLAGS))}."
            )

        normalized.append(token)
        if token in RAWTOOLS_VALUE_FLAGS:
            idx += 1
            if idx >= len(tokens):
                raise ValidationError(f"RawTools argument '{token}' requires a value.")
            value = tokens[idx]
            if value in RAWTOOLS_ALLOWED_FLAGS:
                raise ValidationError(f"RawTools argument '{token}' requires a value.")
            if not RAWTOOLS_VALUE_RE.match(value):
                raise ValidationError(
                    f"Invalid value '{value}' for RawTools argument '{token}'."
                )
            normalized.append(value)
        idx += 1
    return normalized


def normalize_rawtools_args(rawtools_args):
    if rawtools_args is None:
        return None
    return shlex.join(parse_rawtools_args(rawtools_args))


def validate_rawtools_args(rawtools_args):
    parse_rawtools_args(rawtools_args)


class RawToolsSetup(models.Model):

    rawtools_setup_id = models.AutoField(primary_key=True)

    rawtools_args = models.CharField(
        max_length=256,
        null=True,
        default=DEFAULT_RAWTOOLS_ARGS,
        validators=[validate_rawtools_args],
    )

    def __str__(self):
        return self.rawtools_args

    @property
    def rawtools_args_list(self):
        return parse_rawtools_args(self.rawtools_args)

    def clean(self):
        super().clean()
        self.rawtools_args = normalize_rawtools_args(self.rawtools_args)

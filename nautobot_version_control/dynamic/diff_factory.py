"""The diff_factory wraps a model's diff and returns a queryable DiffModel."""

import copy

import django_tables2 as tables
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django_tables2.utils import call_with_appropriate

from nautobot_version_control import diff_table_for_model


class DiffListViewFactory:
    """DiffListViewFactory dynamically generate diff models."""

    def __init__(self, content_type):
        """The DiffListViewFactory init methods."""
        self.content_type = content_type

    def get_table_model(self):
        """Returns the underlying the underlying model."""
        try:
            return apps.get_model("nautobot_version_control", self.table_model_name)
        except LookupError:
            return self.make_table_model()

    def make_table_model(self):
        """Create a DiffList of a model."""
        try:
            # lookup the list view table for this content type
            # todo: once available, use https://github.com/nautobot/nautobot/issues/747
            model = self.content_type.model_class()
            ModelViewTable = diff_table_for_model(model)  # pylint: disable=C0103

            return type(
                self.table_model_name,
                (
                    ModelViewTable,
                    DiffListViewBase,
                ),
                {
                    "__module__": "nautobot_version_control.tables",
                    "_declared": timezone.now(),
                    "Meta": self._get_table_meta(ModelViewTable),
                    "content_type": self.content_type,
                },
            )
        except KeyError as exc:
            raise exc

    @staticmethod
    def _get_table_meta(table):
        meta = copy.deepcopy(table._meta)
        # add diff styling
        meta.row_attrs = {"class": row_attrs_for_record}
        meta.sequence = ("diff", "...")
        return meta

    @property
    def table_model_name(self):
        """Return the diff table for the model."""
        return f"diff_{str(self.content_type.app_label)}_{str(self.content_type.model)}"


def row_attrs_for_record(record):  # pylint: disable=R1710
    """The row_attrs_for_record returns button attributes per diff type."""
    if not record.diff:
        return ""
    if record.diff["diff_type"] == "added":
        return "bg-success"
    if record.diff["diff_type"] == "removed":
        return "bg-danger"

    # diff_type == "modified"
    if record.diff["root"] == "to":
        return "bg-warning"
    if record.diff["root"] == "from":
        return "bg-warning"


class DiffListViewBase(tables.Table):
    """DiffListViewBase base model for a DiffList."""

    diff = tables.Column(verbose_name="Diff Type")

    class Meta:  # pylint: disable=too-few-public-methods
        """Metaclass attributes of DiffListViewBase."""

        abstract = True

    def __init__(self, *args, **kwargs):
        """Overwrite init method on DiffListViewBase."""
        super().__init__(*args, **kwargs)
        for col in self.columns:
            if col.name == "diff":
                continue  # uses `render_diff()`
            col.render = self.wrap_render_func(col.render)

    def render_diff(self, value, record):  # pylint: disable=W0613
        """Custom rendering for the the `Diff Type` columns."""
        content_type = ContentType.objects.get_for_model(self.Meta.model)  # pylint: disable=E1101
        href = reverse(
            "plugins:nautobot_version_control:diff_detail",
            kwargs={
                "app_label": content_type.app_label,
                "model": content_type.model,
                "from_commit": record.diff["from_commit"],
                "to_commit": record.diff["to_commit"],
                "pk": record.pk,
            },
        )

        if record.diff["diff_type"] == "added":
            return format_html(
                f"""<a href="{ href }">
                    <span class="label label-success">added</span>
                </a>"""
            )
        if record.diff["diff_type"] == "removed":
            return format_html(
                f"""<a href="{ href }">
                    <span class="label label-danger">removed</span>
                </a>"""
            )
        # diff_type == "modified"
        cnt = self.count_diffs(record.diff)
        return format_html(
            f"""<a href="{ href }">
                <span class="label label-primary">changed ({ cnt })</span>
            </a>"""
        )

    @staticmethod
    def count_diffs(diff):
        """Count the numbers of diffs."""
        skip_fields = (
            "root",
            "diff_type",
            "to_commit",
            "to_commit_date",
            "from_commit",
            "from_commit_date",
        )
        cnt = 0
        for key, val in diff.items():
            if key in skip_fields:
                continue
            if key.startswith("to_"):
                # compare to and from values
                from_key = f"from_{key[3:]}"
                if val != diff[from_key]:
                    cnt += 1
        return cnt

    @staticmethod
    def wrap_render_func(func):
        """Wraps an existing cell rendering function with diff styling."""

        def render_before_after_diff(value, record, column, bound_column, bound_row, table):  # pylint: disable=R0913  # noqa: PLR0913
            # the previous render function may take any of the
            # following args, so provide them all
            kwargs = {
                "value": value,
                "record": record,
                "column": column,
                "bound_column": bound_column,
                "bound_row": bound_row,
                "table": table,
            }
            try:
                # render the existing column function with best effort.
                cell = call_with_appropriate(func, kwargs)
            except Exception:  # pylint: disable=broad-except
                # In particular, rendering TemplateColumns for deleted rows
                # causes errors. Deleted rows are accessed with "time-travel"
                # queries, but are templates rendered from the current tip of
                # the branch, leading to referential integrity errors.
                return value

            if not record.diff or record.diff["diff_type"] != "modified":
                # only render before/after diff styling
                # for 'modified' rows
                return cell

            before_name = f"from_{bound_column.name}"
            if before_name not in record.diff:
                # can't render diff styling
                return cell

            after_name = f"to_{bound_column.name}"
            if after_name in record.diff and record.diff[after_name] == record.diff[before_name]:
                # no diff
                return cell

            # re-render the cell value with its before value
            kwargs["value"] = record.diff[before_name]
            before_cell = call_with_appropriate(func, kwargs)

            if before_cell == cell:
                # no change
                return cell

            before_cell = before_cell if before_cell else " — "
            return format_html(
                f"""<div>
                <span class="bg-danger text-danger">
                    <b>{before_cell}</b>
                </span>
                </br>
                <span class="bg-success text-success">
                    <b>{cell}</b>
                </span>
            </div>"""
            )

        return render_before_after_diff

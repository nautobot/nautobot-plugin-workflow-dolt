"""The middleware add-ons needed for the Version Control plugin to work."""

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.html import format_html
from nautobot.extras.models.change_logging import ObjectChange

from nautobot_version_control.constants import (
    DOLT_BRANCH_KEYWORD,
    DOLT_DEFAULT_BRANCH,
)
from nautobot_version_control.models import Branch, Commit
from nautobot_version_control.utils import DoltError


def dolt_health_check_intercept_middleware(get_response):
    """Intercept health check calls and disregard."""
    # TODO: fix health-check and remove

    def middleware(request):
        if "/health" in request.path:
            return HttpResponse(status=201)
        return get_response(request)

    return middleware


class DoltBranchMiddleware:
    """DoltBranchMiddleware keeps track of which branch the dolt database is on."""

    def __init__(self, get_response):
        """The init method for DoltBranchMiddleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Override __call__."""
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        """This maintains the dolt branch session cookie and verifies authentication. It then returns the view that needs to be rendered."""
        # Check whether the desired branch was passed in as a querystring
        query_string_branch = request.GET.get(DOLT_BRANCH_KEYWORD, None)
        if query_string_branch is not None:
            # update the session Cookie
            request.session[DOLT_BRANCH_KEYWORD] = query_string_branch
            return redirect(request.path)

        branch = DoltBranchMiddleware.get_branch(request)
        try:
            branch.checkout()
        except Exception as err:  # pylint: disable=broad-except
            msg = "could not checkout branch {}: {}"
            messages.error(request, format_html(msg, branch, err))

        try:
            return view_func(request, *view_args, **view_kwargs)
        except DoltError as err:
            messages.error(request, format_html("{}", err))
            return redirect(request.path)

    @staticmethod
    def get_branch(request):
        """Returns the Branch object of the branch stored in the session cookie."""
        # lookup the active branch in the session cookie
        requested = branch_from_request(request)
        try:
            return Branch.objects.get(pk=requested)
        except ObjectDoesNotExist:
            messages.warning(
                request,
                format_html('<div class="text-center">branch not found: {}</div>', requested),
            )
            request.session[DOLT_BRANCH_KEYWORD] = DOLT_DEFAULT_BRANCH
            return Branch.objects.get(pk=DOLT_DEFAULT_BRANCH)


class DoltAutoCommitMiddleware:  # pylint: disable=too-few-public-methods
    """
    DoltAutoCommitMiddleware calls the AutoDoltCommit class on a request.

    - adapted from nautobot.extras.middleware.ObjectChangeMiddleware.
    """

    def __init__(self, get_response):
        """The init method for DoltAutoCommitMiddleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Override call."""
        # Process the request with auto-dolt-commit enabled
        with AutoDoltCommit(request):
            return self.get_response(request)


class AutoDoltCommit:
    """
    AutoDoltCommit handles automatic dolt commits on the case than objects is created or deleted.

    - adapted from `nautobot.extras.context_managers`.
    """

    def __init__(self, request):
        """The init methods for dolt commit."""
        self.request = request
        self.commit = False
        self.changes_for_db = {}

    def __enter__(self):
        """Overwrite methods for dolt commit enter."""
        # Connect our receivers to the post_save and post_delete signals.
        post_save.connect(self._handle_update, dispatch_uid="dolt_commit_update")
        m2m_changed.connect(self._handle_update, dispatch_uid="dolt_commit_update")
        pre_delete.connect(self._handle_delete, dispatch_uid="dolt_commit_delete")

    def __exit__(self, type, value, traceback):  # pylint: disable=W0622
        """Overwrite methods for dolt commit exit."""
        if self.commit:
            self.make_commits()

        # Disconnect change logging signals. This is necessary to avoid recording any errant
        # changes during test cleanup.
        post_save.disconnect(self._handle_update, dispatch_uid="dolt_commit_update")
        m2m_changed.disconnect(self._handle_update, dispatch_uid="dolt_commit_update")
        pre_delete.disconnect(self._handle_delete, dispatch_uid="dolt_commit_delete")

    def _handle_update(self, sender, instance, **kwargs):  # pylint: disable=W0613
        """Fires when an object is created or updated."""
        if isinstance(instance, ObjectChange):
            # ignore ObjectChange instances
            return

        msg = self.change_msg_for_update(instance, kwargs)
        self.collect_change(instance, msg)
        self.commit = True

    def _handle_delete(self, sender, instance, **kwargs):  # pylint: disable=W0613
        """Fires when an object is deleted."""
        if isinstance(instance, ObjectChange):
            # ignore ObjectChange instances
            return

        msg = self.change_msg_for_delete(instance)
        self.collect_change(instance, msg)
        self.commit = True

    def make_commits(self):
        """Create and saves a Commit object."""
        for database, msgs in self.changes_for_db.items():
            msg = "; ".join(msgs)
            Commit(message=msg).save(
                user=self.request.user,
                using=database,
            )

    def collect_change(self, instance, msg):
        """Stores changes messages for each db."""
        database = self.database_from_instance(instance)
        if database not in self.changes_for_db:
            self.changes_for_db[database] = []
        self.changes_for_db[database].append(msg)

    @staticmethod
    def database_from_instance(instance):
        """Returns a database from an instance type."""
        return instance._state.db  # pylint: disable=W0212

    @staticmethod
    def change_msg_for_update(instance, kwargs):
        """Generates a commit message for create or update."""
        created = "created" in kwargs and kwargs["created"]
        verb = "Created" if created else "Updated"
        return f"""{verb} {instance._meta.verbose_name} "{instance}" """

    @staticmethod
    def change_msg_for_delete(instance):
        """Generates a commit message for delete."""
        return f"""Deleted {instance._meta.verbose_name} "{instance}" """


def branch_from_request(request):
    """
    Returns the active branch from a request.

    :param request: A django request
    :return: Branch name
    """
    if DOLT_BRANCH_KEYWORD in request.session:
        return request.session.get(DOLT_BRANCH_KEYWORD)
    if DOLT_BRANCH_KEYWORD in request.headers:
        return request.headers.get(DOLT_BRANCH_KEYWORD)
    return DOLT_DEFAULT_BRANCH

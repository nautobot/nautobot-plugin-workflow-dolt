"""App declaration for nautobot_version_control."""

# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

import django_tables2
from django.db.models.signals import post_migrate, pre_migrate
from nautobot.apps import NautobotAppConfig

from nautobot_version_control.migrations import auto_dolt_commit_migration

__version__ = metadata.version(__name__)


class NautobotVersionControlConfig(NautobotAppConfig):
    """App configuration for the nautobot_version_control app."""

    name = "nautobot_version_control"
    verbose_name = "Nautobot Version Control"
    description = "Nautobot Version Control with Dolt"
    base_url = "version-control"
    version = __version__
    author = "Network to Code, LLC"
    author_email = "opensource@networktocode.com"
    min_version = "2.0.0"
    max_version = "2.999"
    required_settings = []
    default_settings = {
        # TODO: are these respected?
        #   this is also set in /development/nautobot_config.py
        "DATABASE_ROUTERS": [
            "nautobot_version_control.routers.GlobalStateRouter",
        ],
        "SESSION_ENGINE": "django.contrib.sessions.backends.signed_cookies",
        "CACHEOPS_ENABLED": False,
    }
    middleware = [
        "nautobot_version_control.middleware.dolt_health_check_intercept_middleware",
        "nautobot_version_control.middleware.DoltBranchMiddleware",
        "nautobot_version_control.middleware.DoltAutoCommitMiddleware",
    ]

    def ready(self):
        """App ready method."""
        super().ready()

        # disable the GlobalStateRouter during migrations.
        pre_migrate.connect(switch_global_router_off, sender=self)
        post_migrate.connect(switch_global_router_on, sender=self)

        # make a Dolt commit to save database migrations.
        post_migrate.connect(auto_dolt_commit_migration, sender=self)


config = NautobotVersionControlConfig  # pylint:disable=invalid-name


def query_registry(model, registry):
    """Performs a lookup on a content type registry.

    Args:
        model (Model): a Django model class
        registry (dict): a python dictionary like
            ```
            {
                "my_app_label": True,
                "my_other_model": {
                    "my_model": True,
                },
            }
            ```
            The type of `<value>` is specific to each
            registry. A return value of `None` signals
            that nothing is registered for that `model`.
    """
    app_label = model._meta.app_label
    model = model.__name__.lower()

    if app_label not in registry:
        return None
    if not isinstance(registry[app_label], dict):
        return registry[app_label]

    # subset specified
    if model not in registry[app_label]:
        return None
    return registry[app_label][model]


# Registry of Content Types of models that should be under version control.
# Top-level dict keys are app_labels. If the top-level dict value is `True`,
# then all models under that app_label are allowlisted.The top-level value
# may also be a nest dict containing a subset of version-controlled models
# within the app_label.
__VERSIONED_MODEL_REGISTRY___ = {
    "nautobot_version_control": {
        # Pull Requests are not versioned
        "pullrequest": False,
        "pullrequestreviewcomments": False,
        "pullrequestreviews": False,
        "branchmeta": False,
        "branch": False,
        # todo: calling the following "versioned" is odd.
        #   their contents are parameterized by branch
        #   changes, but they are not under VCS.
        "commit": True,
        "commitancestor": True,
        "conflicts": True,
        "constraintviolations": True,
    },
    "dcim": True,
    "circuits": True,
    "ipam": True,
    "virtualization": True,
    "taggit": True,
    "tenancy": True,
    "extras": {
        # TODO: what should be versioned from `extras`?
        "computedfield": True,
        "configcontext": True,
        "configcontextschema": True,
        "customfield": True,
        "customfieldchoice": True,
        "customlink": True,
        "exporttemplate": True,
        # "gitrepository": True,
        "graphqlquery": True,
        "imageattachment": True,
        # "job": True,
        # "jobresult": True,
        "objectchange": True,
        "relationship": True,
        "relationshipassociation": True,
        "secret": True,
        "secretsgroup": True,
        "status": True,
        "tag": True,
        "taggeditem": True,
        "webhook": True,
    },
}


def is_versioned_model(model):
    """
    Determines whether a model is under version control.

    See __MODELS_UNDER_VERSION_CONTROL__ for more info.
    """
    registry = __VERSIONED_MODEL_REGISTRY___
    return bool(query_registry(model, registry))


def register_versioned_models(registry):
    """Register additional content types to be versioned.

    Args:
        registry (dict): a python dict of content types that
            will be placed under version control:
            ```
            {
                "my_app_label": True,
                "my_other_model": {
                    "my_model": True,
                },
            }
            ```
    """
    err = ValueError("invalid versioned model registry")
    for key, val in registry.items():
        if not isinstance(key, str):
            # key must be string
            raise err
        if isinstance(val, bool):
            # val may be bool
            continue
        if not isinstance(val, dict):
            # val must be dict if not bool
            raise err
        # validate nested dict
        for inner_key, inner_val in val.items():
            if not isinstance(inner_key, str):
                # inner_key must be string
                raise err
            if not isinstance(inner_val, bool):
                # inner_val must be bool
                raise err
    __VERSIONED_MODEL_REGISTRY___.update(registry)


__DIFF_TABLE_REGISTRY__ = {}


def diff_table_for_model(model):
    """Returns a table object for a model, if it exists in the ` __DIFF_TABLE_REGISTRY__`."""
    return query_registry(model, __DIFF_TABLE_REGISTRY__)


def register_diff_tables(registry):
    """Register additional tables to be used in diffs.

    Registry values must be subclasses of django_tables2.Table.

    Args:
        registry (dict): a python dict of content types that
            will be placed under version control:
            ```
            {
                "my_app_label": True,
                "my_other_model": {
                    "my_model": True,
                },
            }
            ```
    """
    err = ValueError("invalid diff table registry")
    for key, val in registry.items():
        if not isinstance(key, str):
            # key must be string
            raise err
        if not isinstance(val, dict):
            # val must be dict
            raise err
        for inner_key, inner_val in val.items():
            if not isinstance(inner_key, str):
                # inner_key must be string
                raise err
            if not issubclass(inner_val, django_tables2.tables.Table):
                # inner_val must be Table
                raise err
    __DIFF_TABLE_REGISTRY__.update(registry)


__GLOBAL_ROUTER_SWITCH__ = True


def is_global_router_enabled():
    """Returns true if the __GLOBAL_ROUTER_SWITCH__ is turned on."""
    global __GLOBAL_ROUTER_SWITCH__  # pylint: disable=W0602  # noqa: PLW0602
    return __GLOBAL_ROUTER_SWITCH__


def switch_global_router_on(**kwargs):
    """Sets __GLOBAL_ROUTER_SWITCH to true."""
    global __GLOBAL_ROUTER_SWITCH__  # pylint: disable=global-statement  # noqa: PLW0603
    __GLOBAL_ROUTER_SWITCH__ = True


def switch_global_router_off(**kwargs):
    """Sets __GLOBAL_ROUTER_SWITCH to false."""
    global __GLOBAL_ROUTER_SWITCH__  # pylint: disable=global-statement  # noqa: PLW0603
    __GLOBAL_ROUTER_SWITCH__ = False

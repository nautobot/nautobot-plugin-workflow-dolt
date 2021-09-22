from django import forms

from nautobot.users.models import User
from nautobot.utilities.forms import BootstrapMixin, ConfirmationForm, add_blank_choice

from dolt.models import Branch, Commit, PullRequest, PullRequestReview
from dolt.utils import active_branch, DoltError
from dolt.constants import DOLT_DEFAULT_BRANCH


#
# Branches
#


class BranchForm(forms.ModelForm, BootstrapMixin):
    name = forms.SlugField()
    starting_branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(), to_field_name="name", required=True
    )
    creator = forms.ModelChoiceField(
        queryset=User.objects.all(),
        to_field_name="username",
        required=True,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Branch
        fields = [
            "name",
            "starting_branch",
        ]

    def __init__(self, *args, **kwargs):
        # self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        self.instance.starting_branch = self.cleaned_data["starting_branch"]
        self.instance.creator = self.cleaned_data["creator"]
        return super().save(*args, **kwargs)


class MergeForm(forms.Form, BootstrapMixin):
    source_branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(), to_field_name="name", required=True
    )
    destination_branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(), to_field_name="name", required=True
    )

    class Meta:
        fields = [
            "source_branch",
            "destination_branch",
        ]


class MergePreviewForm(forms.Form, BootstrapMixin):
    source_branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        to_field_name="name",
        disabled=True,
    )
    destination_branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        to_field_name="name",
        disabled=True,
    )

    class Meta:
        fields = [
            "source_branch",
            "destination_branch",
        ]


class BranchBulkEditForm(forms.Form, BootstrapMixin):
    class Meta:
        model = Branch
        fields = [
            "name",
        ]


class BranchBulkDeleteForm(ConfirmationForm):
    pk = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.all(), widget=forms.MultipleHiddenInput
    )

    def clean_pk(self):
        # TODO: log error messages
        deletes = [str(b) for b in self.cleaned_data["pk"]]
        if active_branch() in deletes:
            raise DoltError(f"Cannot delete active branch: {active_branch()}")
        if DOLT_DEFAULT_BRANCH in deletes:
            raise DoltError(f"Cannot delete primary branch: {DOLT_DEFAULT_BRANCH}")
        return self.cleaned_data["pk"]

    class Meta:
        model = Branch
        fields = [
            "name",
        ]


class BranchFilterForm(forms.Form, BootstrapMixin):
    model = Branch
    field_order = ["q"]
    q = forms.CharField(required=False, label="Search")

    latest_committer = forms.ChoiceField(choices=[], required=False)

    def __init__(self, *args, **kwargs):
        super(BranchFilterForm, self).__init__(*args, **kwargs)
        self.fields["latest_committer"].choices = add_blank_choice(
            Branch.objects.all()
            .values_list("latest_committer", "latest_committer")
            .distinct()
        )


#
# Commits
#


class CommitForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = Commit
        fields = ["message"]


class CommitFilterForm(forms.Form, BootstrapMixin):
    model = Commit
    field_order = ["q"]
    q = forms.CharField(required=False, label="Search")
    committer = forms.ChoiceField(choices=[], required=False)

    def __init__(self, *args, **kwargs):
        super(CommitFilterForm, self).__init__(*args, **kwargs)
        self.fields["committer"].choices = (
            Commit.objects.all().values_list("committer", "committer").distinct()
        )


class CommitBulkRevertForm(forms.Form, BootstrapMixin):
    pk = forms.ModelMultipleChoiceField(
        queryset=Commit.objects.all(), widget=forms.MultipleHiddenInput()
    )

    class Meta:
        fields = ["branch"]


#
# PullRequests
#


class PullRequestForm(forms.ModelForm, BootstrapMixin):
    qs = Branch.objects.exclude(name__startswith="xxx")
    source_branch = forms.ModelChoiceField(
        queryset=qs, to_field_name="name", required=True
    )
    destination_branch = forms.ModelChoiceField(
        queryset=qs, to_field_name="name", required=True
    )

    class Meta:
        model = PullRequest
        fields = [
            "title",
            "source_branch",
            "destination_branch",
            "description",
        ]


class PullRequestDeleteForm(ConfirmationForm):
    pk = forms.ModelMultipleChoiceField(
        queryset=PullRequest.objects.all(), widget=forms.MultipleHiddenInput
    )

    def clean_pk(self):
        return self.cleaned_data["pk"]

    class Meta:
        model = PullRequest
        fields = [
            "pk",
        ]


class PullRequestFilterForm(forms.Form, BootstrapMixin):
    model = PullRequest
    q = forms.CharField(required=False, label="Search")
    state = forms.MultipleChoiceField(
        required=False, choices=PullRequest.PR_STATE_CHOICES
    )
    creator = forms.ModelChoiceField(required=False, queryset=User.objects.all())
    reviewer = forms.ModelChoiceField(required=False, queryset=User.objects.all())

    def __init__(self, *args, **kwargs):
        super(PullRequestFilterForm, self).__init__(*args, **kwargs)
        if args is not None:
            if not args[0].get("state", None):
                newArgs = args[0].copy()
                newArgs.update({"state": PullRequest.OPEN})
                super(PullRequestFilterForm, self).__init__(newArgs, **kwargs)

    class Meta:
        fields = [
            "state",
            "title",
            "source_branch",
            "destination_branch",
            "description",
        ]


class PullRequestReviewForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = PullRequestReview
        fields = [
            "pull_request",
            "summary",
            "state",
        ]

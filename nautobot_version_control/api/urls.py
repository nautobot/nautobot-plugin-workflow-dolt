"""API urls for version_control app."""

from nautobot.core.api.routers import OrderedDefaultRouter

from . import views

router = OrderedDefaultRouter()
router.APIRootView = views.VCSRootView

# Sites
router.register("branches", views.BranchViewSet)
router.register("commits", views.CommitViewSet)
router.register("pull_requests", views.PullRequestViewSet)
router.register("pull_requests_reviews", views.PullRequestReviewViewSet)

app_name = "nautobot_version_control-api"
urlpatterns = router.urls

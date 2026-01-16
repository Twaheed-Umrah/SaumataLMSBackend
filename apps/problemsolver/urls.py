from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProblemReportViewSet

router = DefaultRouter()
router.register(r'problems', ProblemReportViewSet, basename='problem')

urlpatterns = [
    path('', include(router.urls)),
]

# Note: The router automatically creates the following URLs:
# GET /problems/ - List all problems
# POST /problems/ - Create new problem
# GET /problems/{id}/ - Retrieve problem
# PUT /problems/{id}/ - Update problem
# PATCH /problems/{id}/ - Partial update
# DELETE /problems/{id}/ - Delete problem
# POST /problems/{id}/update_problem/ - Custom update
# POST /problems/{id}/add_communication/ - Add communication
# POST /problems/{id}/assign/ - Assign problem
# POST /problems/{id}/mark_resolved/ - Mark as resolved
# POST /problems/bulk_update/ - Bulk update
# GET /problems/stats/ - Get statistics
# GET /problems/my_assigned/ - Get user's assigned problems
# GET /problems/dashboard/ - Get dashboard data
# GET /problems/customer_problems/ - Get customer problems
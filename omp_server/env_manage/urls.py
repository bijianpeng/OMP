# -*- coding: utf-8 -*-
"""
环境管理路由

挂载方式：omp_server/urls.py 中 path("env/", include("env_manage.urls"))，
故注册前缀为空串，最终 URL 为 /api/env/、/api/env/{id}/、
/api/env/{id}/users/。
"""
from rest_framework.routers import DefaultRouter

from env_manage.views import EnvView

router = DefaultRouter()
router.register("", EnvView, basename="env")

urlpatterns = router.urls

"""The course requires every implemented HTTP endpoint to be asynchronous."""

import inspect

from fastapi.routing import APIRoute

from app.api import (
    auth,
    health,
    languages,
    logs,
    plagiarism,
    problems,
    submissions,
    system,
    users,
)


# 函数 `test_all_application_routes_are_async`：负责当前测试或测试夹具。
def test_all_application_routes_are_async() -> None:
    routers = (
        auth.router,
        health.router,
        languages.router,
        logs.router,
        plagiarism.router,
        problems.router,
        submissions.router,
        system.router,
        users.router,
    )
    routes = [route for router in routers for route in router.routes]

    assert routes
    assert all(isinstance(route, APIRoute) for route in routes)
    assert all(inspect.iscoroutinefunction(route.endpoint) for route in routes)

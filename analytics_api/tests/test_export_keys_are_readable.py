"""Every sensor the API offers can also be read.

The export map drives the manifest, the CSV exports and the count cache, and the
dashboard requests a sensor's rows at `/{platform}/{device_id}/{key}`. A key
added to the map without a route is counted and exported but answers 404 to the
page — which has happened twice, each time noticed only by opening the URL.
"""

import pytest

from app.routers import android as android_router
from app.routers import ios as ios_router


def _keys_without_routes(module, prefix: str) -> list[str]:
    routes = {
        route.path.replace(prefix, "")
        for route in module.router.routes
        if route.path.startswith(prefix)
    }
    return sorted(set(module._EXPORT_MODELS) - routes)


@pytest.mark.parametrize(
    "module, prefix",
    [
        (android_router, "/android/{device_id}/"),
        (ios_router, "/ios/{device_id}/"),
    ],
    ids=["android", "ios"],
)
def test_every_offered_sensor_is_readable(module, prefix):
    missing = _keys_without_routes(module, prefix)
    assert not missing, (
        f"{missing} are exported and counted but have no route, so the dashboard "
        "gets a 404 asking for their rows"
    )

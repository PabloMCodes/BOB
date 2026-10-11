"""Hub frontend API (C10): REST + WS /v1/live for the browser, over the hub replicas.

Layout:
  app.py     FastAPI app, routes, auth (bearer header or ?token=), WS /v1/live
  views.py   replica -> response models
  worksites.py  profile authoring + inspection start/end forwarded to the rover
  twin.py    Twin routes (sessions, track, pins, debug map.svg) over bobapp.hub.twin
  models/    response models by area (they generate the OpenAPI description)
"""

from .app import HUB_ROUTES, create_hub_app, route_table

__all__ = ["HUB_ROUTES", "create_hub_app", "route_table"]

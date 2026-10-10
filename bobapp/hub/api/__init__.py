"""Hub frontend API (C10): REST + WS /v1/live for the browser, over the hub replicas.

Layout:
  app.py     FastAPI app, routes, auth (bearer header or ?token=), WS /v1/live
  views.py   replica -> response models
  models/    response models by area (they generate the OpenAPI description)
"""

from .app import HUB_ROUTES, create_hub_app

__all__ = ["HUB_ROUTES", "create_hub_app"]

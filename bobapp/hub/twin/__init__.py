"""Read-only session-local 2D Twin (plan §7): data for the frontend and a debug SVG.

Layout:
  projection.py  ARKit world -> map / SVG axes and heading
  data.py        sessions, track segments, pins + unlocalized, phone-camera marker
  svg.py         debug map rendering (walk test aid, not the product UI)
"""

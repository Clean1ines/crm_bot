from __future__ import annotations

"""Knowledge port package marker.

Do not re-export knowledge ports from this package root.

Import concrete bounded-context modules directly, for example:
- src.application.ports.knowledge.runtime_search
- src.application.ports.knowledge.production_retrieval

The old eager barrel import pulled removed compiler/candidate ports and made
safe runtime imports load the retired compiler domain.
"""

__all__: tuple[str, ...] = ()

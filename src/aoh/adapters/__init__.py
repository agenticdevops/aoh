"""Runtime adapters for AOH packs.

Importing this package registers every built-in adapter in
`aoh.adapters.base.ADAPTERS` as a side effect, so `from aoh.adapters.base
import ADAPTERS` alone (without directly importing an adapter module) still
sees the full registry.
"""

from aoh.adapters import claude_code as _claude_code  # noqa: F401
from aoh.adapters import hermes as _hermes  # noqa: F401

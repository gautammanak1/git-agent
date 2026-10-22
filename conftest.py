"""Pytest bootstrap: make ``main`` importable without the uAgents SDK.

The agent source imports ``uagents`` and ``ai_engine`` (and uses ``requests``)
at module level. When those packages are not installed - or fail to import
(for example an SDK that is incompatible with the running Python version) -
minimal in-memory stubs are registered in ``sys.modules`` so the module can
still be imported and its pure logic (input validation, API error mapping,
HTML formatting, message handler) can be tested. Stubs are only installed
when the real packages cannot be imported, so a working SDK always wins.
"""

import importlib.util
import sys
import types
from pathlib import Path

# Make the repository root (this directory) importable so ``import main`` works
# regardless of where pytest was invoked from.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _importable(name: str) -> bool:
    """True when ``name`` can actually be imported (not merely installed)."""
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


if not _importable("requests"):
    # Only the tiny surface main.py touches; tests never perform real I/O.
    requests = types.ModuleType("requests")
    requests.exceptions = types.SimpleNamespace(
        Timeout=type("Timeout", (Exception,), {}),
        RequestException=type("RequestException", (Exception,), {}),
    )

    class _StubSession:
        def request(self, *args, **kwargs):
            raise RuntimeError("network access is not available in tests")

    requests.Session = _StubSession
    sys.modules["requests"] = requests


if not _importable("uagents"):
    uagents = types.ModuleType("uagents")

    class Agent:
        def __init__(self, *args, **kwargs):
            self.included = []

        def include(self, protocol, publish_manifest=False):
            self.included.append((protocol, publish_manifest))

    class Context:
        """Type-only stub; tests provide their own fake context objects."""

    def Field(*args, **kwargs):
        # Return the declared default (or None) so message models get plain
        # class-level defaults without pydantic.
        return args[0] if args else kwargs.get("default")

    class Model:
        """Minimal message-model base: annotated fields get defaults."""

        def __init__(self, **kwargs):
            cls = type(self)
            for name in dict(getattr(cls, "__annotations__", {})):
                setattr(self, name, kwargs.pop(name, getattr(cls, name, None)))
            for name, value in kwargs.items():
                setattr(self, name, value)

    class Protocol:
        def __init__(self, name=None):
            self.name = name
            self.handlers = []

        def on_message(self, model=None, replies=None):
            def decorator(func):
                self.handlers.append((model, replies, func))
                return func

            return decorator

    uagents.Agent = Agent
    uagents.Context = Context
    uagents.Field = Field
    uagents.Model = Model
    uagents.Protocol = Protocol
    sys.modules["uagents"] = uagents


if not _importable("ai_engine"):
    ai_engine = types.ModuleType("ai_engine")

    class UAgentResponse:
        def __init__(self, message="", type=None, **kwargs):
            self.message = message
            self.type = type

    class UAgentResponseType:
        FINAL = "final"
        ERROR = "error"

    ai_engine.UAgentResponse = UAgentResponse
    ai_engine.UAgentResponseType = UAgentResponseType
    sys.modules["ai_engine"] = ai_engine
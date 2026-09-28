"""ToonOptimizer backend: a local Raidbots built on SimulationCraft."""

__version__ = "0.1.0"


def main() -> None:
    import uvicorn

    from toonopt.config import settings

    uvicorn.run("toonopt.main:app", host="127.0.0.1", port=settings.port, reload=False)

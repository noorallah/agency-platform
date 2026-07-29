"""Base service abstractions for future application use cases."""


class BaseService:
    """Provide a dependency-owning base class for application services.

    Services coordinate use cases and depend on repositories or unit-of-work
    abstractions; HTTP adapters and ORM queries remain outside subclasses.
    """

"""Which routes only a platform administrator may reach, pinned.

`require_platform_admin()` is a different kind of gate from
`require_permission("CODE")`. A permission can be granted to a role and given
to somebody; the designation cannot -- it comes from a `platform_admins` row
and nothing a firm administrator can do reaches it. So putting the designation
on a route that *also* has a seeded permission code makes that code grant
nothing, silently and for ever.

That is what had happened to `GET /api/v1/roles`. It was the only one of the
four role endpoints on the designation -- `get_role`, `create_role` and
`update_role` all took `ROLE_VIEW` -- and the only one of the three identity
lists, beside `list_users` and `list_permissions` which take their own view
codes. `ROLE_VIEW` was seeded, granted to `FIRM_ADMIN`, honoured everywhere
except the one screen a firm administrator would start from, and the firm
filtering inside `list_roles` had been written for a caller who could never
reach it. Found by driving the endpoint with a real firm-admin token while
building user templates -- a firm cannot assemble a template without seeing
the roles it may bundle.

This pins the set rather than forbidding it. A platform-only route is a
deliberate act; the point is that adding one is a decision somebody made on
purpose, and this test is where they say so.

`PUT /api/v1/users/{user_id}/firms` came **off** the list on 2026-09-06, which
is the other thing this file is for. Its reason read "which firms a person
belongs to is a cross-firm fact, so not a decision any single firm's
administrator can make" -- true in its first half and a non-sequitur in its
second. An administrator of two firms putting a new hire in both is the
ordinary case and was refused outright. The cross-firm part is handled by
reach now: `_firms_the_caller_may_staff` limits them to firms where they hold
`USER_CREATE`, and memberships outside that are carried through untouched
rather than replaced.
"""

# ruff: noqa: D103

from functools import lru_cache

import pytest


@lru_cache(maxsize=1)
def _platform_only_routes() -> frozenset[tuple[str, str]]:
    """Return (method, path) for every route behind the platform designation."""
    from fastapi.dependencies.utils import get_dependant
    from fastapi.routing import APIRoute

    from app.main import create_app

    def guarded(route: APIRoute) -> bool:
        """Whether `require_platform_admin` appears anywhere in the tree."""
        pending = list(get_dependant(path=route.path, call=route.endpoint).dependencies)
        seen = 0
        while pending and seen < 500:
            seen += 1
            dependency = pending.pop()
            call = getattr(dependency, "call", None)
            qualname = getattr(call, "__qualname__", "")
            if qualname.startswith("require_platform_admin"):
                return True
            pending.extend(dependency.dependencies)
        return False

    found: set[tuple[str, str]] = set()
    for route in create_app().routes:
        candidates = (
            [route]
            if isinstance(route, APIRoute)
            else (
                list(getattr(route, "original_router", None).routes or [])
                if getattr(route, "original_router", None) is not None
                else []
            )
        )
        for candidate in candidates:
            if isinstance(candidate, APIRoute) and guarded(candidate):
                found.update((method, candidate.path) for method in candidate.methods)
    return frozenset(found)


#: Every route only a platform administrator may reach.
#:
#: Each of these is a decision about the platform rather than about a firm's
#: business: who the administrators are, which firms exist, where a firm's data
#: lives, and the shape of the permission catalogue itself. A firm
#: administrator is deliberately not offered any of them.
_EXPECTED = frozenset(
    {
        # Which firms exist, and where each one's data lives.
        ("GET", "/api/v1/firms"),
        ("POST", "/api/v1/firms"),
        ("DELETE", "/api/v1/firms/{firm_id}"),
        ("GET", "/api/v1/firms/{firm_id}"),
        ("PUT", "/api/v1/firms/{firm_id}"),
        ("POST", "/api/v1/firms/{firm_id}/provision"),
        # Whether a firm is finished, and the one step that finishes it. Both
        # reach across every firm's store from the platform side, which is
        # what setting a firm up is; a firm administrator sees the result as
        # their own chart of accounts and financial years.
        ("GET", "/api/v1/firms/{firm_id}/readiness"),
        ("POST", "/api/v1/firms/{firm_id}/open-books"),
        ("POST", "/api/v1/firms/{firm_id}/apply-tax-template"),
        ("POST", "/api/v1/firms/{firm_id}/create-default-branch"),
        # The capability catalogue roles are built from. Roles are
        # configurable per firm; the capabilities are not.
        ("POST", "/api/v1/permissions"),
        ("DELETE", "/api/v1/permissions/{permission_id}"),
        ("GET", "/api/v1/permissions/{permission_id}"),
        ("PATCH", "/api/v1/permissions/{permission_id}"),
        # The platform dashboard: counts across every firm.
        ("GET", "/api/v1/dashboard"),
        # Bringing a deleted user back. Deletion is firm-scoped, but a deleted
        # user is invisible to a firm's grid and their memberships are
        # platform facts, so the way back is the platform's.
        ("POST", "/api/v1/users/{user_id}/restore"),
        # Setting somebody else's password without knowing the current one.
        # A firm administrator handing out a temporary password would be
        # taking over an account that may also work in a firm they cannot see.
        ("POST", "/api/v1/users/{user_id}/password"),
        # The industry-profile framework -- which features and modules
        # exist at all, and which profile a firm is assigned. Setting a firm up is
        # platform work; using what it was set up with is not.
        ("GET", "/api/v1/business-framework/attribute-definitions"),
        ("POST", "/api/v1/business-framework/attribute-definitions"),
        ("DELETE", "/api/v1/business-framework/attribute-definitions/{attribute_id}"),
        ("PUT", "/api/v1/business-framework/attribute-definitions/{attribute_id}"),
        ("GET", "/api/v1/business-framework/category-attribute-rules"),
        ("POST", "/api/v1/business-framework/category-attribute-rules"),
        ("DELETE", "/api/v1/business-framework/category-attribute-rules/{rule_id}"),
        ("PUT", "/api/v1/business-framework/category-attribute-rules/{rule_id}"),
        ("GET", "/api/v1/business-framework/features"),
        ("POST", "/api/v1/business-framework/features"),
        ("DELETE", "/api/v1/business-framework/features/{feature_id}"),
        ("PUT", "/api/v1/business-framework/features/{feature_id}"),
        ("GET", "/api/v1/business-framework/firm-profile-assignments"),
        ("GET", "/api/v1/business-framework/firms/{firm_id}/profile-assignment"),
        ("GET", "/api/v1/business-framework/firms/{firm_id}/profiles"),
        ("PUT", "/api/v1/business-framework/firms/{firm_id}/profile-assignment"),
        ("GET", "/api/v1/business-framework/modules"),
        ("POST", "/api/v1/business-framework/modules"),
        ("DELETE", "/api/v1/business-framework/modules/{module_id}"),
        ("PUT", "/api/v1/business-framework/modules/{module_id}"),
        ("GET", "/api/v1/business-framework/profiles"),
        ("POST", "/api/v1/business-framework/profiles"),
        ("DELETE", "/api/v1/business-framework/profiles/{profile_id}"),
        ("GET", "/api/v1/business-framework/profiles/{profile_id}"),
        ("PUT", "/api/v1/business-framework/profiles/{profile_id}"),
        ("GET", "/api/v1/business-framework/profiles/{profile_id}/configuration"),
        ("PUT", "/api/v1/business-framework/profiles/{profile_id}/features"),
        ("PUT", "/api/v1/business-framework/profiles/{profile_id}/modules"),
        # Document types, states and numbering rules. Worth a second
        # look one day -- a firm arguably owns its own numbering -- but it is
        # pre-existing and changing it is a product decision, not a tidy-up.
        ("POST", "/api/v1/document-framework/document-states"),
        ("DELETE", "/api/v1/document-framework/document-states/{state_id}"),
        ("PUT", "/api/v1/document-framework/document-states/{state_id}"),
        ("POST", "/api/v1/document-framework/document-types"),
        ("DELETE", "/api/v1/document-framework/document-types/{document_type_id}"),
        ("PUT", "/api/v1/document-framework/document-types/{document_type_id}"),
        ("POST", "/api/v1/document-framework/documents/{document_id}/events"),
        # The shared geography masters. Guarded by the designation and
        # by no permission code at all, deliberately: countries, states and
        # districts are shared reference data, so one firm editing them would
        # edit them for everybody.
        ("POST", "/api/v1/sales-territories/geo/cities"),
        ("DELETE", "/api/v1/sales-territories/geo/cities/{city_id}"),
        ("PUT", "/api/v1/sales-territories/geo/cities/{city_id}"),
        ("POST", "/api/v1/sales-territories/geo/countries"),
        ("DELETE", "/api/v1/sales-territories/geo/countries/{country_id}"),
        ("PUT", "/api/v1/sales-territories/geo/countries/{country_id}"),
        ("POST", "/api/v1/sales-territories/geo/districts"),
        ("DELETE", "/api/v1/sales-territories/geo/districts/{district_id}"),
        ("PUT", "/api/v1/sales-territories/geo/districts/{district_id}"),
        ("POST", "/api/v1/sales-territories/geo/localities"),
        ("DELETE", "/api/v1/sales-territories/geo/localities/{locality_id}"),
        ("PUT", "/api/v1/sales-territories/geo/localities/{locality_id}"),
        ("POST", "/api/v1/sales-territories/geo/postal-codes"),
        ("DELETE", "/api/v1/sales-territories/geo/postal-codes/{postal_code_id}"),
        ("PUT", "/api/v1/sales-territories/geo/postal-codes/{postal_code_id}"),
        ("POST", "/api/v1/sales-territories/geo/states"),
        ("DELETE", "/api/v1/sales-territories/geo/states/{state_id}"),
        ("PUT", "/api/v1/sales-territories/geo/states/{state_id}"),
        ("PUT", "/api/v1/sales-territories/hierarchy-levels"),
    }
)


def test_only_the_declared_routes_are_platform_only() -> None:
    found = _platform_only_routes()
    unexpected = sorted(found - _EXPECTED)
    assert not unexpected, (
        "these routes are gated on the platform designation and are not in "
        "`_EXPECTED`:\n  "
        + "\n  ".join(f"{method} {path}" for method, path in unexpected)
        + "\n\nThe designation cannot be granted to anybody, so any permission "
        "code on such a route grants nothing. If that is deliberate, add it "
        "above with the reason; if it is not, gate the route on its permission "
        "code instead -- which is what `GET /api/v1/roles` needed."
    )


def test_every_declared_platform_only_route_still_exists() -> None:
    """The inverse, which is the one that rots.

    A route renamed or removed leaves a line here claiming a restriction that
    is no longer enforced anywhere, and nothing else would say so.
    """
    found = _platform_only_routes()
    missing = sorted(_EXPECTED - found)
    assert not missing, (
        "`_EXPECTED` names routes that are no longer platform-only:\n  "
        + "\n  ".join(f"{method} {path}" for method, path in missing)
        + "\n\nEither the gate was removed -- in which case check it was meant "
        "to be -- or the route was renamed and this line is now fiction."
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/roles"),
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/permissions"),
    ],
)
def test_the_identity_lists_are_reachable_with_a_permission(
    method: str, path: str
) -> None:
    """The three lists a firm administrator starts from.

    `GET /api/v1/roles` was not, and the consequence was concrete: a firm could
    not see the roles a user template may bundle, so it could not build one.
    """
    assert (method, path) not in _platform_only_routes()

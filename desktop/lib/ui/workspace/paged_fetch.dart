import '../../models/entities.dart';

/// The largest page any list endpoint on this platform will serve.
///
/// `MAX_PAGE_SIZE` in `backend/app/core/constants/core.py`. Asking for more is
/// not clamped — it is refused, and on the routers that build their
/// `PaginationParams` by hand it surfaced as a 500 rather than a message
/// naming the limit. A screen that needs everything pages through instead.
const int maxApiPageSize = 100;

/// Read every page of a list endpoint.
///
/// Screens that need a whole collection — the customers on a round, the people
/// a firm can put on one — must not ask for it in a single oversized page. Two
/// screens did, with `pageSize: 500`, and every one of those reads failed:
/// the round pane on the Route Builder and the Customers tab of the territory
/// dialog were both permanently broken against a real server while their
/// tests, whose fakes ignore `pageSize`, stayed green.
///
/// [maxPages] is a backstop, not a limit anyone should reach: it stops a
/// server that keeps answering with a full page from spinning the client
/// forever.
Future<List<T>> fetchAllPages<T>(
  Future<PagedResult<T>> Function(int page) fetch, {
  int maxPages = 20,
}) async {
  final List<T> collected = <T>[];
  for (int page = 1; page <= maxPages; page++) {
    final PagedResult<T> result = await fetch(page);
    collected.addAll(result.items);
    if (result.items.isEmpty || collected.length >= result.total) break;
  }
  return collected;
}

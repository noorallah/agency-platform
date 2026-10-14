import '../../core/api/api_client.dart';
import '../../models/salesman.dart';

/// The firm's salesman list, read once per firm per session (P2).
///
/// Every Salesman box -- the order, the bill, a round, a target, a
/// commission rule, a customer's account manager, a promotion -- asks the
/// same list, so it is read once and shared, exactly as `FirmPeople` shares
/// the firm's people with every History panel. The Salesmen screen calls
/// [invalidate] after anything it changes, so the next box reads the list
/// again.
///
/// The cache answers only for the [ApiClient] it was configured with: a
/// screen handed another one (a test's fake) reads that one directly, so a
/// list cached by one session can never be served to another.
abstract final class FirmSalesmen {
  static ApiClient Function()? _api;
  static String? Function()? _firmId;
  static String? _loadedFor;
  static List<Salesman>? _list;
  static Future<List<Salesman>>? _inFlight;

  /// Where the list comes from and which firm is active.
  static void configure({
    required ApiClient Function() api,
    required String? Function() firmId,
  }) {
    _api = api;
    _firmId = firmId;
  }

  /// Forget everything, as a test or a sign-out does.
  static void reset() {
    _api = null;
    _firmId = null;
    invalidate();
  }

  /// Forget the list, so the next box reads it again.
  static void invalidate() {
    _loadedFor = null;
    _list = null;
    _inFlight = null;
  }

  /// Every salesman of the firm [api] is scoped to, active or not.
  static Future<List<Salesman>> of(ApiClient api) {
    final ApiClient? configured = _api?.call();
    final String firm = _firmId?.call() ?? '';
    if (configured == null || !identical(configured, api) || firm.isEmpty) {
      return api.firmSalesmen();
    }
    final List<Salesman>? held = _list;
    if (held != null && _loadedFor == firm) return Future.value(held);
    final Future<List<Salesman>>? pending = _inFlight;
    if (pending != null && _loadedFor == firm) return pending;
    _loadedFor = firm;
    _list = null;
    late final Future<List<Salesman>> started;
    started = () async {
      try {
        final List<Salesman> rows = await api.firmSalesmen();
        if (_loadedFor == firm && identical(_inFlight, started)) _list = rows;
        return rows;
      } on Object {
        // Not kept: the next box asks again.
        if (_loadedFor == firm) _loadedFor = null;
        rethrow;
      } finally {
        if (identical(_inFlight, started)) _inFlight = null;
      }
    }();
    _inFlight = started;
    return started;
  }
}

/// The options a Salesman box offers: the active salesmen, plus [current]
/// when it names somebody no longer offered -- made inactive, or deleted --
/// so a saved document keeps showing who is on it rather than losing them
/// on the next save.
///
/// [current]'s own label is their name where the list still knows them,
/// marked inactive, and the bare id only for somebody the list has lost.
List<({String id, String label})> salesmanOptions(
  List<Salesman> all, {
  String? current,
}) {
  final List<({String id, String label})> options = [
    for (final Salesman item in all)
      if (item.isActive) (id: item.id, label: item.label),
  ];
  final String? held = current;
  if (held != null &&
      held.isNotEmpty &&
      !options.any((option) => option.id == held)) {
    Salesman? known;
    for (final Salesman item in all) {
      if (item.id == held) known = item;
    }
    options.add((
      id: held,
      label: known == null ? held : '${known.label} (inactive)',
    ));
  }
  return options;
}

/// [id]'s name in [all]; the id itself when the list does not know it, and
/// empty for nobody.
String salesmanName(List<Salesman> all, String? id) {
  if (id == null || id.isEmpty) return '';
  for (final Salesman item in all) {
    if (item.id == id) return item.label;
  }
  return id;
}

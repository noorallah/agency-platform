import '../../models/firm_member.dart';
import '../../phase2/display_dates.dart';

/// Who did what, in words: the one place a document's History / Timeline turns
/// the server's codes into something a person reads (D-BUY-25).
///
/// The server records `purchase.approved`, `SUBMITTED`, a user id and an ISO
/// timestamp. Every document's timeline goes through `EnterpriseTimeline`, which
/// calls these, so no document shows the codes and none has its own copy.

/// `purchase.approved` -> `Approved`; `goods_receipt.completed` -> `Completed`;
/// `STATUS CHANGED` -> `Status changed`.
String historyActionWords(String action) {
  final String trimmed = action.trim();
  final String tail = trimmed.contains('.')
      ? trimmed.substring(trimmed.lastIndexOf('.') + 1)
      : trimmed;
  return _sentenceCase(tail);
}

/// `SUBMITTED` -> `Submitted`; `PARTIALLY_RECEIVED` -> `Partially received`.
String historyStatusWords(String status) => _sentenceCase(status.trim());

String _sentenceCase(String code) {
  final String words = code.replaceAll(RegExp(r'[_\s]+'), ' ').trim();
  if (words.isEmpty) return '';
  return words[0].toUpperCase() + words.substring(1).toLowerCase();
}

/// `2026-10-04T17:38:51.002872+05:30` -> `04-10-2026 17:38` in the signed-in
/// person's own date format, on this machine's clock. Text that is not a
/// timestamp is returned as it came.
String historyWhen(String iso) {
  final DateTime? parsed = DateTime.tryParse(iso.trim());
  if (parsed == null) return iso;
  final DateTime local = parsed.toLocal();
  final String hh = local.hour.toString().padLeft(2, '0');
  final String mm = local.minute.toString().padLeft(2, '0');
  return '${DisplayDates.write(local)} $hh:$mm';
}

final RegExp _userId = RegExp(
  r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
);

/// What the timeline calls somebody it cannot name.
const String unknownHistoryActor = 'Someone outside the firm';

/// The firm's people, read once per firm for the session and shared by every
/// timeline on screen.
///
/// One holder rather than a parameter on each of the dozen document screens,
/// which have no session to ask (the same reason as [DisplayDates]). Set up
/// where the API client is built; the first timeline to open asks
/// `GET /api/v1/firm-members` and every later one -- and every row -- reuses
/// the answer. A failed read is not kept, so the next timeline tries again.
abstract final class FirmPeople {
  static Future<List<FirmMember>> Function()? _load;
  static String? Function()? _firmId;
  static String? _loadedFor;
  static Map<String, String>? _names;
  static Future<void>? _inFlight;

  /// Where the names come from and which firm is active.
  static void configure({
    required Future<List<FirmMember>> Function() load,
    required String? Function() firmId,
  }) {
    _load = load;
    _firmId = firmId;
  }

  /// Forget everything, as a test or a sign-out does.
  static void reset() {
    _load = null;
    _firmId = null;
    _loadedFor = null;
    _names = null;
    _inFlight = null;
  }

  /// Make sure the active firm's people are known. One request per firm.
  static Future<void> ensure() {
    final Future<List<FirmMember>> Function()? load = _load;
    if (load == null) return Future<void>.value();
    final String firm = _firmId?.call() ?? '';
    if (_names != null && _loadedFor == firm) return Future<void>.value();
    final Future<void>? pending = _inFlight;
    if (pending != null && _loadedFor == firm) return pending;
    _loadedFor = firm;
    _names = null;
    late final Future<void> started;
    started = () async {
      try {
        final List<FirmMember> people = await load();
        if (_loadedFor == firm) {
          _names = {
            for (final FirmMember m in people) m.userId.toLowerCase(): m.label,
          };
        }
      } on Object {
        // Not kept: the next timeline asks again.
        if (_loadedFor == firm) _loadedFor = null;
      } finally {
        if (identical(_inFlight, started)) _inFlight = null;
      }
    }();
    _inFlight = started;
    return started;
  }

  /// True once the active firm's people have been read.
  static bool get isLoaded => _names != null;

  /// [actor] as a person: their name if the firm has them, the text itself if
  /// it was never an id (`system`), [unknownHistoryActor] for an id the firm
  /// does not know (a platform administrator), and nothing while unread.
  static String nameFor(String actor) {
    final String id = actor.trim();
    if (id.isEmpty) return '';
    if (!_userId.hasMatch(id)) return id;
    final Map<String, String>? names = _names;
    if (names == null) return '';
    return names[id.toLowerCase()] ?? unknownHistoryActor;
  }
}

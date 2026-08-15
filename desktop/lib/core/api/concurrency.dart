import 'api_client.dart';

/// What to put on screen when a save loses a race.
///
/// The server's own sentence is "This record changed since you loaded it.
/// Reload and try again." That is right for an API caller and wrong for a
/// person, who needs to know what happened to what they typed.
///
/// [noun] names the record as the user would say it: `customer`, `vendor`,
/// `product`, `quotation`.
///
/// [changesKept] is the difference between the two shapes of editor in this
/// application, and getting it wrong tells the user a lie about their own
/// work:
///
/// * The customer editor saves from **inside** the dialog, so a refusal leaves
///   the form on screen still holding every keystroke. The message says so,
///   because the safe-looking action — closing it — is the one that discards
///   them.
/// * Every other editor returns its payload and closes, and the save happens
///   after. By the time a refusal arrives the typing is already gone, so the
///   message must not claim otherwise.
String concurrencyMessage(String noun, {required bool changesKept}) =>
    changesKept
        ? 'Somebody else saved this $noun while you were editing it. Your '
            'changes are still here and have not been sent. Copy anything you '
            'need, then close and reopen to see theirs.'
        : 'Somebody else saved this $noun while you were editing it. Your '
            'changes were not saved. Open it again to see theirs and redo '
            'yours.';

/// The message for a failed save, whatever the cause.
///
/// One helper rather than a conditional at every call site: a screen that
/// forgets the conflict branch shows the server's sentence, which reads as
/// though the edit were merely refused and gives no hint about the typing.
String saveFailureMessage(
  ApiException exception,
  String noun, {
  required bool changesKept,
}) =>
    exception.isConflict
        ? concurrencyMessage(noun, changesKept: changesKept)
        : exception.message;

/// The version to send as a precondition, or null when there is none to send.
///
/// Zero means the server did not publish one — an older backend, or a response
/// that predates the field — and the save then carries no precondition rather
/// than a version nobody read. Sending a guess would refuse every edit.
int? preconditionFor(int version) => version > 0 ? version : null;

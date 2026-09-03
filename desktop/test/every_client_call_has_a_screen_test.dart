// Every method on `ApiClient` should be reachable from a screen.
//
// The backend's `test_routes_have_a_caller.py` is the outer half of this and
// cannot see the inner half: a path named anywhere in `api_client.dart` counts
// as a caller there, so a route can have a client method while no screen can
// reach it. Six features shipped that way between 2026-09-02 and 2026-09-03 --
// charging for delivery, raising a proforma, spending loyalty points, sweeping
// lapsed ones, naming the order a deposit came in against, and reading what has
// been paid against an order. Every one passed the backend guard.
//
// A client method with no caller is not automatically a defect. Some are the
// single-record read of a resource whose editors open from list rows, which is
// this application's documented shape. So this does not forbid them: it splits
// them into the ones that have been looked at and judged fine, and the ones
// that are a real hole somebody has to close. A method in neither list fails
// the build, which makes adding one a deliberate act with a reason beside it.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// A public method declaration on `ApiClient`, at class indentation.
final RegExp _declaration = RegExp(
  r'^  (?:Future<[^>]*>|[A-Z]\w*[^=;{()]*)\s+([a-z]\w+)\s*\(',
  multiLine: true,
);

/// Plumbing every other method goes through. Not features, and a caller for
/// them would be a screen bypassing the client's own error and retry handling.
const Set<String> _plumbing = <String>{
  'request',
  'multipartRequest',
  'downloadBytes',
  'downloadText',
  'reportClientErrors',
};

/// Judged, and right as it is.
const Map<String, String> _accepted = <String, String>{
  'batchRecord': 'the single-record read; the batch screens open their editors '
      'from list rows, which is why a version is a field on the row as well as '
      'an ETag on the record',
  'lotRecord': 'as batchRecord',
  'serialRecord': 'as batchRecord',
  'salesReturn': 'as batchRecord -- the list row carries what the editor needs',
  'journalEntry': 'as batchRecord',
  'beatPlan': 'as batchRecord',
  'einvoiceRegistration': 'as batchRecord; the registrations list carries the '
      'reference, the mode and the failure reason already',
  'postCustomerReceivableTransaction':
      'deliberately unreachable. It moves a customer balance without writing a '
          'journal, so the two books drift by every rupee recorded through it -- '
          'money is recorded through /receipts and /payments, which post',
  'customerReceivableSummary':
      'superseded by the customer statement and ageing screens, which '
          'reconcile the bills against the account rather than reporting one side',
  'customerReceivableTransactions': 'superseded by the customer statement',
  'importPurchaseOrdersJson':
      'the JSON twin of importPurchaseOrdersFile, which the import dialog uses '
          '-- a screen posting rows it parsed itself would be a second parser',
};

/// Real holes: a feature the backend serves and no screen can reach.
///
/// Found by sweep on 2026-09-03, after #195 fixed six of the same shape by
/// hand. Each entry is a feature a firm is paying for and cannot use. Take one
/// off this list by wiring it, never by moving it to `_accepted`.
const Map<String, String> _knownGaps = <String, String>{
  'createTaxSystem': 'a tax system can be deleted from the desktop and not '
      'created, which is worse than neither',
  'updateTaxSystem': 'as createTaxSystem',
  'restoreTaxSystem': 'a soft-deleted tax system cannot be brought back',
  'restoreTaxProfile': 'a soft-deleted tax profile cannot be brought back',
  'restoreTaxComponent': 'a soft-deleted tax component cannot be brought back',
  'createLedgerAccount': 'the chart of accounts is read-only, so a firm cannot '
      'add an account',
  'updateLedgerAccount': 'as createLedgerAccount',
  'accountGroups': 'the grouping a ledger-account editor needs',
  'updateCommissionPayout': 'a draft payout cannot be adjusted, though the '
      'service takes a reason and expects it to be',
  'cancelPhysicalCount': 'a count can be opened, recorded and posted, and not '
      'called off',
  'updateGoodsReceipt': 'a receipt cannot be corrected before completion',
  'beatPlanCallList': "the plan's own call list, which is the point of a plan",
  'searchTerritories': 'the territory search endpoint',
  'resetUserPreferences': 'preferences cannot be put back to their defaults',
  'bulkDeleteBranches': 'no screen offers it',
  'bulkRestoreBranches': 'no screen offers it',
  'bulkDeleteWarehouses': 'no screen offers it',
  'bulkRestoreWarehouses': 'no screen offers it',
  'bulkDeleteVendors': 'no screen offers it',
  'bulkRestoreVendors': 'no screen offers it',
};

/// Every method name referenced from anywhere in `lib/` but the client itself.
///
/// A call or a tear-off passed as a callback -- `ResourceDefinition` takes the
/// second form, so matching only `name(` would report every resource screen's
/// reads as unreachable.
Set<String> _referenced(Set<String> declared) {
  final Set<String> found = <String>{};
  for (final FileSystemEntity entity
      in Directory('lib').listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith('.dart')) continue;
    if (entity.path
        .replaceAll(r'\', '/')
        .endsWith('core/api/api_client.dart')) {
      continue;
    }
    final String source = entity.readAsStringSync();
    for (final String name in declared) {
      if (RegExp('\\.$name\\b').hasMatch(source)) found.add(name);
    }
  }
  return found;
}

Set<String> _declared() {
  final File file = File('lib/core/api/api_client.dart');
  // Run from the desktop root or not at all -- a silent pass because the tree
  // was not found is the failure this guard exists to prevent.
  expect(file.existsSync(), isTrue,
      reason: 'run `flutter test` from `desktop/`');
  return _declaration
      .allMatches(file.readAsStringSync())
      .map((match) => match.group(1)!)
      .toSet();
}

void main() {
  test('every ApiClient method is reachable from a screen', () {
    final Set<String> declared = _declared()..removeAll(_plumbing);
    final Set<String> referenced = _referenced(declared);

    final List<String> unexplained = (declared
          ..removeAll(referenced)
          ..removeAll(_accepted.keys)
          ..removeAll(_knownGaps.keys))
        .toList()
      ..sort();

    expect(
      unexplained,
      isEmpty,
      reason: 'these client methods exist and no screen can reach them:\n  '
          '${unexplained.join('\n  ')}\n\n'
          'Give each one a control, or record it in `_accepted` with the '
          'reason it needs none. Do not put a real hole in `_accepted` -- '
          '`_knownGaps` is where those go, and they come off it by being '
          'wired.',
    );
  });

  test('a gap that has been closed is taken off the list', () {
    // The list is only worth keeping if it shrinks. A method wired up while
    // its entry stays behind leaves the next reader believing a feature is
    // unreachable when it is not, which is how a stale note talks somebody out
    // of checking.
    final Set<String> declared = _declared();
    final Set<String> referenced = _referenced(declared);

    final List<String> stale = <String>[
      for (final String name in <String>{..._knownGaps.keys, ..._accepted.keys})
        if (referenced.contains(name)) name,
    ]..sort();

    expect(stale, isEmpty,
        reason: 'these now have a caller and should come off `_knownGaps` / '
            '`_accepted`:\n  ${stale.join('\n  ')}');
  });
}

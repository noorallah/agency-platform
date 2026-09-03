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
//
// **A route can be reachable while its named method is not.**
// `ResourceManagementPage` writes through a generic `api.create(resource, ...)`
// and `api.update(resource, id, ...)`, so a screen declaring
// `resource: 'finance/ledger-accounts'` reaches POST and PATCH on that path
// without ever naming `createLedgerAccount`. Counting method names alone
// therefore reports a screen that exists as a hole -- which it did, for the
// whole chart of accounts, until somebody opened the workspace and looked.
// `_genericallyReachable` closes that: a method whose path matches a declared
// `resource:` counts as reached, and the mistake cannot be made by reading
// this file's output again.

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
  'searchTerritories':
      'the territory workspace searches through `territories(search:)`, the '
          'list endpoint every other master screen uses -- /search is a second '
          'way to ask one question',
  'resetUserPreferences':
      'every preference it resets is already settable from the control that '
          'owns it -- the appearance chooser and the firm switcher -- so it is '
          'a convenience over reachable settings rather than a capability '
          'nobody has',
  'bulkDeleteBranches':
      'deleting a branch is reachable one row at a time, and the bulk endpoint '
          'runs the same `_assert_branch_removable` guard and audits each row. '
          'Multi-select across three masters screens that are edited rarely is '
          'a second path to a capability that already has one -- recorded as a '
          'judgement, and worth building if somebody actually retires branches '
          'in batches',
  'bulkRestoreBranches': 'as bulkDeleteBranches',
  'bulkDeleteWarehouses': 'as bulkDeleteBranches',
  'bulkRestoreWarehouses': 'as bulkDeleteBranches',
  'bulkDeleteVendors': 'as bulkDeleteBranches',
  'bulkRestoreVendors': 'as bulkDeleteBranches',
  'createTaxSystem':
      'superseded by POST /tax-framework/setup, which the tax setup page uses: '
          'a system is created with its components and profiles in one atomic '
          'call, and creating the bare system leaves a setup half made',
  'updateTaxSystem': 'superseded by PUT /tax-framework/setup/{id}, as '
      'createTaxSystem',
};

/// Real holes: a feature the backend serves and no screen can reach.
///
/// Found by sweep on 2026-09-03, after #195 fixed six of the same shape by
/// hand. Each entry is a feature a firm is paying for and cannot use. Take one
/// off this list by wiring it, never by moving it to `_accepted`.
const Map<String, String> _knownGaps = <String, String>{
  'updateGoodsReceipt':
      'the only capability still unreachable. A receipt can be created, '
          'completed, cancelled and closed, but a draft cannot be corrected, '
          'so a wrong quantity or warehouse means cancelling and re-keying '
          'every line -- and the service takes the edit precisely so it need '
          'not. Left because the editor is built around picking a purchase '
          'order and has to be reshaped to open an existing receipt, which is '
          'a bigger piece than the rest of this list rather than a smaller one',
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

/// Every `/api/v1/...` path each client method builds, by method name.
///
/// Read off the method body rather than guessed from the name, because the
/// two disagree often enough to matter.
Map<String, String> _pathsByMethod(String client) {
  final Map<String, String> paths = <String, String>{};
  final List<RegExpMatch> declarations =
      _declaration.allMatches(client).toList();
  for (int index = 0; index < declarations.length; index++) {
    final int start = declarations[index].start;
    final int end = index + 1 < declarations.length
        ? declarations[index + 1].start
        : client.length;
    final RegExpMatch? path =
        RegExp(r"'(/api/v1/[^']*)'").firstMatch(client.substring(start, end));
    if (path != null) paths[declarations[index].group(1)!] = path.group(1)!;
  }
  return paths;
}

/// Methods whose route a screen already reaches through the generic resource
/// machinery.
///
/// `ResourceManagementPage` takes `resource: 'finance/ledger-accounts'` and
/// calls `api.create` / `api.update` / `api.delete` against it, so the named
/// twins are reached in effect even though nothing writes their names. This
/// is the check whose absence made the chart of accounts look read-only when
/// it has always been editable.
Set<String> _genericallyReachable(Map<String, String> paths) {
  final Set<String> resources = <String>{};
  for (final FileSystemEntity entity
      in Directory('lib').listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith('.dart')) continue;
    for (final RegExpMatch match in RegExp(r"(?:optionsR|r)esource: '([^']+)'")
        .allMatches(entity.readAsStringSync())) {
      resources.add(match.group(1)!);
    }
  }
  return <String>{
    for (final MapEntry<String, String> entry in paths.entries)
      for (final String resource in resources)
        if (entry.value == '/api/v1/$resource' ||
            entry.value.startsWith('/api/v1/$resource/\$'))
          entry.key,
  };
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
    final String client =
        File('lib/core/api/api_client.dart').readAsStringSync();
    final Set<String> declared = _declared()..removeAll(_plumbing);
    final Set<String> referenced = _referenced(declared)
      ..addAll(_genericallyReachable(_pathsByMethod(client)));

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
    final String client =
        File('lib/core/api/api_client.dart').readAsStringSync();
    final Set<String> declared = _declared();
    final Set<String> referenced = _referenced(declared)
      ..addAll(_genericallyReachable(_pathsByMethod(client)));

    final List<String> stale = <String>[
      for (final String name in <String>{..._knownGaps.keys, ..._accepted.keys})
        if (referenced.contains(name)) name,
    ]..sort();

    expect(stale, isEmpty,
        reason: 'these now have a caller and should come off `_knownGaps` / '
            '`_accepted`:\n  ${stale.join('\n  ')}');
  });
}

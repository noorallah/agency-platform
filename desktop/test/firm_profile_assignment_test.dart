// The Profile Assignment grid shows which profile each firm has.
//
// It could not before, and the reason is worth keeping: assignments live in
// each firm's own store, so there is no single query for this list. The server
// iterates the stores; this client reads one call and joins it onto the rows.
//
// The cell is never blank. "No profile", "the store could not be read" and
// "not loaded yet" are three different situations, and an empty cell reads as
// "nothing to do here" for all of them — on a screen whose whole job is to
// show what is assigned.

import 'package:agency_desktop/models/entities.dart';
import 'package:flutter_test/flutter_test.dart';

FirmProfileAssignment _row({
  String code = 'WHOLESALE',
  String name = 'Wholesale Distribution',
  bool active = true,
  String reason = '',
}) =>
    FirmProfileAssignment.fromJson(<String, dynamic>{
      'firm_id': 'firm-1',
      'business_profile_code': code,
      'business_profile_name': name,
      'is_active': active,
      'unavailable_reason': reason,
    });

void main() {
  test('an assigned profile shows its code', () {
    expect(_row().label, 'WHOLESALE');
  });

  test('an inactive assignment says so rather than looking assigned', () {
    // A profile that is assigned but switched off decides nothing, so showing
    // the bare code would overstate what the firm is operating on.
    expect(_row(active: false).label, 'WHOLESALE (inactive)');
  });

  test('a firm with no assignment says "Not assigned"', () {
    expect(_row(code: '', name: '').label, 'Not assigned');
  });

  test('a store that could not be read is not shown as unassigned', () {
    // This is the distinction that matters. An unprovisioned firm needs a
    // setup step; an unassigned one needs a decision. Rendering both as "Not
    // assigned" invites the administrator to fix the wrong thing.
    final FirmProfileAssignment unreadable = _row(
      code: '',
      name: '',
      reason: "Firm storage for 'ELEC01' has not been provisioned yet.",
    );

    expect(unreadable.label, 'Unavailable');
    expect(unreadable.isUnavailable, isTrue);
    expect(unreadable.hasProfile, isFalse);
  });

  test('unavailable wins over a stale profile value', () {
    // If the server ever sends both, the failure is the more important fact.
    expect(_row(reason: 'connection refused').label, 'Unavailable');
  });

  test('a missing field parses rather than throwing', () {
    final FirmProfileAssignment sparse =
        FirmProfileAssignment.fromJson(<String, dynamic>{'firm_id': 'firm-1'});

    expect(sparse.label, 'Not assigned');
    expect(sparse.isActive, isFalse);
  });
}

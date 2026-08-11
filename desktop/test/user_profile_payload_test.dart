// The user create form shows Mobile and Profile photo, so the create request
// has to carry them.
//
// It did not: the create branch of the payload builder sent six fields and
// dropped the eighteen profile ones, so a mobile number typed at creation was
// discarded and the record opened blank afterwards. The server half of the
// same defect is covered by
// backend/tests/unit/test_identity_hardening.py::
// test_creating_a_user_keeps_the_profile_fields_it_was_given.

import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('the profile payload carries what the form collected', () {
    final Json payload = userProfilePayload({
      'personal_mobile': '+91 98765 43210',
      'profile_photo_url': 'https://photos.example.test/p.png',
      'employee_code': 'EMP-0042',
      'department': 'Sales',
    });

    expect(payload['personal_mobile'], '+91 98765 43210');
    expect(payload['profile_photo_url'], 'https://photos.example.test/p.png');
    expect(payload['employee_code'], 'EMP-0042');
    expect(payload['department'], 'Sales');
  });

  test('a blank box clears the field rather than storing an empty string', () {
    final Json payload = userProfilePayload({
      'personal_mobile': '   ',
      'profile_photo_url': '',
    });

    expect(payload['personal_mobile'], isNull);
    expect(payload['profile_photo_url'], isNull);
  });

  test('address and document lists default to empty, never null', () {
    final Json payload = userProfilePayload(<String, dynamic>{});

    expect(payload['profile_addresses'], isEmpty);
    expect(payload['profile_documents'], isEmpty);
  });
}

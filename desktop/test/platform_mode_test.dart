import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:flutter_test/flutter_test.dart';

/// Where a session lands, and who may work with no firm at all.
///
/// `platform-admin@agency.local` carries `ALL_FIRMS` and **zero** firm
/// memberships, so `/me/firms` answered an empty list and its switcher had
/// nothing in it -- while its token carried every permission code, so the
/// sidebar offered Sales, Purchases and Inventory on a context that could not
/// send `X-Firm-ID`. The backend half of the fix widens that list. This is the
/// other half: a firm reached by the designation is a place to go *to*, not
/// the place to start.
AssignedFirm _firm(String id, {bool primary = false}) => AssignedFirm(
      id: id,
      code: id.toUpperCase(),
      name: 'Firm $id',
      isPrimary: primary,
    );

void main() {
  group('where a session lands', () {
    final List<AssignedFirm> firms = [
      _firm('a'),
      _firm('b', primary: true),
      _firm('c'),
    ];

    test('an ordinary user lands on their primary firm', () {
      // Over the one they last used: the primary is theirs to choose from
      // the user menu, and read the other way round the flag meant nothing
      // to anybody who ever switched. `primary_firm_test.dart` has the rest.
      expect(
        SessionController.resolveLandingFirm(firms, 'c',
                isPlatformAdmin: false)
            ?.id,
        'b',
      );
    });

    test('and on the firm they last used when none is primary', () {
      final List<AssignedFirm> unmarked = [_firm('a'), _firm('b'), _firm('c')];
      expect(
        SessionController.resolveLandingFirm(unmarked, 'c',
                isPlatformAdmin: false)
            ?.id,
        'c',
      );
    });

    test('a platform administrator always lands on the platform', () {
      // Every time, whatever they were last working in: their designation
      // reaches every firm's books, so restoring one would drop them into
      // somebody's ledgers on a screen that looks like their own.
      expect(
        SessionController.resolveLandingFirm(firms, 'c', isPlatformAdmin: true),
        isNull,
      );
      expect(
        SessionController.resolveLandingFirm(firms, null,
            isPlatformAdmin: true),
        isNull,
      );
    });

    test('somebody with no firms lands nowhere either way', () {
      expect(
        SessionController.resolveLandingFirm(const [], null,
            isPlatformAdmin: false),
        isNull,
      );
    });
  });

  group('choosing the platform', () {
    SessionController controller({required bool platformAdmin}) =>
        SessionController(
          baseUrl: 'http://localhost:8000',
          isPlatformAdmin: () => platformAdmin,
        );

    test('is offered to a platform administrator', () {
      expect(controller(platformAdmin: true).canWorkWithoutAFirm, isTrue);
    });

    test('is not offered to anybody else', () {
      // For an ordinary user a null firm is not a mode, it is an empty
      // application: every module they hold is their firm's own business.
      expect(controller(platformAdmin: false).canWorkWithoutAFirm, isFalse);
    });

    test('and is refused rather than silently emptying their sidebar', () async {
      await expectLater(
        controller(platformAdmin: false).switchFirm(null),
        throwsA(isA<ApiException>()),
      );
    });
  });

  group('the picker distinguishes dismissal from choosing the platform', () {
    test('a chosen firm carries its id', () {
      expect(const FirmChoice('firm-1').firmId, 'firm-1');
    });

    test('the platform carries none', () {
      // Which is why this is a class and not a `String?`: `showDialog` already
      // answers null for a dismissal, and conflating the two would make
      // pressing Escape switch an administrator out of the firm they were in.
      expect(const FirmChoice(null).firmId, isNull);
    });
  });
}

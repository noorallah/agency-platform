import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/identity/profile_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A person sees what is held about them without holding `USER_VIEW`.
///
/// The only screens that showed a name, a mobile number or an employee code
/// were the administration grid and forms, behind `USER_VIEW`. Most people do
/// not hold it, so most people could see nothing about themselves. This is a
/// read of `GET /me`, gated on being signed in, and it is read-only: changing
/// these is an administrator's job, and the dialog says so.
Map<String, dynamic> _me({bool platformAdmin = false}) => {
      'id': 'u-1',
      'email': 'asha@example.com',
      'full_name': 'Asha Rao',
      'is_platform_admin': platformAdmin,
      'primary_firm_id': 'firm-1',
      'last_login_at': '2026-09-08T04:18:36Z',
      'profile': {
        'employee_code': 'EMP-042',
        'department': 'Sales',
        'designation': 'Area Manager',
        'personal_mobile': '+91 98765 43210',
        'joining_date': '2024-04-01T00:00:00Z',
      },
      'roles': [
        {'code': 'VIEWER', 'name': 'Viewer', 'firm_id': null, 'firm_code': null},
        {
          'code': 'SALES_MANAGER',
          'name': 'Sales Manager',
          'firm_id': 'firm-1',
          'firm_code': 'WHOLE01',
        },
        {
          'code': 'CASHIER',
          'name': 'Cashier',
          'firm_id': 'firm-2',
          'firm_code': 'ELEC01',
        },
      ],
    };

class _Api extends ApiClient {
  _Api({required this.answer, this.fail = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  final Map<String, dynamic> answer;
  final bool fail;

  @override
  Future<CurrentUser> me() async {
    if (fail) throw const ApiException('Server unavailable.', statusCode: 503);
    return CurrentUser.fromJson(answer);
  }
}

const List<AssignedFirm> _firms = [
  AssignedFirm(id: 'firm-1', code: 'WHOLE01', name: 'Wholesale', isPrimary: true),
  AssignedFirm(id: 'firm-2', code: 'ELEC01', name: 'Electro', isPrimary: false),
];

Future<void> _pump(WidgetTester tester, _Api api, {CurrentUser? known}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1200, 900);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ProfileDialog(api: api, firms: _firms, known: known),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows who they are and what is held about them',
      (tester) async {
    await _pump(tester, _Api(answer: _me()));

    expect(find.text('Asha Rao'), findsOneWidget);
    expect(find.text('asha@example.com'), findsOneWidget);
    expect(find.text('EMP-042'), findsOneWidget);
    expect(find.text('Area Manager'), findsOneWidget);
    expect(find.text('+91 98765 43210'), findsOneWidget);
    // A date, not a timestamp.
    expect(find.text('2024-04-01'), findsOneWidget);
    expect(find.text('2026-09-08 04:18 UTC'), findsOneWidget);
  });

  testWidgets('says Not set rather than leaving a blank', (tester) async {
    // A blank reads as a field that failed to load; this one holds nothing.
    await _pump(tester, _Api(answer: _me()));

    expect(find.text('Not set'), findsWidgets);
  });

  testWidgets('groups roles by where they apply', (tester) async {
    await _pump(tester, _Api(answer: _me()));

    expect(find.text('In every firm'), findsOneWidget);
    expect(find.text('Viewer'), findsOneWidget);
    expect(find.text('In WHOLE01'), findsOneWidget);
    expect(find.text('Sales Manager'), findsOneWidget);
    expect(find.text('In ELEC01'), findsOneWidget);
    expect(find.text('Cashier'), findsOneWidget);
  });

  testWidgets('marks the primary firm and the designation', (tester) async {
    await _pump(tester, _Api(answer: _me(platformAdmin: true)));

    expect(find.text('Primary'), findsOneWidget);
    expect(find.text('Wholesale (WHOLE01)'), findsOneWidget);
    expect(find.text('Platform administrator'), findsOneWidget);
  });

  testWidgets('an ordinary user carries no designation chip', (tester) async {
    await _pump(tester, _Api(answer: _me()));

    expect(find.text('Platform administrator'), findsNothing);
  });

  testWidgets('a failed refresh keeps what the session knew and says so',
      (tester) async {
    await _pump(
      tester,
      _Api(answer: _me(), fail: true),
      known: CurrentUser.fromJson(_me()),
    );

    expect(find.text('Asha Rao'), findsOneWidget);
    expect(find.textContaining('the refresh failed'), findsOneWidget);
  });

  testWidgets('says these are the administrator\'s to change', (tester) async {
    await _pump(tester, _Api(answer: _me()));

    expect(find.textContaining('held by your administrator'), findsOneWidget);
    expect(find.byType(TextField), findsNothing, reason: 'read-only');
  });
}

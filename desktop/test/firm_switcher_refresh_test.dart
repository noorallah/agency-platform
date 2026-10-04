// The firm switcher offers a firm created this session (D-UI-4): the list is
// fetched once at sign-in, so the switcher re-reads it as it opens -- one
// `/me/firms` call -- and keeps the cached list when that read fails.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

AssignedFirm _firm(String id, String name) => AssignedFirm.fromJson(
      <String, dynamic>{'id': id, 'code': id.toUpperCase(), 'name': name},
    );

class _Api extends ApiClient {
  _Api(this.server)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  List<AssignedFirm> server;
  bool failing = false;
  int reads = 0;

  @override
  Future<List<AssignedFirm>> myFirms() async {
    reads++;
    if (failing) throw const ApiException('offline');
    return server;
  }
}

Future<void> _open(WidgetTester tester, SessionController session) async {
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: FirmSwitcherDialog(session: session)),
  ));
}

void main() {
  testWidgets('a firm added server-side appears without signing out',
      (tester) async {
    final _Api api = _Api(<AssignedFirm>[_firm('f1', 'Alpha Traders')]);
    final SessionController session =
        SessionController(baseUrl: 'http://localhost:8000')..api = api;
    await session.refreshFirms();
    expect(session.firms.map((f) => f.name), ['Alpha Traders']);
    api.reads = 0;

    // A firm is created while the session is open.
    api.server = <AssignedFirm>[
      _firm('f1', 'Alpha Traders'),
      _firm('f2', 'Beta Stores'),
    ];
    await _open(tester, session);
    await tester.pumpAndSettle();

    expect(find.text('Alpha Traders'), findsOneWidget);
    expect(find.text('Beta Stores'), findsOneWidget);
    expect(api.reads, 1);
  });

  testWidgets('a failed read keeps the cached list', (tester) async {
    final _Api api = _Api(<AssignedFirm>[_firm('f1', 'Alpha Traders')]);
    final SessionController session =
        SessionController(baseUrl: 'http://localhost:8000')..api = api;
    await session.refreshFirms();
    api.failing = true;

    await _open(tester, session);
    await tester.pumpAndSettle();

    expect(find.text('Alpha Traders'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

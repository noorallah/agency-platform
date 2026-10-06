// Approval in levels (PLT-1): the pending list reads, signing sends the
// document and its type, rejecting sends the reason, a bulk reject sends the
// ticked items of one type with one reason, and the rules editor sends
// exactly the declared keys.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/approvals/approval_rules_dialog.dart';
import 'package:agency_desktop/ui/approvals/approvals_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool manage = true}) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'SALES_APPROVE',
      'PURCHASE_APPROVE',
      if (manage) ...['SALES_MANAGE_SETTINGS', 'PURCHASE_MANAGE_SETTINGS'],
    ],
  }));

Json _status(
  String id, {
  String type = 'SALES_ORDER',
  String status = 'SUBMITTED',
  String amount = '150000.00',
}) =>
    <String, dynamic>{
      'document_type': type,
      'document_id': id,
      'document_number': 'DOC-$id',
      'amount': amount,
      'status': status,
      'steps': [
        {
          'level': 1,
          'roles': ['SALES_MANAGER'],
          'signed_by': 'u-1',
          'signed_at': '2026-10-03T09:00:00Z',
        },
        {
          'level': 2,
          'roles': ['FINANCE'],
          'signed_by': null,
          'signed_at': null,
        },
      ],
      'next_level': 2,
      'rejected_reason': null,
      'rejected_at': null,
    };

class _Api extends ApiClient {
  _Api({this.pending = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> pending;
  final List<String> requested = <String>[];
  Json? signBody;
  Json? rejectBody;
  Json? bulkBody;
  Json? rulesBody;
  String? rulesType;

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    requested.add('$method $path');
    if (method == 'GET' && path == '/api/v1/approvals/pending') {
      return <String, dynamic>{'data': pending};
    }
    if (method == 'POST' && path == '/api/v1/approvals/sign-off') {
      signBody = body;
      return <String, dynamic>{'data': _status('o-1', status: 'APPROVED')};
    }
    if (method == 'POST' && path == '/api/v1/approvals/reject') {
      rejectBody = body;
      return <String, dynamic>{'data': _status('o-1', status: 'REJECTED')};
    }
    if (method == 'POST' && path == '/api/v1/approvals/bulk-reject') {
      bulkBody = body;
      return <String, dynamic>{
        'data': {
          'done': 2,
          'refused': 0,
          'results': [
            {'id': 'o-1', 'number': 'DOC-o-1', 'outcome': 'DONE'},
            {'id': 'o-2', 'number': 'DOC-o-2', 'outcome': 'DONE'},
          ],
        },
      };
    }
    if (method == 'GET' &&
        path.startsWith('/api/v1/approvals/') &&
        path.split('/').length == 6) {
      return <String, dynamic>{'data': _status(path.split('/').last)};
    }
    if (method == 'GET' && path == '/api/v1/approvals/rules') {
      return <String, dynamic>{
        'data': [
          {
            'id': 'r-1',
            'document_type': 'SALES_ORDER',
            'level': 1,
            'min_amount': '50000',
            'role_code': 'SALES_MANAGER',
          },
        ],
      };
    }
    if (method == 'PUT' && path.startsWith('/api/v1/approvals/rules/')) {
      rulesType = path.split('/').last;
      rulesBody = body;
      return <String, dynamic>{'data': const <Json>[]};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('approvals'),
    );

Future<void> _pump(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: ApprovalsPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String number) async {
  await tester.tap(find.text(number).first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the pending list renders with the steps summary',
      (tester) async {
    await _pump(tester, _Api(pending: [_status('o-1')]));
    expect(find.text('DOC-o-1'), findsOneWidget);
    expect(find.text('Sales order'), findsOneWidget);
    expect(find.text('1,50,000.00'), findsOneWidget);
    expect(find.text('Level 2'), findsOneWidget);
    expect(find.text('L1 signed, L2 awaiting FINANCE'), findsOneWidget);
    await _select(tester, 'DOC-o-1');
    expect(find.byKey(const ValueKey('approval-details')), findsOneWidget);
    expect(find.textContaining('signed by u-1'), findsOneWidget);
  });

  testWidgets('sign off sends the document and its type', (tester) async {
    final _Api api = _Api(pending: [_status('o-1')]);
    await _pump(tester, api);
    await _select(tester, 'DOC-o-1');
    await tester.tap(find.byKey(const ValueKey('selection-sign-off')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sign-off-confirm')));
    await tester.pumpAndSettle();
    expect(api.signBody, <String, dynamic>{
      'document_type': 'SALES_ORDER',
      'document_id': 'o-1',
    });
  });

  testWidgets('reject sends the reason', (tester) async {
    final _Api api = _Api(pending: [_status('o-1')]);
    await _pump(tester, api);
    await _select(tester, 'DOC-o-1');
    await tester.tap(find.byKey(const ValueKey('selection-reject')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Price too low');
    await tester.pump();
    await tester.tap(find.text('Reject').last);
    await tester.pumpAndSettle();
    expect(api.rejectBody, <String, dynamic>{
      'document_type': 'SALES_ORDER',
      'document_id': 'o-1',
      'reason': 'Price too low',
    });
  });

  testWidgets('bulk reject sends the ticked items and one reason',
      (tester) async {
    final _Api api =
        _Api(pending: [_status('o-1'), _status('o-2'), _status('o-3')]);
    await _pump(tester, api);
    final Finder boxes = find.byType(Checkbox);
    // The first box is the header's "all"; tick the first two rows.
    await tester.tap(boxes.at(1));
    await tester.pump();
    await tester.tap(boxes.at(2));
    await tester.pump();
    await tester
        .tap(find.byKey(const ValueKey('selection-bulk-reject')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Not agreed');
    await tester.pump();
    await tester.tap(find.text('Reject documents'));
    await tester.pumpAndSettle();
    expect(api.bulkBody, <String, dynamic>{
      'document_type': 'SALES_ORDER',
      'items': [
        {'id': 'o-1'},
        {'id': 'o-2'},
      ],
      'reason': 'Not agreed',
    });
  });

  testWidgets('the rules editor sends the declared keys', (tester) async {
    final _Api api = _Api();
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ApprovalRulesDialog(api: api, permissions: _permissions()),
      ),
    ));
    await tester.pumpAndSettle();
    // The existing level 1 row is read in; add a level 2 beside it.
    expect(find.byKey(const ValueKey('approval-rule-amount-0')),
        findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('approval-rule-add')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('approval-rule-amount-1')), '200000');
    await tester.enterText(
        find.byKey(const ValueKey('approval-rule-role-1')), 'FINANCE');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('approval-rules-save')));
    await tester.pumpAndSettle();
    expect(api.rulesType, 'SALES_ORDER');
    expect(api.rulesBody, <String, dynamic>{
      'rules': [
        {'level': 1, 'min_amount': '50000', 'role_code': 'SALES_MANAGER'},
        {'level': 2, 'min_amount': '200000', 'role_code': 'FINANCE'},
      ],
    });
  });
}

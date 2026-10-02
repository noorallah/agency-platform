import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/customer_records.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Bank accounts and files on the phase 2 customer record (MST-4).
Json _customerJson() => <String, dynamic>{
      'id': 'cust-1',
      'version': 4,
      'firm_id': 'firm-1',
      'code': 'CUS-001',
      'customer_type': 'BUSINESS',
      'name': 'Anand Agencies',
      'display_name': 'Anand Agencies',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '50000.00',
      'current_outstanding': '0.00',
      'payment_terms_days': 30,
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
    };

CustomerBankAccount _account({bool masked = false}) => CustomerBankAccount(
      id: 'b-1',
      bankName: 'HDFC Bank',
      accountName: 'Anand Agencies',
      accountNumber: masked ? 'XXXXXXXX6666' : '50100012346666',
      ifsc: 'HDFC0000123',
      isPrimary: true,
      masked: masked,
    );

class _Calls {
  List<Json>? savedAccounts;
  List<Json>? addedFiles;
  String? removedFile;
  String? refuse;
  final List<CustomerAttachment> files = [
    const CustomerAttachment(
      id: 'f-1',
      fileName: 'agreement.pdf',
      filePath: '/tmp/agreement.pdf',
      caption: 'Signed copy',
      createdAt: '2026-10-03T10:00:00Z',
    ),
  ];
}

Future<_Calls> _pump(
  WidgetTester tester, {
  bool masked = false,
  bool canManageBank = true,
  bool existing = true,
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final _Calls calls = _Calls();
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: CustomerWorkspaceDialog(
        mode: existing ? CustomerDialogMode.edit : CustomerDialogMode.create,
        customer: existing ? Customer.fromJson(_customerJson()) : null,
        onSave: (payload) async => Customer.fromJson(_customerJson()),
        loadPlaces: (level, {parentId = ''}) async => const [],
        loadBankAccounts:
            existing ? () async => [_account(masked: masked)] : null,
        onSaveBankAccounts: existing && canManageBank
            ? (accounts) async {
                if (calls.refuse != null) throw ApiException(calls.refuse!);
                calls.savedAccounts = accounts;
              }
            : null,
        loadFiles: existing ? () async => List.of(calls.files) : null,
        onAddFiles: existing
            ? (files) async {
                calls.addedFiles = files;
                calls.files.add(const CustomerAttachment(
                  id: 'f-2',
                  fileName: 'slip.pdf',
                  filePath: 'slip.pdf',
                  createdAt: '2026-10-03T11:00:00Z',
                ));
              }
            : null,
        onRemoveFile: existing
            ? (id) async {
                calls.removedFile = id;
                calls.files.removeWhere((f) => f.id == id);
              }
            : null,
        pickFiles: () async => [XFile('slip.pdf')],
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return calls;
}

Future<void> _scrollTo(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a masked number shows with the note', (tester) async {
    await _pump(tester, masked: true, canManageBank: false);
    await _scrollTo(tester, find.byKey(const ValueKey('bank-account-b-1')));
    expect(find.textContaining('XXXXXXXX6666'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('bank-accounts-masked-note')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('bank-accounts-edit')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a full number has no note', (tester) async {
    await _pump(tester);
    await _scrollTo(tester, find.byKey(const ValueKey('bank-account-b-1')));
    expect(find.textContaining('50100012346666'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('bank-accounts-masked-note')),
      findsNothing,
    );
  });

  testWidgets('saving sends the whole list', (tester) async {
    final _Calls calls = await _pump(tester);
    await _scrollTo(tester, find.byKey(const ValueKey('bank-accounts-edit')));
    await tester.tap(find.byKey(const ValueKey('bank-accounts-edit')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('bank-add')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('bank-name-1')), 'SBI');
    await tester.enterText(
        find.byKey(const ValueKey('bank-holder-1')), 'Anand Agencies');
    await tester.enterText(
        find.byKey(const ValueKey('bank-number-1')), '1234567890');
    await tester.tap(find.byKey(const ValueKey('bank-save')));
    await tester.pumpAndSettle();
    expect(calls.savedAccounts, hasLength(2));
    expect(calls.savedAccounts![0]['account_number'], '50100012346666');
    expect(calls.savedAccounts![0]['is_primary'], isTrue);
    expect(calls.savedAccounts![1], <String, dynamic>{
      'bank_name': 'SBI',
      'account_name': 'Anand Agencies',
      'account_number': '1234567890',
      'ifsc': null,
      'branch': null,
      'upi_id': null,
      'is_primary': false,
    });
    expect(find.byKey(const ValueKey('bank-save')), findsNothing);
  });

  testWidgets('a refusal stays in the dialog with the message',
      (tester) async {
    final _Calls calls = await _pump(tester, size: const Size(800, 600));
    calls.refuse = 'Only one account can be primary.';
    await _scrollTo(tester, find.byKey(const ValueKey('bank-accounts-edit')));
    await tester.tap(find.byKey(const ValueKey('bank-accounts-edit')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('bank-save')));
    await tester.pumpAndSettle();
    expect(find.text('Only one account can be primary.'), findsOneWidget);
    expect(find.byKey(const ValueKey('bank-save')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('files list, add sends the list, remove asks first',
      (tester) async {
    final _Calls calls = await _pump(tester);
    await _scrollTo(tester, find.byKey(const ValueKey('customer-file-f-1')));
    expect(find.text('agreement.pdf'), findsOneWidget);
    expect(find.textContaining('Signed copy'), findsOneWidget);
    expect(find.textContaining('2026-10-03'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('customer-files-add')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Attach photo or document'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('customer-files-save')));
    await tester.pumpAndSettle();
    expect(calls.addedFiles, hasLength(1));
    expect(calls.addedFiles!.first['file_name'], 'slip.pdf');
    expect(calls.addedFiles!.first['file_path'], 'slip.pdf');
    expect(find.byKey(const ValueKey('customer-file-f-2')), findsOneWidget);

    await tester.tap(find.byTooltip('Remove').first);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Remove'));
    await tester.pumpAndSettle();
    expect(calls.removedFile, 'f-1');
    expect(find.byKey(const ValueKey('customer-file-f-1')), findsNothing);
  });

  testWidgets('a new customer is told to save first', (tester) async {
    await _pump(tester, existing: false);
    expect(find.textContaining('Save the customer first'), findsNWidgets(2));
    expect(find.byKey(const ValueKey('bank-accounts-edit')), findsNothing);
  });
}

// Staff Advances on the wire.
//
// The widget tests hand the screen what a fake returns, so none of them can
// see an answer being read off the envelope instead of out of `data`. These
// talk to a real loopback server that answers the real envelopes.
//
// No `testWidgets` here, deliberately: that binding answers every request
// with 400 and makes no real connection.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/staff_advance.dart';
import 'package:flutter_test/flutter_test.dart';

class _Seen {
  _Seen(this.method, this.uri, this.headers, this.body);

  final String method;
  final Uri uri;
  final HttpHeaders headers;
  final String body;
}

Map<String, dynamic> _entry(String status) => <String, dynamic>{
      'id': 'en-1',
      'entry_number': 'SAD-000001',
      'entry_date': '2026-09-01',
      'kind': 'RECOVERY',
      'employee_account_id': 'emp-1',
      'employee_name': 'Ravi',
      'other_account_id': 'a-salary',
      'other_account_code': '6100',
      'other_account_name': 'Salaries',
      'other_side': 'SALARY',
      'amount': '1500.00',
      'narration': null,
      'status': status,
      'journal_entry_id': 'j-1',
      'reversal_journal_entry_id': null,
      'cancel_reason': null,
      'cancelled_at': null,
      'version': 4,
    };

Future<(ApiClient, List<_Seen>)> _start() async {
  final HttpServer server =
      await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  final List<_Seen> seen = <_Seen>[];
  server.listen((HttpRequest request) async {
    final String body = await utf8.decoder.bind(request).join();
    seen.add(_Seen(
        request.method, request.uri, request.headers, body));
    final String path = request.uri.path;
    Object? data;
    Object? pagination;
    int status = 200;
    if (path == '/api/v1/staff-advances/employees') {
      if (request.method == 'POST') {
        status = 201;
        data = <String, dynamic>{
          'account_id': 'emp-9',
          'code': 'SA-9',
          'name': 'Meena',
          'is_active': true,
          'advanced': '0.00',
          'recovered': '0.00',
          'owes': '0.00',
        };
      } else {
        data = <Map<String, dynamic>>[
          <String, dynamic>{
            'account_id': 'emp-1',
            'code': 'SA-1',
            'name': 'Ravi',
            'is_active': true,
            'advanced': '5000.00',
            'recovered': '1000.00',
            'owes': '4000.00',
          },
        ];
      }
    } else if (path == '/api/v1/staff-advances/accounts') {
      data = <String, dynamic>{
        'money_accounts': <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'a-cash',
            'code': '1000',
            'name': 'Cash',
            'kind': 'CASH',
          },
        ],
        'salary_accounts': <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'a-salary',
            'code': '6100',
            'name': 'Salaries',
            'kind': null,
          },
        ],
      };
    } else if (path == '/api/v1/staff-advances' && request.method == 'GET') {
      data = <Map<String, dynamic>>[_entry('POSTED')];
      pagination = <String, dynamic>{
        'page': 1,
        'page_size': 10,
        'total_records': 23,
        'total_pages': 3,
      };
    } else if (path == '/api/v1/staff-advances') {
      status = 201;
      data = _entry('POSTED');
    } else {
      data = _entry('CANCELLED');
    }
    request.response
      ..statusCode = status
      ..headers.contentType = ContentType.json
      ..write(jsonEncode(<String, dynamic>{
        'success': true,
        'data': data,
        'message': null,
        if (pagination != null) 'pagination': pagination,
        'timestamp': '2026-09-01T00:00:00Z',
        'requestId': 'r-1',
      }));
    await request.response.close();
  });
  addTearDown(() => server.close(force: true));
  return (
    ApiClient(
      baseUrl: 'http://127.0.0.1:${server.port}',
      accessToken: () => 'token-1',
      refreshAccessToken: () async => false,
      activeFirmId: () => 'firm-1',
    ),
    seen,
  );
}

void main() {
  test('the employee list is read out of data', () async {
    final (ApiClient api, List<_Seen> seen) = await _start();

    final List<StaffEmployee> rows = await api.staffEmployees();

    expect(seen.single.method, 'GET');
    expect(seen.single.uri.path, '/api/v1/staff-advances/employees');
    expect(rows.single.name, 'Ravi');
    expect(rows.single.accountId, 'emp-1');
    expect(rows.single.owes, '4000.00');
    expect(rows.single.owesValue, 4000.0);
    expect(rows.single.isActive, isTrue);
  });

  test('adding an employee sends the name and reads the record', () async {
    final (ApiClient api, List<_Seen> seen) = await _start();

    final StaffEmployee made = await api.addStaffEmployee('Meena');

    expect(seen.single.method, 'POST');
    expect(seen.single.uri.path, '/api/v1/staff-advances/employees');
    expect(jsonDecode(seen.single.body), <String, dynamic>{'name': 'Meena'});
    expect(made.name, 'Meena');
    expect(made.accountId, 'emp-9');
  });

  test('the account choices are read out of data', () async {
    final (ApiClient api, List<_Seen> seen) = await _start();

    final StaffAdvanceAccountChoices choices =
        await api.staffAdvanceAccountChoices();

    expect(seen.single.uri.path, '/api/v1/staff-advances/accounts');
    expect(choices.moneyAccounts.single.id, 'a-cash');
    expect(choices.moneyAccounts.single.kind, 'CASH');
    expect(choices.salaryAccounts.single.name, 'Salaries');
  });

  test('the entries come as a page with the filter in the query', () async {
    final (ApiClient api, List<_Seen> seen) = await _start();

    final PagedResult<StaffAdvanceEntry> page = await api.staffAdvances(
      page: 2,
      pageSize: 10,
      employeeAccountId: 'emp-1',
      status: 'POSTED',
    );

    expect(seen.single.method, 'GET');
    expect(seen.single.uri.path, '/api/v1/staff-advances');
    expect(seen.single.uri.queryParameters, <String, String>{
      'page': '2',
      'page_size': '10',
      'employee_account_id': 'emp-1',
      'status': 'POSTED',
    });
    expect(page.total, 23);
    expect(page.items.single.entryNumber, 'SAD-000001');
    expect(page.items.single.what, 'Recovery from salary');
    expect(page.items.single.version, 4);
  });

  test('recording sends the body and reads the entry', () async {
    final (ApiClient api, List<_Seen> seen) = await _start();

    final StaffAdvanceEntry saved =
        await api.recordStaffAdvance(<String, dynamic>{
      'kind': 'RECOVERY',
      'entry_date': '2026-09-01',
      'employee_account_id': 'emp-1',
      'other_account_id': 'a-salary',
      'amount': '1500',
      'cash_below_zero_confirmed': true,
    });

    expect(seen.single.method, 'POST');
    expect(seen.single.uri.path, '/api/v1/staff-advances');
    expect(jsonDecode(seen.single.body), <String, dynamic>{
      'kind': 'RECOVERY',
      'entry_date': '2026-09-01',
      'employee_account_id': 'emp-1',
      'other_account_id': 'a-salary',
      'amount': '1500',
      'cash_below_zero_confirmed': true,
    });
    expect(saved.id, 'en-1');
    expect(saved.employeeName, 'Ravi');
    expect(saved.amount, '1500.00');
  });

  test('cancelling sends the reason and If-Match', () async {
    final (ApiClient api, List<_Seen> seen) = await _start();

    final StaffAdvanceEntry cancelled =
        await api.cancelStaffAdvance('en-1', reason: 'Typed twice', version: 4);

    expect(seen.single.method, 'POST');
    expect(seen.single.uri.path, '/api/v1/staff-advances/en-1/cancel');
    expect(jsonDecode(seen.single.body),
        <String, dynamic>{'reason': 'Typed twice'});
    expect(seen.single.headers.value('if-match'), isNotNull);
    expect(seen.single.headers.value('if-match'), contains('4'));
    expect(cancelled.isCancelled, isTrue);
  });
}

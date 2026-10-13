// What the bill's paper looks like on the wire (backlog 151).
//
// The widget tests hand the prompt a `BillPaper` built by a fake, so none of
// them can see the answer being read out of the wrong place: the server wraps
// it in the usual envelope, and an answer read off the envelope itself says
// the firm prints on no paper at all, which opens no box. These talk to a
// real loopback server.
//
// No `testWidgets` here, deliberately: that binding answers every request
// with 400 and makes no real connection.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/bill_paper.dart';
import 'package:flutter_test/flutter_test.dart';

Future<(ApiClient, List<Uri>)> _start() async {
  final HttpServer server =
      await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  final List<Uri> asked = <Uri>[];
  server.listen((HttpRequest request) async {
    asked.add(request.uri);
    await utf8.decoder.bind(request).join();
    if (request.uri.path.endsWith('/print/paper')) {
      request.response
        ..statusCode = 200
        ..headers.contentType = ContentType.json
        ..write(jsonEncode(<String, dynamic>{
          'success': true,
          'data': <String, dynamic>{
            'firm_paper': 'HALF',
            'customer_paper': 'A4',
            'paper': 'A4',
            'fits_half_page': true,
            'may_choose': true,
          },
          'message': null,
        }));
    } else {
      request.response
        ..statusCode = 200
        ..headers.contentType = ContentType('application', 'pdf')
        ..add(<int>[37, 80, 68, 70]);
    }
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
    asked,
  );
}

void main() {
  test('the paper is read out of the envelope', () async {
    final (ApiClient api, List<Uri> asked) = await _start();

    final BillPaper paper = await api.salesInvoicePaper('inv-1');

    expect(asked.single.path, '/api/v1/sales-invoices/inv-1/print/paper');
    expect(paper.firmPaper, 'HALF');
    expect(paper.customerPaper, 'A4');
    expect(paper.paper, 'A4');
    expect(paper.fitsHalfPage, isTrue);
    expect(paper.mayChoose, isTrue);
  });

  test('the paper chosen reaches the print as a query', () async {
    final (ApiClient api, List<Uri> asked) = await _start();

    await api.salesInvoicePdf('inv-1', paper: 'HALF');
    await api.salesInvoicePdf('inv-1', referenceCopy: true, paper: 'A4');
    await api.salesInvoicePdf('inv-1');

    expect(asked[0].queryParameters, <String, String>{'paper': 'HALF'});
    expect(asked[1].queryParameters, <String, String>{
      'reference_copy': 'true',
      'paper': 'A4',
    });
    expect(asked[2].queryParameters, isEmpty);
  });
}

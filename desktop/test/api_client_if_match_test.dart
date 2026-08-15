// The `If-Match` header this client puts on the wire.
//
// Kept out of the widget tests deliberately: `TestWidgetsFlutterBinding`
// installs HttpOverrides that answer every request with 400 and make no real
// connection, so a header assertion there would pass or fail for reasons that
// have nothing to do with the header. A file with no `testWidgets` gets no
// such binding, so these talk to a real loopback server and read what actually
// arrived.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:flutter_test/flutter_test.dart';

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
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
    };

/// A loopback server that answers one canned customer, plus a reader for the
/// `If-Match` it was asked with.
class _Probe {
  _Probe(this.api, this._read);
  final ApiClient api;
  final String? Function() _read;
  String? get ifMatch => _read();

  static Future<_Probe> start() async {
    final HttpServer server =
        await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    String? received;
    server.listen((HttpRequest request) async {
      received = request.headers.value(HttpHeaders.ifMatchHeader);
      request.response
        ..statusCode = 200
        ..headers.contentType = ContentType.json
        ..write(jsonEncode(<String, dynamic>{'data': _customerJson()}));
      await request.response.close();
    });
    addTearDown(() => server.close(force: true));
    return _Probe(
      ApiClient(
        baseUrl: 'http://127.0.0.1:${server.port}',
        accessToken: () => null,
        refreshAccessToken: () async => false,
        activeFirmId: () => 'firm-1',
      ),
      () => received,
    );
  }
}

void main() {
  test('a version is sent as a quoted entity tag', () async {
    final _Probe probe = await _Probe.start();

    await probe.api
        .updateCustomer('cust-1', <String, dynamic>{}, expectedVersion: 7);

    // Quoted, because that is what an entity tag is. `parse_if_match` on the
    // server tolerates a bare number, but the standard form is what anything
    // else on the path — a proxy, a cache — knows how to read.
    expect(probe.ifMatch, '"7"');
  });

  test('no version means no header at all', () async {
    final _Probe probe = await _Probe.start();

    await probe.api.updateCustomer('cust-1', <String, dynamic>{});

    // Not `*`, and not a guess at the next number. Sending nothing is how the
    // server is told there is no precondition, which is what every call did
    // before this existed and what an older record still does.
    expect(probe.ifMatch, isNull);
  });
}

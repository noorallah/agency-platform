// D-UI-20: a connection the server drops mid-request reaches the caller as an
// ApiException, never as a raw dart:io HttpException that no screen catches.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('a dropped connection is an ApiException on every transport path',
      () async {
    // Accepts the connection and closes it without a byte of answer, which
    // dart:io reports as "Connection closed before full header was received".
    final ServerSocket server =
        await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((Socket socket) => socket.destroy());
    addTearDown(() => server.close());
    final ApiClient api = ApiClient(
      baseUrl: 'http://127.0.0.1:${server.port}',
      accessToken: () => null,
      refreshAccessToken: () async => false,
      activeFirmId: () => 'firm-1',
    );

    await expectLater(
      api.request('GET', '/api/v1/anything'),
      throwsA(isA<ApiException>()),
    );
    await expectLater(
      api.downloadText('/api/v1/anything'),
      throwsA(isA<ApiException>()),
    );
  });
}

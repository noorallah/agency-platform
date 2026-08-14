import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:flutter_test/flutter_test.dart';

/// The server address rule, which is a deployment decision with security in it.
///
/// The product puts the client on one machine and the backend on another in the
/// same building. Requiring HTTPS everywhere made that impossible without an
/// installer that puts a certificate in every client's trust store, so plain
/// HTTP over the local network is a supported choice. HTTP to a public address
/// is not, because that is the same passwords crossing the internet in clear
/// text.
///
/// These cases are the decision written down. Changing them changes what the
/// product promises about its traffic.
void main() {
  group('HTTPS is accepted anywhere', () {
    test('a public HTTPS address', () {
      expect(
        normalizeServerUrl('https://erp.example.com'),
        'https://erp.example.com',
      );
    });

    test('an HTTPS address on the local network', () {
      expect(
        normalizeServerUrl('https://192.168.1.20:8000'),
        'https://192.168.1.20:8000',
      );
    });

    test('a trailing slash is trimmed so two spellings are one server', () {
      expect(
        normalizeServerUrl('https://erp.example.com/'),
        'https://erp.example.com',
      );
    });
  });

  group('plain HTTP is accepted on the local network', () {
    for (final String url in <String>[
      'http://localhost:8000',
      'http://127.0.0.1:8000',
      'http://10.0.0.5:8000',
      'http://172.16.4.9:8000',
      'http://172.31.255.254:8000',
      'http://192.168.1.20:8000',
      'http://169.254.10.1:8000',
      'http://server01:8000',
      'http://erp.local:8000',
      'http://erp.lan:8000',
      'http://[fd00::1]:8000',
      'http://[fe80::1]:8000',
    ]) {
      test(url, () => expect(normalizeServerUrl(url), url));
    }
  });

  group('plain HTTP is refused off the local network', () {
    for (final String url in <String>[
      'http://erp.example.com',
      'http://203.0.113.10:8000',
      'http://8.8.8.8',
      // 172.32 is outside the private block, and the boundary is worth pinning:
      // reading the range as "all of 172" would open the public internet.
      'http://172.32.0.1:8000',
      'http://172.15.0.1:8000',
      'http://[2001:db8::1]:8000',
    ]) {
      test(url, () {
        expect(
          () => normalizeServerUrl(url),
          throwsA(
            isA<FormatException>().having(
              (error) => error.message,
              'message',
              contains('clear text'),
            ),
          ),
        );
      });
    }
  });

  group('the rest of the address is still constrained', () {
    for (final String url in <String>[
      'https://user:pass@erp.example.com',
      'https://erp.example.com?token=1',
      'https://erp.example.com#fragment',
      'ftp://erp.example.com',
      'not a url at all',
    ]) {
      test(url, () {
        expect(() => normalizeServerUrl(url), throwsA(isA<FormatException>()));
      });
    }
  });

  group('classifying a host', () {
    test('an address it cannot read is not local', () {
      // Erring towards "no" is the whole point: an unclassifiable host must not
      // quietly become a place plain HTTP is allowed.
      expect(isPrivateNetworkHost('999.1.1.1'), isFalse);
      expect(isPrivateNetworkHost(''), isFalse);
    });

    test('case does not change the answer', () {
      expect(isPrivateNetworkHost('ERP.LOCAL'), isTrue);
      expect(isPrivateNetworkHost('ERP.EXAMPLE.COM'), isFalse);
    });
  });
}

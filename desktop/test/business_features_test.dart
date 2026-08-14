import 'package:agency_desktop/core/business/business_features.dart';
import 'package:flutter_test/flutter_test.dart';

/// Which optional fields a firm is offered.
///
/// The server refuses a gated field it has not enabled -- a goods receipt
/// carrying an expiry date at a firm without EXPIRY_TRACKING comes back 403
/// naming the feature -- and the client used to offer the field anyway, so the
/// first anybody heard of it was a refusal after the document was keyed.
void main() {
  group('what the firm is offered', () {
    test('an enabled feature is offered', () {
      expect(
        const BusinessFeatures({'EXPIRY_TRACKING'}).isEnabled('EXPIRY_TRACKING'),
        isTrue,
      );
    });

    test('a feature the firm does not have is not offered', () {
      expect(
        const BusinessFeatures({'EXPIRY_TRACKING'}).isEnabled('VEHICLE_TRACKING'),
        isFalse,
      );
    });

    test('unknown means offered, not hidden', () {
      // The set is null before the answer arrives and after a failed call.
      // Hiding fields because a request failed would take working screens away
      // from firms entitled to them; a configuration gap is not a decision.
      const BusinessFeatures unknown = BusinessFeatures.unknown();
      expect(unknown.isEnabled('EXPIRY_TRACKING'), isTrue);
      expect(unknown.isEnabled('ANYTHING_AT_ALL'), isTrue);
      expect(unknown.isResolved, isFalse);
    });

    test('a firm with no features at all is gated, not defaulted', () {
      // An empty answer is still an answer: this firm has none of them.
      const BusinessFeatures none = BusinessFeatures({});
      expect(none.isEnabled('EXPIRY_TRACKING'), isFalse);
      expect(none.isResolved, isTrue);
    });

    test('the code is matched without case getting in the way', () {
      expect(
        const BusinessFeatures({'BARCODE'}).isEnabled('barcode'),
        isTrue,
      );
    });

    test('vehicle tracking is offered where the profile has it', () {
      // The delivery note and goods receipt both ask this before showing a
      // vehicle field. WHOLE01 has no VEHICLE_TRACKING, so both hid it, and a
      // dispatch carrying one came back 403 after the document was keyed.
      expect(
        const BusinessFeatures({'BARCODE'}).isEnabled('VEHICLE_TRACKING'),
        isFalse,
      );
      expect(
        const BusinessFeatures({'VEHICLE_TRACKING'}).isEnabled('VEHICLE_TRACKING'),
        isTrue,
      );
    });

    test('the explanation names the feature', () {
      // "Disabled" without saying by what leaves somebody guessing at their
      // own configuration.
      expect(
        const BusinessFeatures({}).explain('EXPIRY_TRACKING'),
        contains('EXPIRY_TRACKING'),
      );
    });
  });
}

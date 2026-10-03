import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/line_tax_rule.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/quotation.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/phase2/document_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('LineTaxRule', () {
    test('reads the rule off a sales invoice line', () {
      final LineTaxRule rule = LineTaxRule.fromJson(<String, dynamic>{
        'tax_rule_code': 'GST18',
        'tax_rule_version': 2,
      });
      expect(rule.code, 'GST18');
      expect(rule.version, 2);
      expect(rule.label, 'Tax rule: GST18 (v2)');
    });

    test('reads the rule off a supplier bill line', () {
      final LineTaxRule rule = LineTaxRule.fromJson(<String, dynamic>{
        'tax_rule_code': 'GST5-IN',
        'tax_rule_version': 1,
      });
      expect(rule.label, 'Tax rule: GST5-IN (v1)');
    });

    test('absent or null keys give no rule', () {
      for (final Map<String, dynamic>? json in <Map<String, dynamic>?>[
        null,
        <String, dynamic>{},
        <String, dynamic>{'tax_rule_code': null, 'tax_rule_version': null},
      ]) {
        final LineTaxRule rule = LineTaxRule.fromJson(json);
        expect(rule.code, isNull);
        expect(rule.version, isNull);
        expect(rule.label, '');
      }
    });
  });

  group('typed line models', () {
    test('quotation line parses and defaults to null', () {
      final QuotationLine with_ = QuotationLine.fromJson(<String, dynamic>{
        'tax_rule_code': 'GST12',
        'tax_rule_version': 3,
      });
      expect(with_.taxRuleCode, 'GST12');
      expect(with_.taxRuleVersion, 3);
      final QuotationLine without = QuotationLine.fromJson(<String, dynamic>{});
      expect(without.taxRuleCode, isNull);
      expect(without.taxRuleVersion, isNull);
    });

    test('goods receipt line is not written back with the rule', () {
      final GoodsReceiptLine line = GoodsReceiptLine.fromJson(<String, dynamic>{
        'tax_rule_code': 'GST18',
        'tax_rule_version': 1,
      });
      expect(line.taxRuleCode, 'GST18');
      expect(line.toJson().keys, isNot(contains('tax_rule_code')));
      expect(line.toJson().keys, isNot(contains('tax_rule_version')));
      expect(GoodsReceiptLine.fromJson(<String, dynamic>{}).taxRuleCode,
          isNull);
    });

    test('purchase order and sales return lines parse', () {
      final PurchaseOrderLine order =
          PurchaseOrderLine.fromJson(<String, dynamic>{
        'tax_rule_code': 'GST18',
        'tax_rule_version': 4,
      });
      expect(order.taxRuleCode, 'GST18');
      expect(order.taxRuleVersion, 4);
      expect(PurchaseOrderLine.fromJson(<String, dynamic>{}).taxRuleVersion,
          isNull);
      final SalesReturnLine back = SalesReturnLine.fromJson(<String, dynamic>{
        'tax_rule_code': 'GST28',
        'tax_rule_version': 1,
      });
      expect(back.taxRuleCode, 'GST28');
      expect(SalesReturnLine.fromJson(<String, dynamic>{}).taxRuleCode,
          isNull);
    });
  });

  group('line tax detail', () {
    Future<void> show(WidgetTester tester, LineTaxRule? rule) {
      return tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Column(
            children: documentTaxLines(
              taxable: 1000,
              tax: 180,
              interstate: false,
              taxRule: rule,
            ),
          ),
        ),
      ));
    }

    testWidgets('names the rule that decided the tax', (tester) async {
      await show(
        tester,
        const LineTaxRule(code: 'GST18', version: 2),
      );
      expect(find.text('Tax rule: GST18 (v2)'), findsOneWidget);
    });

    testWidgets('says nothing when no rule matched', (tester) async {
      await show(tester, const LineTaxRule());
      expect(find.textContaining('Tax rule'), findsNothing);
      await show(tester, null);
      expect(find.textContaining('Tax rule'), findsNothing);
    });
  });
}

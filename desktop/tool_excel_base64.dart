import 'dart:convert';
import 'package:excel/excel.dart' as xls;

void main() {
  final xls.Excel workbook = xls.Excel.createExcel();
  final xls.Sheet sheet = workbook['Sheet1'];
  final rows = [
    ['ProductCode', 'BranchCode', 'WarehouseCode', 'Quantity', 'ReferenceNumber', 'TransactionDate'],
    ['MED-001', 'BR-001', 'WH-001', '5', 'ADJ-001', '2026-08-02'],
  ];
  for (int rowIndex = 0; rowIndex < rows.length; rowIndex++) {
    for (int columnIndex = 0; columnIndex < rows[rowIndex].length; columnIndex++) {
      sheet.cell(xls.CellIndex.indexByColumnRow(columnIndex: columnIndex, rowIndex: rowIndex)).value = xls.TextCellValue(rows[rowIndex][columnIndex]);
    }
  }
  print(base64Encode(workbook.save()!));
}

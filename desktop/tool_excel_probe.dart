// ignore_for_file: avoid_print
//
// A developer script run with `dart run`, not part of the shipped app:
// stdout is the whole point of it.
import 'package:excel/excel.dart' as xls;

void main() {
  final xls.Excel workbook = xls.Excel.createExcel();
  final xls.Sheet sheet = workbook['Sheet1'];
  sheet.cell(xls.CellIndex.indexByColumnRow(columnIndex: 0, rowIndex: 0)).value = xls.TextCellValue('ProductCode');
  sheet.cell(xls.CellIndex.indexByColumnRow(columnIndex: 1, rowIndex: 0)).value = xls.TextCellValue('BranchCode');
  sheet.cell(xls.CellIndex.indexByColumnRow(columnIndex: 0, rowIndex: 1)).value = xls.TextCellValue('MED-001');
  sheet.cell(xls.CellIndex.indexByColumnRow(columnIndex: 1, rowIndex: 1)).value = xls.TextCellValue('BR-001');
  final bytes = workbook.save()!;
  print('saved ${bytes.length}');
  final xls.Excel decoded = xls.Excel.decodeBytes(bytes);
  print('tables ${decoded.tables.keys.join(',')}');
  final first = decoded.tables.values.first;
  print(first.rows.map((row) => row.map((cell) => cell?.value?.toString() ?? '').join('|')).join('\n'));
}

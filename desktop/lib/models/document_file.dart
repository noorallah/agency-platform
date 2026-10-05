import 'entities.dart' show Json, stringValue;

/// Which document a file is attached to: a purchase bill or a goods receipt
/// (PG-4), or one of the five sales documents (SG-6).
enum AttachableDocument {
  purchaseInvoice,
  goodsReceipt,
  quotation,
  salesOrder,
  deliveryNote,
  salesInvoice,
  salesReturn,
}

/// The biggest file the server accepts for a bill or a receipt.
const int maxDocumentFileBytes = 10 * 1024 * 1024;

/// A file kept with a supplier's bill or a goods receipt.
class DocumentFileRecord {
  const DocumentFileRecord({
    required this.id,
    required this.fileName,
    required this.contentType,
    required this.sizeBytes,
    required this.caption,
    required this.createdAt,
  });

  final String id;
  final String fileName;
  final String contentType;
  final int sizeBytes;
  final String caption;
  final String createdAt;

  factory DocumentFileRecord.fromJson(Json json) => DocumentFileRecord(
        id: stringValue(json['id']),
        fileName: stringValue(json['file_name']),
        contentType: stringValue(json['content_type']),
        sizeBytes: int.tryParse(stringValue(json['size_bytes'])) ?? 0,
        caption: stringValue(json['caption']),
        createdAt: stringValue(json['created_at']),
      );
}

/// Why a file cannot be attached, or null when it can. Checked before the
/// upload so the person is told at once; the server checks again.
String? documentFileProblem(String fileName, int sizeBytes) {
  final String lower = fileName.toLowerCase();
  const List<String> allowed = ['.pdf', '.jpg', '.jpeg', '.png'];
  if (!allowed.any(lower.endsWith)) {
    return '$fileName is not a PDF, JPG or PNG. Only those can be attached.';
  }
  if (sizeBytes > maxDocumentFileBytes) {
    final String mb = (sizeBytes / (1024 * 1024)).toStringAsFixed(1);
    return '$fileName is $mb MB; the limit is 10 MB.';
  }
  if (sizeBytes <= 0) return '$fileName is empty.';
  return null;
}

/// A size as a person reads it: 842 KB, 2.3 MB.
String documentFileSize(int bytes) {
  if (bytes >= 1024 * 1024) {
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
  if (bytes >= 1024) return '${(bytes / 1024).round()} KB';
  return '$bytes B';
}

/// The Files column: a clip and the count, blank when nothing is attached.
String documentFilesCell(Object? count) {
  final int n = int.tryParse(stringValue(count)) ?? 0;
  return n > 0 ? '\u{1F4CE} $n' : '';
}

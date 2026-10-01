import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../workspace/master_import_dialog.dart';

/// Load products from a CSV or XLSX file: the shared [MasterImportDialog]
/// wired to the product endpoints. Closes with the applied `FileImportReport`,
/// or null if nothing was imported.
class ProductImportDialog extends StatelessWidget {
  const ProductImportDialog({
    super.key,
    required this.api,
    required this.permissions,
    this.pickFileOverride,
    this.saveBytesOverride,
  });

  final ApiClient api;
  final PermissionService permissions;
  final Future<XFile?> Function()? pickFileOverride;
  final SaveBytesOverride? saveBytesOverride;

  @override
  Widget build(BuildContext context) => MasterImportDialog(
        noun: 'products',
        fileStem: 'product',
        downloadTemplate: (format) => api.productImportTemplate(format: format),
        checkFile: api.checkProductImportFile,
        canUpdate: permissions.hasPermission('PRODUCT_UPDATE'),
        pickFileOverride: pickFileOverride,
        saveBytesOverride: saveBytesOverride,
      );
}

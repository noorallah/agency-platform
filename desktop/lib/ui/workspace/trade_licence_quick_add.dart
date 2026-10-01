import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../resource_management_page.dart';

/// Opens the trade licence form pre-set to one holder -- a customer or a
/// vendor whose editor offers "Add licence" on its own Licences section
/// (backlog 54).
///
/// Reuses [CrudWorkspaceDialog] directly rather than the full trade licence
/// [ResourceDefinition]: the holder is already known here, so asking again
/// with a FIRM/CUSTOMER/VENDOR chooser would ask a question this call has
/// already answered. Returns whether a licence was saved.
Future<bool> addTradeLicenceFor(
  BuildContext context, {
  required ApiClient api,
  required String holderType,
  String? customerId,
  String? vendorId,
  required String holderLabel,
}) async {
  assert(
    holderType == 'CUSTOMER' ? customerId != null : vendorId != null,
    'A quick-added licence must name the holder it is being added for.',
  );
  final Map<String, dynamic>? values = await showDialog<Map<String, dynamic>>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) => CrudWorkspaceDialog(
      title: 'Trade Licence',
      subtitle: holderLabel,
      mode: CrudDialogMode.create,
      values: const {},
      api: api,
      fields: const [
        FieldSpec(
          key: 'licence_type_id',
          label: 'Licence type',
          optionsResource: 'trade-licences/types',
          singleSelection: true,
        ),
        FieldSpec(
          key: 'licence_number',
          label: 'Licence number',
          required: true,
        ),
        FieldSpec(key: 'issued_by', label: 'Issued by'),
        FieldSpec(
          key: 'valid_from',
          label: 'Valid from',
          kind: FieldKind.date,
        ),
        FieldSpec(
          key: 'valid_to',
          label: 'Valid to',
          kind: FieldKind.date,
          helperText: 'Required when the licence type runs out.',
        ),
        FieldSpec(key: 'premises', label: 'Premises'),
        FieldSpec(key: 'remarks', label: 'Remarks', multiline: true),
      ],
      onSave: (formValues) async {
        await api.create('trade-licences', {
          'licence_type_id': formValues['licence_type_id'],
          'holder_type': holderType,
          'branch_id': null,
          'customer_id': holderType == 'CUSTOMER' ? customerId : null,
          'vendor_id': holderType == 'VENDOR' ? vendorId : null,
          'licence_number': formValues['licence_number'],
          'issued_by': _blank(formValues['issued_by']),
          'valid_from': _blank(formValues['valid_from']),
          'valid_to': _blank(formValues['valid_to']),
          'premises': _blank(formValues['premises']),
          'remarks': _blank(formValues['remarks']),
        });
      },
    ),
  );
  return values != null;
}

String? _blank(Object? value) {
  final String text = (value ?? '').toString().trim();
  return text.isEmpty ? null : text;
}

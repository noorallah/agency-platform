import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import 'attribute_form_fields.dart';

/// The custom fields one record carries, loaded for its entity type.
///
/// The product form resolved its fields through `/products/metadata`; the
/// customer and vendor forms ask `/attribute-definitions/applicable` for the
/// same answer without a product in it. One controller for every form: it
/// loads the applicable definitions, holds one `AttributeFieldController` per
/// definition seeded from the stored values, and answers the payload. A form
/// sends `attributes` **only when the load succeeded** -- the server treats an
/// absent list as "leave them alone" and an empty one as "clear them", so a
/// form that could not read the definitions must not send the empty one.
class CustomFieldsController extends ChangeNotifier {
  CustomFieldsController({
    required this.load,
    List<AttributeValueRecord> stored = const [],
  }) : _stored = {for (final AttributeValueRecord v in stored) v.attributeDefinitionId: _storedValue(v)};

  /// Reads the applicable definitions for the entity type.
  final Future<ApplicableAttributesRecord> Function() load;
  final Map<String, String> _stored;

  List<AttributeDefinitionRecord> definitions = const [];
  Set<String> mandatoryIds = const {};
  final Map<String, AttributeFieldController> controllers = {};
  bool loaded = false;
  bool loading = false;
  String? error;

  static String _storedValue(AttributeValueRecord value) {
    if (value.valueBoolean != null) return value.valueBoolean! ? 'true' : 'false';
    if (value.valueDate.isNotEmpty) return value.valueDate;
    if (value.valueNumber.isNotEmpty) return value.valueNumber;
    return value.valueText;
  }

  Future<void> start() async {
    if (loading || loaded) return;
    loading = true;
    error = null;
    notifyListeners();
    try {
      final ApplicableAttributesRecord answer = await load();
      definitions = answer.definitions;
      mandatoryIds = answer.mandatoryIds.toSet();
      for (final AttributeDefinitionRecord definition in definitions) {
        controllers.putIfAbsent(
          definition.id,
          () => AttributeFieldController(
            definition,
            initialValue: _stored[definition.id],
          ),
        );
      }
      loaded = true;
    } on ApiException catch (exception) {
      error = exception.message;
      loaded = false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  /// Whether the form has something to send. False until the definitions
  /// arrived, so a save cannot clear values it never saw.
  bool get canSend => loaded;

  /// The `attributes` list for the payload: every filled field.
  List<Json> payload() => [
        for (final AttributeDefinitionRecord definition in definitions)
          if (!(controllers[definition.id]?.isEmpty ?? true))
            {
              'attribute_definition_id': definition.id,
              'value': controllers[definition.id]!.payloadValue,
            },
      ];

  /// The first validation message across the fields, or null.
  String? validate() {
    for (final AttributeDefinitionRecord definition in definitions) {
      final AttributeFieldController? controller = controllers[definition.id];
      if (controller == null) continue;
      if (mandatoryIds.contains(definition.id) && controller.isEmpty) {
        return '${definition.name} is required.';
      }
      final String? message = controller.validate();
      if (message != null) return '${definition.name}: $message';
    }
    return null;
  }

  @override
  void dispose() {
    for (final AttributeFieldController controller in controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }
}

/// The section a form places on its Custom fields tab.
class CustomFieldsSection extends StatelessWidget {
  const CustomFieldsSection({
    super.key,
    required this.controller,
    required this.noun,
    this.readOnly = false,
    this.onChanged,
  });

  final CustomFieldsController controller;

  /// What the record is called in the empty message: "customers".
  final String noun;
  final bool readOnly;
  final VoidCallback? onChanged;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          final ThemeData theme = Theme.of(context);
          if (controller.loading) {
            return const Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          if (controller.error != null) {
            return Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      'Could not read the custom fields: ${controller.error}. '
                      'Saving will leave the stored values as they are.',
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    ),
                  ),
                  TextButton(
                    onPressed: controller.start,
                    child: const Text('Retry'),
                  ),
                ],
              ),
            );
          }
          if (controller.definitions.isEmpty) {
            return Padding(
              padding: const EdgeInsets.all(8),
              child: Text(
                'No custom fields are defined for $noun in this firm. An '
                'administrator adds them under Configuration → Business '
                'Profiles → Dynamic Attributes.',
                style: theme.textTheme.bodySmall,
              ),
            );
          }
          return Wrap(
            spacing: 16,
            runSpacing: 12,
            children: [
              for (final AttributeDefinitionRecord definition
                  in controller.definitions)
                AttributeFormField(
                  controller: controller.controllers[definition.id]!,
                  required: controller.mandatoryIds.contains(definition.id),
                  readOnly: readOnly,
                  onChanged: onChanged,
                ),
            ],
          );
        },
      );
}

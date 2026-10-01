import 'entities.dart';

/// The firm's messaging switch and reminder schedule (backlog 51).
class MessagingSettings {
  const MessagingSettings({
    required this.isEnabled,
    required this.dueSoonDays,
    required this.overdueEveryDays,
    required this.isConfigured,
    required this.canStoreCredentials,
  });

  /// The master switch: false means nothing is sent from this firm.
  final bool isEnabled;

  /// How many days before the due date a "payment due soon" goes (0-60).
  final int dueSoonDays;

  /// An overdue reminder repeats every this many days (1-90).
  final int overdueEveryDays;
  final bool isConfigured;

  /// False when the server operator has not set `AGENCY_MESSAGING_KEY`, so
  /// no account can be saved.
  final bool canStoreCredentials;

  factory MessagingSettings.fromJson(Json json) => MessagingSettings(
        isEnabled: boolValue(json['is_enabled']),
        dueSoonDays: (json['due_soon_days'] as num?)?.toInt() ?? 3,
        overdueEveryDays: (json['overdue_every_days'] as num?)?.toInt() ?? 7,
        isConfigured: boolValue(json['is_configured']),
        canStoreCredentials: boolValue(json['can_store_credentials']),
      );

  Json toJson() => <String, dynamic>{
        'is_enabled': isEnabled,
        'due_soon_days': dueSoonDays,
        'overdue_every_days': overdueEveryDays,
      };
}

/// One input of a provider's account form.
class ProviderField {
  const ProviderField({
    required this.name,
    required this.label,
    required this.secret,
    required this.required,
    required this.kind,
    this.help,
    this.choices = const [],
    this.defaultValue,
  });

  final String name;
  final String label;

  /// A secret is never read back: the form says it is saved instead.
  final bool secret;
  final bool required;

  /// text, number, password, email or choice.
  final String kind;
  final String? help;
  final List<String> choices;
  final String? defaultValue;

  factory ProviderField.fromJson(Json json) => ProviderField(
        name: stringValue(json['name']),
        label: stringValue(json['label']),
        secret: boolValue(json['secret']),
        required: boolValue(json['required']),
        kind: stringValue(json['kind']).isEmpty
            ? 'text'
            : stringValue(json['kind']),
        help: json['help'] as String?,
        choices: stringList(json['choices']),
        defaultValue: json['default'] as String?,
      );
}

/// A service that can carry one channel, and the account details it needs.
class MessagingProvider {
  const MessagingProvider({
    required this.provider,
    required this.channel,
    required this.label,
    required this.supportsStatus,
    required this.fields,
  });

  final String provider;
  final String channel;
  final String label;
  final bool supportsStatus;
  final List<ProviderField> fields;

  factory MessagingProvider.fromJson(Json json) => MessagingProvider(
        provider: stringValue(json['provider']),
        channel: stringValue(json['channel']),
        label: stringValue(json['label']),
        supportsStatus: boolValue(json['supports_status']),
        fields: _objects(json['fields']).map(ProviderField.fromJson).toList(),
      );
}

/// A thing that happens to a document and may send a message.
class MessagingEvent {
  const MessagingEvent({
    required this.code,
    required this.label,
    required this.documentType,
    required this.variables,
    required this.isReminder,
    required this.attachesPdf,
    required this.defaultSubject,
    required this.defaultBody,
  });

  final String code;
  final String label;
  final String documentType;

  /// The values a template may use, in the order a WhatsApp or SMS template
  /// numbers them: `{{1}}` is the first.
  final List<String> variables;
  final bool isReminder;
  final bool attachesPdf;
  final String defaultSubject;
  final String defaultBody;

  factory MessagingEvent.fromJson(Json json) => MessagingEvent(
        code: stringValue(json['code']),
        label: stringValue(json['label']),
        documentType: stringValue(json['document_type']),
        variables: stringList(json['variables']),
        isReminder: boolValue(json['is_reminder']),
        attachesPdf: boolValue(json['attaches_pdf']),
        defaultSubject: stringValue(json['default_subject']),
        defaultBody: stringValue(json['default_body']),
      );
}

/// One of the three channels: EMAIL, WHATSAPP or SMS.
class MessagingChannel {
  const MessagingChannel({
    required this.channel,
    required this.provider,
    required this.isEnabled,
    required this.health,
    required this.isConfigured,
    required this.settings,
    required this.secretsSet,
    required this.lastTestedAt,
    required this.lastError,
  });

  final String channel;
  final String? provider;
  final bool isEnabled;

  /// NOT_CONFIGURED, UNTESTED, OK or NEEDS_ATTENTION.
  final String health;
  final bool isConfigured;

  /// The public fields as saved; secrets are never in here.
  final Map<String, String> settings;

  /// Names of the secret fields that already hold a value.
  final List<String> secretsSet;
  final String? lastTestedAt;
  final String? lastError;

  factory MessagingChannel.fromJson(Json json) {
    final Object? raw = json['settings'];
    return MessagingChannel(
      channel: stringValue(json['channel']),
      provider: json['provider'] as String?,
      isEnabled: boolValue(json['is_enabled']),
      health: stringValue(json['health']),
      isConfigured: boolValue(json['is_configured']),
      settings: raw is Map
          ? {
              for (final MapEntry<dynamic, dynamic> entry in raw.entries)
                stringValue(entry.key): stringValue(entry.value),
            }
          : const <String, String>{},
      secretsSet: stringList(json['secrets_set']),
      lastTestedAt: json['last_tested_at'] as String?,
      lastError: json['last_error'] as String?,
    );
  }
}

/// A channel as the server left it, with what the server said about it.
class ChannelOutcome {
  const ChannelOutcome({required this.channel, required this.message});

  final MessagingChannel channel;
  final String message;

  factory ChannelOutcome.fromEnvelope(Json envelope) {
    final Object? data = envelope['data'];
    return ChannelOutcome(
      channel: MessagingChannel.fromJson(
        data is Map ? Map<String, dynamic>.from(data) : envelope,
      ),
      message: stringValue(envelope['message']),
    );
  }
}

/// One channel of an event, in fallback order.
class EventChannelRule {
  const EventChannelRule({
    required this.channel,
    required this.isEnabled,
    this.templateName,
    this.templateLanguage,
    this.subject,
    this.body,
  });

  final String channel;
  final bool isEnabled;
  final String? templateName;
  final String? templateLanguage;
  final String? subject;
  final String? body;

  factory EventChannelRule.fromJson(Json json) => EventChannelRule(
        channel: stringValue(json['channel']),
        isEnabled: boolValue(json['is_enabled']),
        templateName: json['template_name'] as String?,
        templateLanguage: json['template_language'] as String?,
        subject: json['subject'] as String?,
        body: json['body'] as String?,
      );

  Json toJson() => <String, dynamic>{
        'channel': channel,
        'is_enabled': isEnabled,
        'template_name': templateName,
        'template_language': templateLanguage,
        'subject': subject,
        'body': body,
      };
}

/// What the firm has chosen for one event.
class EventConfig {
  const EventConfig({
    required this.eventCode,
    required this.label,
    required this.isEnabled,
    required this.channels,
  });

  final String eventCode;
  final String label;
  final bool isEnabled;
  final List<EventChannelRule> channels;

  factory EventConfig.fromJson(Json json) => EventConfig(
        eventCode: stringValue(json['event_code']),
        label: stringValue(json['label']),
        isEnabled: boolValue(json['is_enabled']),
        channels:
            _objects(json['channels']).map(EventChannelRule.fromJson).toList(),
      );
}

/// A row of the message log.
class MessageLogEntry {
  const MessageLogEntry({
    required this.id,
    required this.eventCode,
    required this.documentNumber,
    required this.channel,
    required this.recipient,
    required this.status,
    required this.reason,
    required this.attempts,
    required this.createdAt,
  });

  final String id;
  final String eventCode;
  final String? documentNumber;
  final String channel;
  final String? recipient;

  /// QUEUED, SENDING, SENT, DELIVERED, READ, FAILED or SKIPPED.
  final String status;
  final String? reason;
  final int attempts;
  final String createdAt;

  factory MessageLogEntry.fromJson(Json json) => MessageLogEntry(
        id: stringValue(json['id']),
        eventCode: stringValue(json['event_code']),
        documentNumber: json['document_number'] as String?,
        channel: stringValue(json['channel']),
        recipient: json['recipient'] as String?,
        status: stringValue(json['status']),
        reason: json['reason'] as String?,
        attempts: (json['attempts'] as num?)?.toInt() ?? 0,
        createdAt: stringValue(json['created_at']),
      );
}

List<Json> _objects(dynamic value) => value is List
    ? value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList()
    : const [];

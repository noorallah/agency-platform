import 'entities.dart';

class CustomerAddress {
  const CustomerAddress({
    required this.id,
    required this.addressType,
    required this.addressLine1,
    required this.addressLine2,
    required this.area,
    required this.city,
    required this.district,
    required this.state,
    required this.country,
    required this.postalCode,
    required this.isDefaultBilling,
    required this.isDefaultShipping,
  });

  final String id;
  final String addressType;
  final String addressLine1;
  final String addressLine2;
  final String area;
  final String city;
  final String district;
  final String state;
  final String country;
  final String postalCode;
  final bool isDefaultBilling;
  final bool isDefaultShipping;

  factory CustomerAddress.fromJson(Json json) => CustomerAddress(
        id: stringValue(json['id']),
        addressType: stringValue(json['address_type']),
        addressLine1: stringValue(json['address_line1']),
        addressLine2: stringValue(json['address_line2']),
        area: stringValue(json['area']),
        city: stringValue(json['city']),
        district: stringValue(json['district']),
        state: stringValue(json['state']),
        country: stringValue(json['country']),
        postalCode: stringValue(json['postal_code']),
        isDefaultBilling: boolValue(json['is_default_billing']),
        isDefaultShipping: boolValue(json['is_default_shipping']),
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'address_type': addressType,
        'address_line1': addressLine1,
        'address_line2': addressLine2,
        'area': area,
        'city': city,
        'district': district,
        'state': state,
        'country': country,
        'postal_code': postalCode,
        'is_default_billing': isDefaultBilling,
        'is_default_shipping': isDefaultShipping,
      };
}

class CustomerContact {
  const CustomerContact({
    required this.id,
    required this.name,
    required this.designation,
    required this.mobile,
    required this.email,
    required this.department,
    required this.isPrimary,
  });

  final String id;
  final String name;
  final String designation;
  final String mobile;
  final String email;
  final String department;
  final bool isPrimary;

  factory CustomerContact.fromJson(Json json) => CustomerContact(
        id: stringValue(json['id']),
        name: stringValue(json['name']),
        designation: stringValue(json['designation']),
        mobile: stringValue(json['mobile']),
        email: stringValue(json['email']),
        department: stringValue(json['department']),
        isPrimary: boolValue(json['is_primary']),
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'name': name,
        'designation': designation,
        'mobile': mobile,
        'email': email,
        'department': department,
        'is_primary': isPrimary,
      };
}

class Customer {
  const Customer({
    required this.id,
    this.version = 0,
    required this.firmId,
    required this.code,
    required this.customerType,
    required this.name,
    required this.displayName,
    required this.gstNumber,
    required this.panNumber,
    required this.email,
    required this.phone,
    required this.alternatePhone,
    required this.website,
    required this.creditLimit,
    required this.openingBalance,
    required this.paymentTermsDays,
    required this.currencyCode,
    required this.currentOutstanding,
    required this.unappliedAdvanceBalance,
    required this.status,
    required this.notes,
    required this.createdBy,
    required this.createdAt,
    required this.updatedBy,
    required this.updatedAt,
    required this.isDeleted,
    required this.addresses,
    required this.contacts,
  });

  final String id;

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server did not supply one, and the
  /// save then carries no precondition — old behaviour, not a guarantee.
  final int version;
  final String firmId;
  final String code;
  final String customerType;
  final String name;
  final String displayName;
  final String gstNumber;
  final String panNumber;
  final String email;
  final String phone;
  final String alternatePhone;
  final String website;
  final String creditLimit;
  final String openingBalance;
  final int paymentTermsDays;
  final String currencyCode;
  final String currentOutstanding;
  final String unappliedAdvanceBalance;
  final String status;
  final String notes;
  final String createdBy;
  final String createdAt;
  final String updatedBy;
  final String updatedAt;
  final bool isDeleted;
  final List<CustomerAddress> addresses;
  final List<CustomerContact> contacts;

  String get city {
    final Iterable<CustomerAddress> defaults =
        addresses.where((address) => address.isDefaultBilling);
    if (defaults.isNotEmpty) return defaults.first.city;
    return addresses.isEmpty ? '' : addresses.first.city;
  }

  factory Customer.fromJson(Json json) => Customer(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        firmId: stringValue(json['firm_id']),
        code: stringValue(json['code']),
        customerType: stringValue(json['customer_type']),
        name: stringValue(json['name']),
        displayName: stringValue(json['display_name']),
        gstNumber: stringValue(json['gst_number']),
        panNumber: stringValue(json['pan_number']),
        email: stringValue(json['email']),
        phone: stringValue(json['phone']),
        alternatePhone: stringValue(json['alternate_phone']),
        website: stringValue(json['website']),
        creditLimit: stringValue(json['credit_limit']).isEmpty
            ? '0.00'
            : stringValue(json['credit_limit']),
        openingBalance: stringValue(json['opening_balance']).isEmpty
            ? '0.00'
            : stringValue(json['opening_balance']),
        paymentTermsDays: (json['payment_terms_days'] as num?)?.toInt() ?? 0,
        currencyCode: stringValue(json['currency_code']),
        currentOutstanding: stringValue(json['current_outstanding']).isEmpty
            ? '0.00'
            : stringValue(json['current_outstanding']),
        unappliedAdvanceBalance:
            stringValue(json['unapplied_advance_balance']).isEmpty
                ? '0.00'
                : stringValue(json['unapplied_advance_balance']),
        status: stringValue(json['status']),
        notes: stringValue(json['notes']),
        createdBy: stringValue(json['created_by']),
        createdAt: stringValue(json['created_at']),
        updatedBy: stringValue(json['updated_by']),
        updatedAt: stringValue(json['updated_at']),
        isDeleted: boolValue(json['is_deleted']),
        addresses:
            _objects(json['addresses']).map(CustomerAddress.fromJson).toList(),
        contacts:
            _objects(json['contacts']).map(CustomerContact.fromJson).toList(),
      );
}

List<Json> _objects(dynamic value) => value is List
    ? value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList()
    : const [];

class CustomerQuery {
  const CustomerQuery({
    this.status,
    this.customerType,
    this.city,
    this.state,
    this.createdFrom,
    this.createdTo,
    this.includeDeleted = false,
  });

  final String? status;
  final String? customerType;
  final String? city;
  final String? state;
  final String? createdFrom;
  final String? createdTo;
  final bool includeDeleted;

  Map<String, String> toQuery() => {
        if (status?.isNotEmpty == true) 'status': status!,
        if (customerType?.isNotEmpty == true) 'customer_type': customerType!,
        if (city?.isNotEmpty == true) 'city': city!,
        if (state?.isNotEmpty == true) 'state': state!,
        if (createdFrom?.isNotEmpty == true) 'created_from': createdFrom!,
        if (createdTo?.isNotEmpty == true) 'created_to': createdTo!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}

class CustomerReceivableSummary {
  const CustomerReceivableSummary({
    required this.customerId,
    required this.customerName,
    required this.outstanding,
    required this.unappliedAdvance,
    required this.netPosition,
  });

  final String customerId;
  final String customerName;
  final String outstanding;
  final String unappliedAdvance;
  final String netPosition;

  factory CustomerReceivableSummary.fromJson(Json json) =>
      CustomerReceivableSummary(
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        outstanding: stringValue(json['outstanding']).isEmpty
            ? '0.00'
            : stringValue(json['outstanding']),
        unappliedAdvance: stringValue(json['unapplied_advance']).isEmpty
            ? '0.00'
            : stringValue(json['unapplied_advance']),
        netPosition: stringValue(json['net_position']).isEmpty
            ? '0.00'
            : stringValue(json['net_position']),
      );
}

class CustomerReceivableTransaction {
  const CustomerReceivableTransaction({
    required this.id,
    required this.customerId,
    required this.firmId,
    required this.transactionType,
    required this.transactionDate,
    required this.amount,
    required this.outstandingDelta,
    required this.advanceDelta,
    required this.outstandingAfter,
    required this.advanceAfter,
    required this.referenceType,
    required this.referenceId,
    required this.referenceNumber,
    required this.remarks,
    required this.createdAt,
  });

  final String id;
  final String customerId;
  final String firmId;
  final String transactionType;
  final String transactionDate;
  final String amount;
  final String outstandingDelta;
  final String advanceDelta;
  final String outstandingAfter;
  final String advanceAfter;
  final String referenceType;
  final String referenceId;
  final String referenceNumber;
  final String remarks;
  final String createdAt;

  factory CustomerReceivableTransaction.fromJson(Json json) =>
      CustomerReceivableTransaction(
        id: stringValue(json['id']),
        customerId: stringValue(json['customer_id']),
        firmId: stringValue(json['firm_id']),
        transactionType: stringValue(json['transaction_type']),
        transactionDate: stringValue(json['transaction_date']),
        amount: stringValue(json['amount']),
        outstandingDelta: stringValue(json['outstanding_delta']),
        advanceDelta: stringValue(json['advance_delta']),
        outstandingAfter: stringValue(json['outstanding_after']),
        advanceAfter: stringValue(json['advance_after']),
        referenceType: stringValue(json['reference_type']),
        referenceId: stringValue(json['reference_id']),
        referenceNumber: stringValue(json['reference_number']),
        remarks: stringValue(json['remarks']),
        createdAt: stringValue(json['created_at']),
      );
}

/// Where one customer stands against their credit limit.
///
/// The thresholds travel with the verdict so a form can explain a warning
/// without a second call for the firm's policy.
class CustomerCreditStatus {
  const CustomerCreditStatus({
    required this.customerId,
    required this.customerName,
    required this.enforcement,
    required this.status,
    required this.limit,
    required this.exposure,
    required this.available,
    required this.usedPercent,
    required this.warnAtPercent,
    required this.blockAtPercent,
    required this.wouldBlock,
    required this.message,
  });

  final String customerId;
  final String customerName;
  final String enforcement;
  final String status;
  final String limit;
  final String exposure;
  final String available;
  final String usedPercent;
  final String warnAtPercent;
  final String blockAtPercent;
  final bool wouldBlock;
  final String message;

  bool get isWarning => status == 'WARNING';

  bool get isBreach => status == 'BREACH';

  /// Whether there is anything worth showing the user at all.
  bool get hasNotice => message.isNotEmpty && status != 'OK';

  factory CustomerCreditStatus.fromJson(Json json) => CustomerCreditStatus(
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        enforcement: stringValue(json['enforcement']),
        status: stringValue(json['status']),
        limit: stringValue(json['limit']),
        exposure: stringValue(json['exposure']),
        available: stringValue(json['available']),
        usedPercent: stringValue(json['used_percent']),
        warnAtPercent: stringValue(json['warn_at_percent']),
        blockAtPercent: stringValue(json['block_at_percent']),
        wouldBlock: boolValue(json['would_block']),
        message: stringValue(json['message']),
      );
}

/// The firm's credit policy.
class CreditControlSettings {
  const CreditControlSettings({
    required this.enforcement,
    required this.warnAtPercent,
    required this.blockAtPercent,
    required this.isConfigured,
  });

  final String enforcement;
  final String warnAtPercent;
  final String blockAtPercent;

  /// False while the firm is still on the platform default.
  final bool isConfigured;

  factory CreditControlSettings.fromJson(Json json) => CreditControlSettings(
        enforcement: stringValue(json['enforcement']),
        warnAtPercent: stringValue(json['warn_at_percent']),
        blockAtPercent: stringValue(json['block_at_percent']),
        isConfigured: boolValue(json['is_configured']),
      );

  Json toJson() => <String, dynamic>{
        'enforcement': enforcement,
        'warn_at_percent': warnAtPercent,
        'block_at_percent': blockAtPercent,
      };
}

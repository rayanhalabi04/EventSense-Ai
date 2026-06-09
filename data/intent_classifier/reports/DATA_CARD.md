# EventSense AI Intent Dataset Data Card

## Purpose
This dataset trains an intent classifier for WhatsApp-style messages received by wedding planners and event agencies.

## Labels
booking_inquiry, pricing_request, availability_question, service_question, urgent_change, guest_count_change, complaint, cancellation_request, payment_issue, human_escalation, other

## Cleaning and preprocessing
The dataset was cleaned by normalizing text, removing empty or duplicate rows, standardizing label names, mapping source labels into the final EventSense label set, and removing unusable or unclear examples. After cleaning, the final dataset was split into train, validation, test, and golden evaluation sets.

## Dataset construction
The dataset combines:
1. EventSense-specific event/wedding labeled examples created in this notebook.
2. Public customer-support intent data for support, cancellation, payment, complaint, and human escalation patterns.
3. Public complaint/payment data for complaint and payment issue language.
4. Public spam/out-of-scope data for the `other` class.
5. Weak domain-transfer data from travel/booking/service datasets where useful.

## Columns
- text: the client/customer message.
- label: the final EventSense intent label.
- source: the dataset or generation source, when available.

## Important limitation
Public datasets do not fully represent real wedding WhatsApp conversations. The event-specific examples cover missing labels such as `guest_count_change`, `urgent_change`, `availability_question`, and `booking_inquiry`. For a stronger final project, replace or expand these examples with real manually labeled messages.

## Final dataset size
Full rows: 6579
Train rows: 5263
Validation rows: 658
Test rows: 658
Golden rows: 70

## Distribution
```json
{
  "booking_inquiry": 522,
  "pricing_request": 608,
  "availability_question": 413,
  "service_question": 800,
  "urgent_change": 423,
  "guest_count_change": 165,
  "complaint": 691,
  "cancellation_request": 677,
  "payment_issue": 800,
  "human_escalation": 680,
  "other": 800
}
```

## Recommended use
Use `train.csv` for fitting only, `validation.csv` for model selection/tuning, and `test.csv` only once for final evaluation. Use `eventsense_golden_test_set.csv` as an extra realistic EventSense check and do not train on it.

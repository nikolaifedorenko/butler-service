"""Реестр кодов Reason (6.2) и каноническое перечисление значений `step` (v7.1/F-05)."""

OPENING_ROUNDED = "OPENING_ROUNDED"
PLAN_EQUALS_FACT = "PLAN_EQUALS_FACT"
UNPAID_CREDITED = "UNPAID_CREDITED"
CODE_PLACED = "CODE_PLACED"
NO_RECEIVER = "NO_RECEIVER"               # единственный код в `exceptions`
BANK_APPLIED = "BANK_APPLIED"
CODE_CUT = "CODE_CUT"
RESIDUAL_CARRIED = "RESIDUAL_CARRIED"

ALL = (OPENING_ROUNDED, PLAN_EQUALS_FACT, UNPAID_CREDITED, CODE_PLACED, NO_RECEIVER,
       BANK_APPLIED, CODE_CUT, RESIDUAL_CARRIED)

# значения Reason.step — каноническое перечисление (6.2, v7.1); иные не допускаются
STEP_OPENING = "opening"
STEP_CARDS = "cards"
STEP_CREDIT_UNPAID = "credit_unpaid"
STEP_PLACEMENT = "placement"
STEP_REPLACEMENT = "replacement"
STEP_DEFERRED = "deferred"
STEP_BANK = "bank"
STEP_CASCADE = "cascade"
STEP_CLOSING = "closing"

ALL_STEPS = (STEP_OPENING, STEP_CARDS, STEP_CREDIT_UNPAID, STEP_PLACEMENT, STEP_REPLACEMENT,
             STEP_DEFERRED, STEP_BANK, STEP_CASCADE, STEP_CLOSING)

# перечисления значений data (6.2)
OPENING_KIND_BANK = "bank"                    # OPENING_ROUNDED.kind
OPENING_KIND_DEFERRED_BLOCK = "deferred_block"
POLICY_YES = "yes"                            # PLAN_EQUALS_FACT.policy
POLICY_AUTO_CODE = "auto_code"
PASS_PRIMARY = "primary"                      # CODE_PLACED.pass
PASS_AFTER_CASCADE = "after_cascade"

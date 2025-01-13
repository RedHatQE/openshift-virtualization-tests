HYPERV_FEATURES_LABELS_DOM_XML = [
    "relaxed",
    "vapic",
    "spinlocks",
    "vpindex",
    "synic",
    "stimer",  # synictimer in VM yaml
    "frequencies",
    "ipi",
    "reset",
    "runtime",
    "tlbflush",
    "reenlightenment",
]

HYPERV_FEATURES_LABELS_VM_YAML = HYPERV_FEATURES_LABELS_DOM_XML.copy()
HYPERV_FEATURES_LABELS_VM_YAML[HYPERV_FEATURES_LABELS_VM_YAML.index("stimer")] = "synictimer"

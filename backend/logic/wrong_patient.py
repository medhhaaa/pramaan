"""Wrong-patient detection: a document whose blood group or sex conflicts with the
patient's other records is held back until a reviewer confirms. (Core backend, P2)"""


def is_wrong_patient(document_facts, patient):
    raise NotImplementedError

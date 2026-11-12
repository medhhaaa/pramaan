"""The full pipeline for one uploaded document. (Ashil)

process_document(pdf_path, patient_id, document_id) -> list of verified facts
    read_pdf -> deidentify -> extract_facts -> reidentify -> verify_facts
The backend upload route calls this function and stores the result.
"""


def process_document(pdf_path, patient_id, document_id):
    raise NotImplementedError

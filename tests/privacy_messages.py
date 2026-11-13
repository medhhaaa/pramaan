"""10 messy free-text messages for the privacy layer (tests/test_privacy_layer.py and the demo:
python -m tests.privacy_messages). All names, numbers and IDs are made up.
Each case: (message, must be removed, must stay)."""

IDENTITY = {"name": "Sunita Rao", "dob": "1952-06-14", "phone": "+91 98765 43210",
            "address": "14, Shanthi Nilaya, Bejai, Mangaluru - 575004"}

CASES = [
    ("namaskara doctor, nanna amma Sunita Rao ge sugar 250 ide, Metformin 500 tegondidare. call madi 98765 43210",
     ["Sunita Rao", "98765 43210"], ["Metformin", "sugar 250"]),
    ("My son Rohan has fever since 3 days, gave Dolo 650. Our number is 98450-12345.",
     ["Rohan", "98450-12345"], ["Dolo 650", "fever"]),
    ("S. Rao, DOB 14/06/1952, UHID KHC-004512 - BP 150/90, taking Amlodipine 5mg OD",
     ["S. Rao", "14/06/1952", "KHC-004512"], ["Amlodipine 5mg OD", "150/90"]),
    ("nanna maga kiran ge asthma, Asthalin inhaler use madtidane. Aadhaar 4987 6543 2102",
     ["kiran", "4987 6543 2102"], ["asthma", "Asthalin"]),
    ("Dr. Anand Shetty from Karavali Clinic, Kadri Road said Parkinson's is ruled out, start Telma 40",
     ["Anand Shetty", "Karavali Clinic"], ["Parkinson's", "Telma 40"]),
    ("Mrs. Lakshmi Hegde W/o Ganesh Hegde, Udupi PIN 576101, email lakshmi.hegde@gmail.com",
     ["Lakshmi Hegde", "Ganesh Hegde", "576101", "lakshmi.hegde@gmail.com"], []),
    ("ನನ್ನ ಮಗಳು ಅನನ್ಯ ಗೆ ಜ್ವರ, Crocin kottidini. ph 9 8 7 6 5 0 1 2 3 4",
     ["ಅನನ್ಯ", "9 8 7 6 5 0 1 2 3 4"], ["Crocin", "ಜ್ವರ"]),
    ("Suneeta rao has Alzheimer's history in family, her father Venkatesh had it. PAN ABCDE1234F",
     ["Suneeta", "Venkatesh", "ABCDE1234F"], ["Alzheimer's"]),
    ("pls check reports of my husband ramesh, mob +91-99001-23456, he takes Glycomet GP1 and Ecosprin 75, ABHA 91-2345-6789-0123",
     ["ramesh", "+91-99001-23456", "91-2345-6789-0123"], ["Glycomet", "Ecosprin 75"]),
    ("Patient: Fathima Begum, 62 yrs, Bejai. c/o chest pain since morning, h/o MI 2015, on Atorvastatin 20mg. Contact son Imran 080-23456789",
     ["Fathima Begum", "Imran", "080-23456789"], ["chest pain", "MI 2015", "Atorvastatin 20mg", "62 yrs"]),
]

if __name__ == "__main__":
    from pipeline.privacy_layer import PrivacyBlocked, preview, protect

    for n, (msg, _gone, _kept) in enumerate(CASES, start=1):
        p = preview(msg, IDENTITY)
        print(f"\n#{n} {msg}")
        print(f"   SENT: {p['redacted']}")
        for layer in sorted(p["by_layer"]):
            print(f"   {layer:17}: " + ", ".join(f"{x['text']} ({x['kind']})" for x in p["by_layer"][layer]))
        try:
            protect(msg, IDENTITY)
            print("   fail-closed check: OK, AI may be called")
        except PrivacyBlocked as e:
            print(f"   fail-closed check: BLOCKED -> {[f.text for f in e.findings]}")

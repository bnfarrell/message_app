"""Static content for the seed. Names, message templates, quick replies, assets, categories."""

FIRST_NAMES = ["Sarah", "Diego", "Nia", "Priya", "Tom", "Lena", "Omar", "Grace", "Hiro", "Amara", "Luca", "Maya",
               "Jonas", "Zara", "Felix", "Ines", "Kwame", "Elena", "Rafael", "Yuki", "Noor", "Mateo", "Ivy", "Tariq",
               "Chloe", "Dmitri", "Aisha", "Ben", "Sofia", "Arjun"]
LAST_NAMES = ["Chen", "Ruiz", "Okafor", "Nair", "Becker", "Park", "Haddad", "Mensah", "Tanaka", "Silva", "Rossi",
              "Novak", "Dubois", "Khan", "Andersen", "Moreno", "Boateng", "Petrova", "Costa", "Sato", "Rahman",
              "Alvarez", "Walsh", "Hassan", "Martin", "Volkov", "Diallo", "Cohen", "Ferreira", "Iyer"]
ROOM_TYPES = ["King", "Queen", "Double Queen", "Suite", "Accessible King"]
RATE_CODES = ["BAR", "AAA", "CORP", "PKG", "GOV"]
LOYALTY = [None, None, None, "Silver", "Silver", "Gold", "Gold", "Platinum"]

# (guest message, department type for a linked work order or None, negative sentiment?)
GUEST_OPENERS = [
    ("Hi, the AC in our room isn't working at all, it's really warm in here.", "engineering", True),
    ("Can we get a late checkout tomorrow? Flight isn't until 4.", "front_desk", False),
    ("Extra towels please, and is the pool open late?", "housekeeping", False),
    ("What time does breakfast start?", None, False),
    ("The shower drain is really slow and water is pooling.", "engineering", True),
    ("Is there parking on site and how much is it?", None, False),
    ("Room hasn't been serviced today and it's 4pm.", "housekeeping", True),
    ("Could someone bring up two more pillows?", "housekeeping", False),
    ("TV remote isn't pairing with the TV in 509.", "engineering", False),
    ("Hi! Just checked in. Where's the gym?", None, False),
    ("There's a strange noise from the ceiling vent.", "engineering", True),
    ("Can I get a wake-up call at 5:30am?", "front_desk", False),
    ("Arriving around 9pm tonight, is that ok?", None, False),
    ("The wifi keeps dropping in our room.", "engineering", False),
    ("Do you have a shuttle to the airport?", None, False),
    ("Our toilet is running constantly.", "engineering", True),
    ("Is the restaurant open for dinner tonight?", None, False),
    ("Could we have the room made up while we're at lunch?", "housekeeping", False),
    ("Bill shows a minibar charge we didn't use.", "front_desk", True),
    ("Love the view! Thank you for the upgrade.", None, False),
]
STAFF_REPLIES = [
    "So sorry about that — I'm sending someone up now, they'll knock within 15 minutes.",
    "Absolutely, I've noted that for you. Anything else you need?",
    "On its way! Housekeeping will be up shortly.",
    "Breakfast is 6:30–10:30 in the Harbour Room on level 2.",
    "Self-parking is $28/night in the garage on Front St; valet is $45.",
    "Done — your checkout is extended to 2 PM at no charge.",
    "The pool and hot tub are open 7 AM–10 PM.",
    "Thank you, Sarah — we're so glad you're enjoying it!",
]
NOTES = ["Gold member, 4th stay — offer 518 if not fixed by 7:30.", "Prefers high floor, away from elevator.",
         "Feather allergy — hypoallergenic pillows pre-set.", "Travelling with infant; crib delivered.",
         "Complained last stay about noise — proactive check-in done."]

WORK_ORDERS = [
    ("AC not cooling", "maintenance", "urgent", "engineering"), ("Toilet running constantly", "maintenance", "normal", "engineering"),
    ("Bathroom faucet dripping", "maintenance", "normal", "engineering"), ("Hallway light out near 512", "maintenance", "low", "engineering"),
    ("TV remote not pairing", "maintenance", "low", "engineering"), ("Ice machine 3F not dispensing", "maintenance", "normal", "engineering"),
    ("Pool pump pressure low", "maintenance", "high", "engineering"), ("Elevator B intermittent door fault", "maintenance", "urgent", "engineering"),
    ("Door closer slams", "maintenance", "low", "engineering"), ("Extra towels + pillows", "guest_request", "normal", "housekeeping"),
    ("Deep clean after checkout — mattress rotation", "housekeeping", "normal", "housekeeping"),
    ("Carpet stain, coffee", "housekeeping", "normal", "housekeeping"), ("Room not serviced by 4pm", "housekeeping", "high", "housekeeping"),
    ("Late checkout request — 2 PM", "guest_request", "normal", "front_desk"), ("Wake-up call 5:30am", "guest_request", "low", "front_desk"),
    ("Shower drain slow", "maintenance", "normal", "engineering"), ("Bedside lamp bulb", "maintenance", "low", "engineering"),
]

QUICK_REPLIES = [
    ("/wifi", "WiFi details", "Hi {{guest_first_name}} — the network is Harbourview-Guest, no password needed. If it drops, toggle WiFi off and on.", None),
    ("/checkout", "Checkout time", "Checkout is 11 AM. Reply LATE if you'd like to request a later time and we'll do our best.", "front_desk"),
    ("/late", "Late checkout granted", "Done — {{guest_first_name}}, your checkout is extended to 2 PM at no charge.", "front_desk"),
    ("/towels", "Towels on the way", "Fresh towels are on their way to {{room_number}} — about 15 minutes.", "housekeeping"),
    ("/eng", "Engineering dispatched", "So sorry about that. Engineering is on the way to {{room_number}} and will knock within 15 minutes.", None),
    ("/parking", "Parking", "Self-parking is $28/night in the garage on Front St; valet is $45 with in-and-out privileges.", "front_desk"),
    ("/breakfast", "Breakfast hours", "Breakfast is 6:30–10:30 in the Harbour Room, level 2.", None),
    ("/pool", "Pool hours", "The pool and hot tub are open 7 AM–10 PM. Towels are poolside.", None),
    ("/gym", "Fitness centre", "The fitness centre is on level 3, open 24 hours with your room key.", None),
    ("/shuttle", "Airport shuttle", "The shuttle runs on the hour from 5 AM to 11 PM from the Front St entrance.", "front_desk"),
    ("/sorry", "Apology", "I'm so sorry, {{guest_first_name}}. That's not the experience we want for you — let me fix it.", None),
    ("/thanks", "Thanks", "Thank you, {{guest_first_name}} — it's a pleasure having you at {{property_name}}.", None),
    ("/housekeeping", "Housekeeping timing", "Housekeeping services rooms between 9 AM and 3 PM. Want us to come at a specific time?", "housekeeping"),
    ("/bill", "Folio question", "Happy to check your folio — I'll review it and text you back within 10 minutes.", "front_desk"),
    ("/restaurant", "Restaurant hours", "The Quay is open for dinner 5:30–10 PM; the bar until midnight.", None),
]

ASSETS = [
    ("WiFi card", "link", "https://example.test/harbourview/wifi.pdf", "Connectivity"),
    ("Property map", "map", "https://example.test/harbourview/map.pdf", "Wayfinding"),
    ("Breakfast menu", "menu", "https://example.test/harbourview/breakfast.pdf", "Dining"),
    ("Dinner menu — The Quay", "menu", "https://example.test/harbourview/quay.pdf", "Dining"),
    ("Spa menu", "menu", "https://example.test/harbourview/spa.pdf", "Wellness"),
    ("Local guide", "link", "https://example.test/harbourview/local.pdf", "Explore"),
    ("Express checkout", "form", "https://example.test/harbourview/checkout", "Stay"),
    ("Shuttle schedule", "file", "https://example.test/harbourview/shuttle.pdf", "Transport"),
]

CATEGORIES = {
    "Maintenance": ["HVAC", "Plumbing", "Electrical", "Elevator"],
    "Service": ["Housekeeping delay", "Front desk", "F&B"],
    "Billing": ["Disputed charge", "Rate question"],
    "Praise": [],
    "Question": ["Hours", "Amenities", "Directions"],
}

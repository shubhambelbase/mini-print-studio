import os
import json
import logging
from typing import List, Optional
from backend.models.template import PrintTemplate
from backend.models.print_job import ContentBlock

logger = logging.getLogger("TemplateManager")


class TemplateManager:
    """
    Manages default built-in thermal print templates and user-saved custom templates.
    """

    def __init__(self, templates_dir: str = "data/templates"):
        self.templates_dir = templates_dir
        os.makedirs(self.templates_dir, exist_ok=True)
        self.builtin_templates = self._get_builtin_templates()

    def _get_builtin_templates(self) -> List[PrintTemplate]:
        return [
            PrintTemplate(
                id="simple_note",
                name="Simple Note",
                description="Clean, minimal note layout with header and body text.",
                category="Notes",
                icon="file-text",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="QUICK NOTE", font_size="large", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="Write your thoughts or reminder notes here...", font_size="normal", align="left"),
                    ContentBlock(type="space", space_height=16)
                ]
            ),
            PrintTemplate(
                id="study_card",
                name="Study Flashcard",
                description="Study note template with topic title, key terms, and summary.",
                category="Notes",
                icon="book-open",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="STUDY FLASHCARD", font_size="title", align="center", invert=True),
                    ContentBlock(type="space", space_height=10),
                    ContentBlock(type="text", content="Topic: Computer Architecture", font_size="large", align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="• Key Term 1: Execution Pipeline\n• Key Term 2: Cache Coherence\n• Key Term 3: Memory Alignment", font_size="normal", align="left"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="Summary: Optimize data flow between L1 cache and registers to avoid stall cycles.", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="space", space_height=16)
                ]
            ),
            PrintTemplate(
                id="checklist",
                name="Daily Checklist",
                description="To-do checklist template with printable check boxes.",
                category="Notes",
                icon="check-square",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="DAILY CHECKLIST", font_size="large", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="[  ] Task 1: Review project PRD\n[  ] Task 2: Implement FastAPI backend\n[  ] Task 3: Test thermal printing engine\n[  ] Task 4: Verify preview renderer", font_size="normal", align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="Date: ____ / ____ / ________", font_size="small", align="right"),
                    ContentBlock(type="space", space_height=16)
                ]
            ),
            PrintTemplate(
                id="qr_label",
                name="QR Code Label",
                description="High resolution QR code with title and payload description.",
                category="Labels",
                icon="qr-code",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="WIFI CONNECT", font_size="large", align="center"),
                    ContentBlock(type="qr", qr_payload="WIFI:S:MyLocalNet;T:WPA;P:SecretPassword123;;", qr_size=5, qr_ecc="M", align="center"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="Scan QR to join network", font_size="small", align="center"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="barcode_label",
                name="Item Barcode Label",
                description="Product inventory label with Code128 barcode and item serial.",
                category="Labels",
                icon="barcode",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="MINI PRINT STUDIO", font_size="normal", align="center"),
                    ContentBlock(type="barcode", barcode_payload="SKU-88492019", barcode_type="code128", barcode_height=40, show_barcode_text=True, align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="Price: $19.99 | Shelf B-4", font_size="small", align="center"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="mini_receipt",
                name="Mini Receipt",
                description="Compact receipt format for purchases or transactions.",
                category="Receipts",
                icon="receipt",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="MINI COFFEE LAB", font_size="title", align="center"),
                    ContentBlock(type="text", content="123 Developer Way\nOrder #042", font_size="small", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="1x Espresso           $3.50\n1x Oat Milk Latte     $4.50\n1x Matcha Scone       $4.00", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="double"),
                    ContentBlock(type="text", content="TOTAL: $12.00", font_size="large", align="right"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="Thank you for visiting!", font_size="small", italic=True, align="center"),
                    ContentBlock(type="qr", qr_payload="https://miniprint.local/receipt/042", qr_size=3, align="center"),
                    ContentBlock(type="space", space_height=16)
                ]
            ),
            PrintTemplate(
                id="structured_receipt",
                name="Structured Receipt",
                description="Invoice-style receipt with a proper item table and totals block.",
                category="Receipts",
                icon="table-2",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="PIXEL BAZAAR", font_size="title", align="center"),
                    ContentBlock(type="text", content="Invoice #INV-2031 · 2026-08-12", font_size="small", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="table",
                                 table_headers=["Item", "Qty", "Price"],
                                 table_rows=[
                                     ["Pixel Sticker Pack", "2", "$4.50"],
                                     ["Thermal Paper Roll", "1", "$6.99"],
                                     ["Mini Display Stand", "1", "$12.00"],
                                 ]),
                    ContentBlock(type="totals",
                                 totals_lines=[
                                     {"label": "Subtotal", "value": "$27.99", "dotted": True, "bold": False},
                                     {"label": "Tax (8%)", "value": "$2.24", "dotted": True, "bold": False},
                                     {"label": "TOTAL", "value": "$30.23", "dotted": True, "bold": True},
                                 ]),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="qr", qr_payload="https://miniprint.local/invoice/2031", qr_size=3, align="center"),
                    ContentBlock(type="text", content="Thank you for your purchase!", font_size="small", italic=True, align="center"),
                    ContentBlock(type="space", space_height=16)
                ]
            ),
            PrintTemplate(
                id="vintage_ticket",
                name="Vintage Ticket",
                description="A cool retro admission ticket layout with a graphic badge.",
                category="Tickets",
                icon="ticket",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="* ADMIT ONE *", font_size="large", invert=True, align="center"),
                    ContentBlock(type="space", space_height=10),
                    ContentBlock(type="text", content="THE GRAND\nEXHIBITION", font_size="title", align="center"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="image", image_data="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAJYAAACWAQAAAAAUekxPAAADn0lEQVR4nM1Wv2/lRBD+/EOxQdE9F0gcKOgZxB+QMsUJm46SvwClpEL5A5C8ETXStXQp6YAOun1Acd29a2hxpOhIQeGcUmyeNh40s2u/9cvzVSmY4vn58+zszOzsNxMRduU+fgABj4JdRsUIkhMDoHJ/7YApAMkUs7KmmWCtYIsJBiypQxRiVmwpt9g6rJM9DZYBpt2WKgswOOutGLQSB+EMN1GJI584YkORONiQmLWCdRnpBbUZ6eWI6WUvvvDHwZ4+3RwBOKsPXYzE29JK9s36aFhrExLHaEWq8ZjJrARAXaMrb8/k9lTsHOpSEkREbXXpM7swC6/X1q/9QfyaGq+nyJkjumE/LWNR70+HDEVuLcV97demqnFrbXbj1YiWuhE9m78ZT/us1K4OiqsRO+FiiAFTvhixo7wVrKufj9iTtJM99OgKkekzF8foCjvjfDk3oxr1VSJxJHdbjKpzsimQbg62NXr6Ce9LuA3q9pgY69mlUUypkAJFHmDlO6xnsQ6wQ2iOo7wIsIOc9STbgbRsr4oCJJG8dP1ETXWsp/jbIHHMeq2rm0G0QYwoNCdvMXY2ljzr6XVVFvGDG6wYCdMCHHOes3+ClBK9XPF5XE/0ns7wwQPOIcTI9QSyJa/d8gVLMWNvmilxOkZxgc3V99/gu48+6BRwULi19vUPHZ69+luKxdvL3/sSf0qoWwygy3fBORdJ3SP5ovjtq/LTpdOzpTzXOPnlj4UY0inoc+Dfn34GSkl4wjll+fDrGwX62O8B85ljM/dLZM2zMTb1yLz7v8Wi6ZnfA3Ea3jYWUz/+vp3jyEE2ndylHVEz9roJ0Mmd3rIQS9ointxAlmjOv6cT4Jqxb3e0fme9wwm0Fm7adRmg1ZaJhY0zvpchXQGlcN3kFvJbjHIodyd1zvuqoBzR96xX7PBGwfdjFUL3Yi/f8U/udBsmf2NYLxVKGeQWteQ5JKxWekA/IZ2XmntANEnM2nGdDagdF3p/X4iByjUNF1qVzvaZ8nxblne98DgKfTZib6zjprw9GbErI3kGOm7wTl5wGDGQmicj9rzl6iHqEzuSQaPm+y+aaHDmjvg95qNSP3rsrz59S98v1u+7iO+Pr33/RW5S16Zu67b0WGoTx+WvlK7fMpeQagxPDV1lk7k5B3PzkNkzN/VoqMPSv9nZOQza9aQLf9JuENoz1+2b//bNidN50he4O7nhnH0298yne+dYar01Ihs98pz9H5XfaJ4Fx8wZAAAAAElFTkSuQmCC", align="center", scale_mode="fit", dither_mode="threshold"),
                    ContentBlock(type="space", space_height=10),
                    ContentBlock(type="text", content="DATE: OCT 24   TIME: 8:00 PM\nROW: A        SEAT: 12", font_size="normal", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="barcode", barcode_payload="TKT-991203", barcode_type="code128", barcode_height=40, show_barcode_text=False, align="center"),
                    ContentBlock(type="space", space_height=20)
                ]
            ),
            PrintTemplate(
                id="shipping_label",
                name="Shipping Label",
                description="Professional shipping label with barcodes and return address.",
                category="Labels",
                icon="package",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="FROM:\nAcme Corp\n123 Wile E. Blvd\nDesert, AZ 85001", font_size="small", align="left"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="SHIP TO:", font_size="normal", align="left"),
                    ContentBlock(type="text", content="John Doe\n456 Tech Lane, Suite 900\nSilicon Valley, CA 94000", font_size="large", align="left"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="barcode", barcode_payload="1Z9999999999999999", barcode_type="code128", barcode_height=80, show_barcode_text=True, align="center"),
                    ContentBlock(type="space", space_height=10),
                    ContentBlock(type="text", content="PRIORITY MAIL", font_size="title", invert=True, align="center"),
                    ContentBlock(type="space", space_height=16)
                ]
            ),
            PrintTemplate(
                id="luggage_tag",
                name="Luggage Tag",
                description="Wallet/strap tag with owner details and contact QR.",
                category="Travel",
                icon="package",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="LUGGAGE TAG", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="NAME  : John Doe\nTEL   : +1 555-0100\nEMAIL : john@mail.com", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="ADDR  : 123 Main St\n        Springfield\nFLIGHT: UA 884 | SEAT 12A", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="qr", qr_payload="TEL:+15550100", qr_size=4, qr_ecc="M", align="center"),
                    ContentBlock(type="text", content="Scan to call the owner", font_size="small", align="center"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="cheat_sheet",
                name="Cheat Sheet",
                description="Dense one-page quick reference with rules, formulas, and commands.",
                category="Study",
                icon="book-open",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="QUICK REFERENCE // CS", font_size="title", align="center", invert=True),
                    ContentBlock(type="text", content="COMPUTER ARCHITECTURE · ONE-PAGER", font_size="small", align="center"),
                    ContentBlock(type="line", line_style="double"),
                    ContentBlock(type="text", content="TERMINOLOGY:", font_size="small", align="left"),
                    ContentBlock(type="text", content="Pipeline      : overlap instr stages\nCache         : fast memory near CPU\nCoherence     : keep copies in sync\nThroughput    : work done / time", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="FORMULAS:", font_size="small", align="left"),
                    ContentBlock(type="text", content="CPU time = IC x CPI x cycle\nAMAT      = hit + miss x missPen\nSpeedup   = T_old / T_new", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="KEY COMMANDS:", font_size="small", align="left"),
                    ContentBlock(type="text", content="git: clone / add / commit / push\nsql: SELECT * FROM t WHERE id=1\nssh: ssh user@host -p 22", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="Review before exam. Good luck!", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="wifi_login",
                name="Wi-Fi Login Card",
                description="Guest Wi-Fi card with network name, password, and scan-to-join QR code.",
                category="Network",
                icon="wifi",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="GUEST WIFI", font_size="title", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="NETWORK : MyLocalNet\nPASSWORD: Secret123\nSECURITY: WPA2", font_size="normal", monospace=True, align="left"),
                    ContentBlock(type="qr", qr_payload="WIFI:S:MyLocalNet;T:WPA;P:Secret123;;", qr_size=5, qr_ecc="M", align="center"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="Scan the QR to join automatically", font_size="small", align="center"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="price_tag",
                name="Price Tag",
                description="Shelf-ready price tag with large price, product name, and barcode.",
                category="Labels",
                icon="tag",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="$ 19.99", font_size="title", align="center"),
                    ContentBlock(type="text", content="PREMIUM NOTEBOOK A5", font_size="normal", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="barcode", barcode_payload="88492019", barcode_type="code128", barcode_height=55, show_barcode_text=True, align="center"),
                    ContentBlock(type="text", content="SKU: 88492019", font_size="small", align="center", monospace=True),
                    ContentBlock(type="space", space_height=10),
                    ContentBlock(type="text", content="STOCK: 42 | AISLE: B-4", font_size="small", align="center"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="weekly_timetable",
                name="Weekly Timetable",
                description="Week-at-a-glance schedule grid in clean monospace rows.",
                category="Study",
                icon="calendar",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="WEEKLY TIMETABLE", font_size="title", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="MON  08-09 ALGO | 10-12 MATH\nTUE  09-10 DB   | 11-13 PHYSICS\nWED  08-10 LAB  | 14-16 CHEM\nTHU  09-11 NETW | 12-14 OS\nFRI  10-12 STAT | 15-16 TUTOR\nSAT  09-11 REVISION / PRACTICE\nSUN  FREE DAY", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="double"),
                    ContentBlock(type="text", content="TOTAL: 34h this week", font_size="small", align="center"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="grocery_list",
                name="Grocery List",
                description="Categorized shopping list with printable checkboxes.",
                category="Shopping",
                icon="shopping-cart",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="GROCERY LIST", font_size="large", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="PRODUCE:", font_size="small", align="left"),
                    ContentBlock(type="text", content="[  ] Apples x6\n[  ] Bananas x4\n[  ] Onions 500g\n[  ] Spinach 1 bag", font_size="small", align="left"),
                    ContentBlock(type="text", content="DAIRY:", font_size="small", align="left"),
                    ContentBlock(type="text", content="[  ] Milk 1L\n[  ] Butter 250g\n[  ] Cheese 200g", font_size="small", align="left"),
                    ContentBlock(type="text", content="MEAT & PANTRY:", font_size="small", align="left"),
                    ContentBlock(type="text", content="[  ] Chicken 1kg\n[  ] Rice 2kg\n[  ] Olive oil\n[  ] Salt", font_size="small", align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="BUDGET: $40", font_size="small", align="right", monospace=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="password_vault",
                name="Password Vault Card",
                description="Compact app/login cheat card in monospace. Keep it safe.",
                category="Security",
                icon="lock",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="PASSWORD VAULT", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="github.com   : hunter2!\nmail        : sun-9912\nbank        : 88!secure\nrouter      : admin#2026\nwifi        : net@55xy", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="2FA codes on phone, not here.", font_size="small", align="center", italic=True),
                    ContentBlock(type="text", content="ROTATE EVERY 90 DAYS", font_size="small", align="center"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="gift_tag",
                name="Gift Tag",
                description="Cute gift tag with To/From lines and a decorative border.",
                category="Creative",
                icon="gift",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="* GIFT TAG *", font_size="large", align="center", invert=True),
                    ContentBlock(type="space", space_height=8),
                    ContentBlock(type="text", content="TO: ______________________", font_size="normal", align="left"),
                    ContentBlock(type="text", content="FROM: ____________________", font_size="normal", align="left"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="HAPPY BIRTHDAY!", font_size="title", align="center"),
                    ContentBlock(type="text", content="May your day be as bright as this ink.", font_size="small", align="center", italic=True),
                    ContentBlock(type="line", line_style="double"),
                    ContentBlock(type="text", content="DATE: ____/____/________", font_size="small", align="right"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="medication_schedule",
                name="Medication Schedule",
                description="Weekly pill schedule with check boxes per day.",
                category="Health",
                icon="pill",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="MEDICATION SCHEDULE", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="PARACETAMOL 500mg — 1 pill\nVITAMIN D3 — 1 capsule\nOMEPRAZOLE 20mg — 1 before food", font_size="small", align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="MON TUE WED THU FRI SAT SUN\n[  ] [  ] [  ] [  ] [  ] [  ] [  ]", font_size="small", monospace=True, align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="MORNING: after breakfast\nEVENING: after dinner", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="text", content="Consult doctor before changing dose.", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="quote_card",
                name="Inspirational Quote",
                description="Big inverted typography quote poster.",
                category="Creative",
                icon="quote",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="space", space_height=8),
                    ContentBlock(type="text", content="\"THE BEST WAY OUT\nIS ALWAYS\nTHROUGH\"", font_size="title", align="center"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="- ROBERT FROST", font_size="normal", align="right"),
                    ContentBlock(type="text", content="HARD WORK BRINGS LUCK", font_size="small", align="center", monospace=True),
                    ContentBlock(type="space", space_height=8),
                    ContentBlock(type="text", content="PRINTED ON: ____/____/______", font_size="small", align="center"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="business_card",
                name="Business Card Mini",
                description="Pocket business card with contact details and QR link.",
                category="Contacts",
                icon="user",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="ALEX DOE", font_size="title", align="center"),
                    ContentBlock(type="text", content="FULL-STACK DEVELOPER", font_size="small", align="center", letter_spacing=2),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="TEL   : +1 555 0100\neMAIL : alex@dev.io\nWEB   : dev.io", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="qr", qr_payload="https://dev.io", qr_size=4, qr_ecc="M", align="center"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="Scan to save my contact", font_size="small", align="center"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="emergency_contacts",
                name="Emergency Contacts Card",
                description="Wallet-size emergency numbers card with important personal contacts.",
                category="Contacts",
                icon="phone",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="EMERGENCY CONTACTS", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="POLICE     : 100\nAMBULANCE  : 102\nFIRE       : 101", font_size="normal", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="HOME       : 555-0142\nFAMILY     : 555-0187\nDOCTOR     : 555-0123\nNEIGHBOR   : 555-0119", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="double"),
                    ContentBlock(type="text", content="BLOOD TYPE: O+\nALLERGIES  : PENICILLIN", font_size="small", align="left"),
                    ContentBlock(type="text", content="Keep this card in your wallet", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="invoice_mini",
                name="Mini Invoice",
                description="Compact invoice with item lines, totals, and payment details.",
                category="Receipts",
                icon="receipt",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="MINI INVOICE", font_size="title", align="center", invert=True),
                    ContentBlock(type="text", content="INV # 0042 | DATE: ____/____/______", font_size="small", align="center", monospace=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="BILL TO:", font_size="small", align="left"),
                    ContentBlock(type="text", content="Acme Corp / John Doe\n456 Tech Lane", font_size="normal", align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="1x Web design      $350.00\n2x Logo drafts      $120.00\n1x Hosting setup     $25.00", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="double"),
                    ContentBlock(type="text", content="SUBTOTAL: $495.00\nTAX (10%):  $49.50\nTOTAL:     $544.50", font_size="normal", monospace=True, align="right"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="PAY BY: Bank transfer\nDUE IN: 14 days\nThanks for your business!", font_size="small", align="left"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="daily_planner",
                name="Day Planner",
                description="Hour-by-hour daily schedule with writing lines.",
                category="Study",
                icon="clock",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="DAY PLANNER", font_size="large", align="center", invert=True),
                    ContentBlock(type="text", content="DATE: ____/____/______", font_size="small", align="right", monospace=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="06:00  ____________________\n07:00  ____________________\n08:00  ____________________\n09:00  ____________________\n10:00  ____________________\n11:00  ____________________\n12:00  ____________________\n13:00  ____________________\n14:00  ____________________\n15:00  ____________________\n16:00  ____________________\n17:00  ____________________\n18:00  ____________________\n19:00  ____________________\n20:00  ____________________\n21:00  ____________________", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="TOP 3 PRIORITIES:\n1. ____________\n2. ____________\n3. ____________", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="packing_list",
                name="Packing Checklist",
                description="Travel packing checklist grouped by category with checkboxes.",
                category="Travel",
                icon="backpack",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="PACKING LIST", font_size="large", align="center", invert=True),
                    ContentBlock(type="text", content="TRIP: ________ | DAYS: ____", font_size="small", align="center", monospace=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="CLOTHES:\n[  ] Shirts x4\n[  ] Pants x2\n[  ] Socks x4\n[  ] Jacket / umbrella", font_size="small", align="left"),
                    ContentBlock(type="text", content="TOILETRIES:\n[  ] Toothbrush & paste\n[  ] Soap / shampoo\n[  ] Meds + first aid", font_size="small", align="left"),
                    ContentBlock(type="text", content="ELECTRONICS:\n[  ] Phone + charger\n[  ] Power bank\n[  ] Earphones\n[  ] Adapter plug", font_size="small", align="left"),
                    ContentBlock(type="text", content="DOCUMENTS:\n[  ] Passport / ID\n[  ] Tickets & hotel\n[  ] Cash + cards", font_size="small", align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="Charged all devices before leaving!", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="plant_care",
                name="Plant Care Card",
                description="Care schedule for your houseplants.",
                category="Home",
                icon="leaf",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="PLANT CARE", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="PLANT: Monstera Deliciosa\nWATER: Every 7 days\nSOIL : Keep moist, not wet\nSUN  : Indirect bright\nFERT : Monthly (spring-summer)\nREPOT: Every 2 years", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="WEEKLY WATERING LOG:\nW1 [  ]  W2 [  ]  W3 [  ]  W4 [  ]", font_size="small", monospace=True, align="center"),
                    ContentBlock(type="text", content="Yellow leaves = overwatering", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="home_info",
                name="House Info Card",
                description="All your home essentials on one slip: wifi, codes, and utilities.",
                category="Home",
                icon="home",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="HOUSE INFO", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="ADDRESS: 42 Maple St, Springfield", font_size="small", bold=False, align="left"),
                    ContentBlock(type="text", content="WIFI    : MyHome_5G\nWIFI PW : maple42!home\nROUTER  : 192.168.1.1 / admin", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="ALARM   : 4281\nGARAGE  : 7742\nMAIN LK : deadbolt + handle", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="UTILITIES:\nPOWER: 555-0101\nWATER: 555-0102\nGAS  : 555-0103", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="text", content="Keep in a safe place, not on the door!", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="budget_sheet",
                name="Budget Sheet",
                description="Monthly budget tracker with planned vs actual columns.",
                category="Finance",
                icon="wallet",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="MONTHLY BUDGET", font_size="large", align="center", invert=True),
                    ContentBlock(type="text", content="MONTH: ________  INCOME: $_______", font_size="small", align="center", monospace=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="ITEM         PLAN    ACTUAL\nRent         $800     ______\nFood         $300     ______\nTransport    $80      ______\nUtilities    $120     ______\nFun          $100     ______\nSavings      $150     ______", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="double"),
                    ContentBlock(type="text", content="TOTAL PLAN: $1550\nLEFTOVER: $_______", font_size="small", monospace=True, align="right"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="Rule: 50/30/20 — needs, wants, savings", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="reading_list",
                name="Reading List",
                description="To-be-read book tracker with rating columns.",
                category="Study",
                icon="book-open",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="READING LIST", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="#  TITLE              RATE\n1  ______________    __/10\n2  ______________    __/10\n3  ______________    __/10\n4  ______________    __/10\n5  ______________    __/10", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="GOAL: 12 books this year\nCURRENT: ___ / 12", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="Reading 20 min/day = ~18 books/yr", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="workout_split",
                name="Workout Split",
                description="Weekly gym split with exercises and rep counts.",
                category="Health",
                icon="dumbbell",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="WEEKLY SPLIT", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="MON  PUSH   Bench 4x8 | OHP 3x10\nTUE  PULL   Rows 4x8 | Pullup 3x8\nWED  LEGS   Squat 4x6 | DL 3x5\nTHU  REST   Stretch + walk\nFRI  PUSH   Incline 4x8 | Fly 3x12\nSAT  PULL   Lat pull 4x10 | Curl 3x12\nSUN  REST   Mobility", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="WARMUP: 5 min cardio + dynamic\nCOOLDOWN: 5 min stretching", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="text", content="Progressive overload, stay hydrated!", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="fortune_cookie",
                name="Fortune Card",
                description="Daily fortune with lucky numbers and color.",
                category="Fun",
                icon="sparkles",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="TODAY'S FORTUNE", font_size="large", align="center", invert=True),
                    ContentBlock(type="space", space_height=6),
                    ContentBlock(type="text", content="\"A SMALL ROUTINE\nTODAY LEADS TO\nA BIG WIN TOMORROW\"", font_size="title", align="center"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="LUCKY NUMBERS: 7 · 14 · 21 · 42\nLUCKY COLOR : ORANGE\nMOOD        : PRODUCTIVE", font_size="small", monospace=True, align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="Tip: print this every morning.", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="compliment_coupons",
                name="Compliment Coupons",
                description="Tear-off coupon book — one free hug, movie night, and more.",
                category="Fun",
                icon="gift",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="COUPON BOOK", font_size="large", align="center", invert=True),
                    ContentBlock(type="text", content="FOR: __________  FROM: __________", font_size="small", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="ONE FREE HUG", font_size="normal", align="center"),
                    ContentBlock(type="text", content="Valid any time. No expiration.\n[  ] Redeemed", font_size="small", align="center"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="MOVIE NIGHT PASS", font_size="normal", align="center"),
                    ContentBlock(type="text", content="Winner picks the film + snacks.\n[  ] Redeemed", font_size="small", align="center"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="COOKIE DUTY EXEMPTION", font_size="normal", align="center"),
                    ContentBlock(type="text", content="Skip baking duty once, no questions.\n[  ] Redeemed", font_size="small", align="center"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="BLANK CANVAS COUPON", font_size="normal", align="center"),
                    ContentBlock(type="text", content="Write your own: ________________\n[  ] Redeemed", font_size="small", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="Expires: never. Redeem with love.", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="rpg_character",
                name="RPG Character Sheet",
                description="Mini tabletop character sheet with stats and inventory.",
                category="Games",
                icon="swords",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="CHARACTER SHEET", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="NAME : __________\nCLASS: __________\nLEVEL: __   RACE: __________", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="text", content="HP: ********  MP: ******\nAC: 14  SPEED: 30ft", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="STR  __     DEX  __\nCON  __     INT  __\nWIS  __     CHA  __", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="INVENTORY:\n[ ] Sword +1\n[ ] Healing potion x3\n[ ] Rope 50ft\n[ ] Lucky coin", font_size="small", align="left"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="Roll 1d20. May the dice favor you.", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="sudoku",
                name="Sudoku Grid",
                description="Printable 9x9 sudoku puzzle with a few hints.",
                category="Games",
                icon="grid",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="SUDOKU #1", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="5 3 · | · 7 · | · · ·\n6 · · | 1 9 5 | · · ·\n· 9 8 | · · · | · 6 ·\n------+------+------\n8 · · | · 6 · | · · 3\n4 · · | 8 · 3 | · · 1\n7 · · | · 2 · | · · 6\n------+------+------\n· 6 · | · · · | 2 8 ·\n· · · | 4 1 9 | · · 5\n· · · | · 8 · | · 7 9", font_size="small", monospace=True, align="center"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="Medium difficulty · 36 clues\nRules: 1-9 in each row, col, box", font_size="small", align="center"),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="movie_ticket",
                name="Movie Night Ticket",
                description="Bogus cinema ticket — perfect for movie nights at home.",
                category="Tickets",
                icon="clapperboard",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="ADMIT ONE", font_size="title", align="center", invert=True),
                    ContentBlock(type="text", content="CINEMA HOME · SCREEN 1", font_size="small", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="FILM: Interstellar (2014)\nDATE: ____/____/______\nTIME: 21:00\nSEAT: C-7\nFORMAT: 4K + Snacks", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="barcode", barcode_payload="MOVIE-C7-2100", barcode_type="code128", barcode_height=35, show_barcode_text=False, align="center"),
                    ContentBlock(type="text", content="Keep stub · Lights off · Phones away", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="truth_dare",
                name="Truth or Dare Cards",
                description="Party-ready truth or dare prompt cards with tear lines.",
                category="Fun",
                icon="dices",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="TRUTH OR DARE", font_size="large", align="center", invert=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="TRUTH: What's the most\nembarrassing thing you've\ndone in public?", font_size="normal", align="center"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="DARE: Speak with an accent\nfor the next 5 minutes.", font_size="normal", align="center"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="TRUTH: What was your\nfirst-ever online username?", font_size="normal", align="center"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="DARE: Dance like nobody's\nwatching for 30 seconds.", font_size="normal", align="center"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="TRUTH: Who do you secretly\ntext the most?", font_size="normal", align="center"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="DARE: Let someone post\none photo from your phone.", font_size="normal", align="center"),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="House rules: no cop-outs, sip on truth.", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="kanban_board",
                name="Kanban Board",
                description="Three-column task board with sticky-note lines.",
                category="Work",
                icon="kanban",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="KANBAN BOARD", font_size="large", align="center", invert=True),
                    ContentBlock(type="text", content="WEEK: ____ | DATE: ____/____/______", font_size="small", align="center", monospace=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="TO DO:", font_size="normal", align="left"),
                    ContentBlock(type="text", content="[ ] ______________\n[ ] ______________\n[ ] ______________\n[ ] ______________", font_size="small", align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="DOING:", font_size="normal", align="left"),
                    ContentBlock(type="text", content="> ______________\n> ______________", font_size="small", align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="DONE:", font_size="normal", align="left"),
                    ContentBlock(type="text", content="x ______________\nx ______________", font_size="small", align="left"),
                    ContentBlock(type="line", line_style="dotted"),
                    ContentBlock(type="text", content="Limit WIP to 2. Move it, don't add to it.", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            ),
            PrintTemplate(
                id="chore_chart",
                name="Chore Chart",
                description="Weekly rotating chore schedule with check boxes.",
                category="Home",
                icon="brush",
                is_builtin=True,
                blocks=[
                    ContentBlock(type="text", content="CHORE CHART", font_size="large", align="center", invert=True),
                    ContentBlock(type="text", content="WEEK OF: ____/____/______", font_size="small", align="center", monospace=True),
                    ContentBlock(type="line", line_style="solid"),
                    ContentBlock(type="text", content="MON  Dishes  [  ]  Vacuum [  ]\nTUE  Laundry [  ]  Trash  [  ]\nWED  Bathroom[  ]  Dust   [  ]\nTHU  Dishes  [  ]  Mop    [  ]\nFRI  Laundry [  ]  Trash  [  ]\nSAT  Deep cln[  ]  Plants [  ]\nSUN  Meal prep [  ]  Rest  [  ]", font_size="small", monospace=True, align="left"),
                    ContentBlock(type="line", line_style="dashed"),
                    ContentBlock(type="text", content="ROTATION: swap duties weekly", font_size="small", align="center", italic=True),
                    ContentBlock(type="text", content="DONE = crossed off before dinner", font_size="small", align="center", italic=True),
                    ContentBlock(type="space", space_height=12)
                ]
            )
  ,
            PrintTemplate(
                id="image_print_test",
                name="Image Print Test",
                description="Test image with recommended photo settings pre-applied for the clearest print.",
                category="Creative",
                icon="image",
                is_builtin=True,
                blocks=[ContentBlock(type="image", image_data="data:image/png;base64,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", align="center", dither_mode="atkinson", scale_mode="fit")]
            )
        ]

    def get_all_templates(self) -> List[PrintTemplate]:
        templates = list(self.builtin_templates)
        # Load user custom templates
        if os.path.exists(self.templates_dir):
            for file_name in os.listdir(self.templates_dir):
                if file_name.endswith(".json"):
                    file_path = os.path.join(self.templates_dir, file_name)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            tpl = PrintTemplate(**data)
                            tpl.is_builtin = False
                            templates.append(tpl)
                    except Exception as e:
                        logger.error(f"Error loading custom template {file_name}: {e}")
        return templates

    def get_template(self, template_id: str) -> Optional[PrintTemplate]:
        for t in self.get_all_templates():
            if t.id == template_id:
                return t
        return None

    def save_custom_template(self, template: PrintTemplate) -> bool:
        template.is_builtin = False
        file_path = os.path.join(self.templates_dir, f"{template.id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(template.model_dump(), f, indent=2)
        return True

    def delete_custom_template(self, template_id: str) -> bool:
        file_path = os.path.join(self.templates_dir, f"{template_id}.json")
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

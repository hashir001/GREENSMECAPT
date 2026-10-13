"""Generate the reproducible GREENSMECAPT conference evidence dossier."""

from __future__ import annotations

import io
import json
import random
from pathlib import Path

import fitz
from PIL import Image, ImageEnhance, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp" / "pdfs" / "mixed_source"
OUT = ROOT / "output" / "pdf" / "greensmecapt_conference_demo_pack"
TMP.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

GREEN = colors.HexColor("#176B4D")
DARK = colors.HexColor("#18382F")
MINT = colors.HexColor("#EAF4EF")
LIGHT = colors.HexColor("#F5F7F6")
LINE = colors.HexColor("#D4DED8")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleX", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23, leading=28, textColor=DARK, spaceAfter=10))
styles.add(ParagraphStyle(name="SubX", parent=styles["BodyText"], fontName="Helvetica", fontSize=11, leading=16, textColor=GREEN, spaceAfter=12))
styles.add(ParagraphStyle(name="H1X", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=DARK, spaceBefore=5, spaceAfter=9))
styles.add(ParagraphStyle(name="H2X", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=GREEN, spaceBefore=8, spaceAfter=5))
styles.add(ParagraphStyle(name="BodyX", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.4, leading=14, textColor=colors.HexColor("#293D35"), spaceAfter=7))
styles.add(ParagraphStyle(name="SmallX", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.8, leading=10.5, textColor=colors.HexColor("#50635B")))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#687A72"))
    canvas.drawString(18 * mm, 9 * mm, "FICTIONAL DEMO EVIDENCE - GREENSMECAPT")
    canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def tbl(rows, widths, header=True):
    cooked = [[Paragraph(str(cell), styles["SmallX"]) for cell in row] for row in rows]
    table = Table(cooked, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    for idx in range(1 if header else 0, len(rows)):
        if idx % 2 == 0:
            commands.append(("BACKGROUND", (0, idx), (-1, idx), LIGHT))
    table.setStyle(TableStyle(commands))
    return table


def banner(text):
    box = Table([[Paragraph(text, styles["BodyX"])]], colWidths=[170 * mm])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), MINT), ("BOX", (0, 0), (-1, -1), 0.7, GREEN), ("PADDING", (0, 0), (-1, -1), 9)]))
    return box


def doc(path, story):
    target = OUT / path
    SimpleDocTemplate(str(target), pagesize=A4, rightMargin=19 * mm, leftMargin=19 * mm, topMargin=17 * mm, bottomMargin=20 * mm, title=target.stem).build(story, onFirstPage=footer, onLaterPages=footer)
    return target


def raster_copy(source, target):
    pdf = fitz.open(source)
    pages = []
    rng = random.Random(target.stem)
    for page in pdf:
        pix = page.get_pixmap(matrix=fitz.Matrix(2.6, 2.6), alpha=False)
        image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
        image = ImageEnhance.Contrast(image).enhance(0.97)
        image = image.filter(ImageFilter.GaussianBlur(0.12))
        image = image.rotate(rng.uniform(-0.15, 0.15), Image.Resampling.BICUBIC, fillcolor=248)
        pages.append(image.convert("RGB"))
    pages[0].save(target, "PDF", resolution=187, save_all=True, append_images=pages[1:])
    for image in pages:
        image.close()
    pdf.close()


def utility_story(c):
    return [
        Paragraph("ELECTRICITY ACCOUNT STATEMENT", styles["TitleX"]),
        Paragraph(c["company"], styles["SubX"]),
        banner("Image-only utility evidence prepared to force OCR routing. Values are fictional and intended only for platform testing."),
        Spacer(1, 8 * mm),
        tbl([["Account", c["account"]], ["Service address", c["site"]], ["Billing period", "1 January 2025 to 31 December 2025"], ["Tariff", "Industrial LV - demonstration"], ["Meter", c["meter"]]], [45 * mm, 125 * mm], header=False),
        Spacer(1, 8 * mm),
        Paragraph("Annual electricity summary", styles["H1X"]),
        tbl([["Indicator", "2024 baseline", "2025 reported", "Unit / scope"], ["Electricity consumption", f'{c["electricity_2024"]:,}', f'{c["electricity"]:,}', "kWh; whole facility"], ["Renewable energy share", f'{c["renewable_2024"]}%', f'{c["renewable"]}%', "Percent of electricity"], ["Production output", f'{c["output_2024"]:,}', f'{c["output"]:,}', "Finished units"], ["Electricity intensity", f'{c["intensity_2024"]:.3f}', f'{c["intensity"]:.3f}', "kWh per finished unit"]], [44 * mm, 37 * mm, 37 * mm, 52 * mm]),
        Spacer(1, 7 * mm),
        Paragraph(f'Total electricity use was {c["electricity"]:,} kWh during calendar year 2025. Renewable energy share was {c["renewable"]} percent for the same operational scope. Electricity intensity equals annual electricity consumption divided by {c["output"]:,} finished packaging units.', styles["BodyX"]),
        PageBreak(),
        Paragraph("METER AND SUPPLY RECORD", styles["TitleX"]),
        Paragraph(c["company"], styles["SubX"]),
        tbl([["Record", "Opening / baseline", "Closing / reported", "Validation note"], ["Main electricity meter", c["opening"], c["closing"], "Difference reconciled to annual statement"], ["Onsite renewable supply", f'{c["renewable_kwh"]:,} kWh', f'{c["renewable"]}% share', "Metered generation plus renewable tariff"], ["Non-renewable electricity", f'{c["nonrenewable_kwh"]:,} kWh', f'{100-c["renewable"]}% share', "Residual purchased electricity"]], [47 * mm, 38 * mm, 38 * mm, 47 * mm]),
        Spacer(1, 9 * mm),
        banner("Verification note: The bill establishes electricity quantity and renewable share. It does not by itself prove environmental performance unless reporting period, operational boundary and production denominator are considered."),
        Spacer(1, 12 * mm),
        tbl([["Issued by", "Fictional Emirates Industrial Utility"], ["Statement reference", c["statement"]], ["Issue date", "10 January 2026"], ["Document status", "Fictional OCR demonstration"]], [45 * mm, 125 * mm], header=False),
    ]


def text_story(c):
    return [
        Paragraph("2025 Sustainability and Impact Narrative", styles["TitleX"]),
        Paragraph(c["company"], styles["SubX"]),
        banner("Searchable native-text report. This file tests direct PDF text reading rather than OCR or table extraction."),
        Spacer(1, 7 * mm),
        Paragraph("Company and reporting boundary", styles["H1X"]),
        Paragraph(f'{c["company"]} manufactures recyclable paper-fibre food packaging at one facility in {c["location"]}. The reporting period is calendar year 2025. The organisational boundary includes production, sanitation, company-controlled onsite fuel and purchased electricity. Supplier production, employee commuting and customer disposal are excluded.', styles["BodyX"]),
        Paragraph("Nature of green contribution", styles["H1X"]),
        Paragraph(c["green_contribution"], styles["BodyX"]),
        Paragraph("Water performance", styles["H1X"]),
        Paragraph(f'Water consumption was {c["water"]:,} m3 in 2025 compared with {c["water_2024"]:,} m3 in 2024. Production output was {c["output"]:,} finished units. Water intensity was therefore {c["water_intensity"]:.2f} litres per finished unit, compared with {c["water_intensity_2024"]:.2f} litres per unit in the baseline year. The boundary covers production and sanitation water.', styles["BodyX"]),
        Paragraph("Greenhouse-gas emissions", styles["H1X"]),
        Paragraph(f'Total GHG emissions were {c["ghg"]:.1f} tCO2e in 2025. This combines company-controlled Scope 1 fuel and location-based Scope 2 electricity. The 2024 baseline was {c["ghg_2024"]:.1f} tCO2e. GHG intensity was {c["ghg_intensity"]:.3f} kgCO2e per finished unit. The values are management estimates and are not presented as externally assured.', styles["BodyX"]),
        PageBreak(),
        Paragraph("Waste, circularity and customer effect", styles["TitleX"]),
        Paragraph("Resource use and recovery", styles["H1X"]),
        Paragraph(f'Total waste generated was {c["waste"]:,} kg during 2025. Waste recycled or reused was {c["diverted_kg"]:,} kg, producing a waste diversion rate of {c["diversion"]} percent. Waste sent to disposal was {c["disposed_kg"]:,} kg. The waste boundary includes production offcuts, rejected fibre products and general site waste. Diversion is measured by mass accepted for recycling or internal reuse divided by total waste generated.', styles["BodyX"]),
        Paragraph("Customer environmental effect", styles["H1X"]),
        Paragraph(c["customer_effect"], styles["BodyX"]),
        Paragraph("Operational transition", styles["H1X"]),
        Paragraph(c["transition"], styles["BodyX"]),
        Paragraph("Cross-document reconciliation test", styles["H1X"]),
        Paragraph(f'This management narrative records annual electricity consumption as {c["electricity_narrative"]:,} kWh for 2025. The utility statement is the authoritative meter record and reports {c["electricity"]:,} kWh for the same facility and period. The difference is deliberately retained so the evidence workspace can flag and resolve a real cross-document conflict rather than silently selecting a value.', styles["BodyX"]),
        Paragraph("Additional environmental information", styles["H1X"]),
        Paragraph(c["discovery_metric"], styles["BodyX"]),
        Paragraph("A separate supplier note states that recycled input increased by 11 percent but does not identify a baseline year, measurement boundary or supporting quantity. It is intentionally incomplete and should remain contextual rather than becoming a scored performance value.", styles["BodyX"]),
        Paragraph("Evidence limitations", styles["H1X"]),
        Paragraph("The reported figures are fictional demonstration data. Absolute consumption must be interpreted with production output, baseline trends and operational boundaries. Projected benefits are not counted as achieved results. Certification, permit and project-finance claims require their own supporting records.", styles["BodyX"]),
        Spacer(1, 10 * mm),
        tbl([["Prepared by", c["sustainability_manager"]], ["Role", "Operations and Sustainability Manager"], ["Approval date", "15 September 2026"], ["Status", "Management-approved fictional demonstration evidence"]], [46 * mm, 124 * mm], header=False),
    ]


def table_story(c):
    return [
        Paragraph("Financial and Investment Data Tables", styles["TitleX"]),
        Paragraph(c["company"], styles["SubX"]),
        banner("Table-heavy searchable PDF designed to test structured table extraction and financial evidence review."),
        Spacer(1, 7 * mm),
        Paragraph("Statement of financial position", styles["H1X"]),
        tbl([["AED", "31 Dec 2024", "31 Dec 2025"], ["Cash and equivalents", f'{c["cash_2024"]:,}', f'{c["cash"]:,}'], ["Trade receivables", f'{c["receivables_2024"]:,}', f'{c["receivables"]:,}'], ["Inventory and other current assets", f'{c["inventory_2024"]:,}', f'{c["inventory"]:,}'], ["Total current assets", f'{c["current_assets_2024"]:,}', f'{c["current_assets"]:,}'], ["Property, plant and other assets", f'{c["noncurrent_2024"]:,}', f'{c["noncurrent"]:,}'], ["Total assets", f'{c["assets_2024"]:,}', f'{c["assets"]:,}'], ["Total current liabilities", f'{c["current_liabilities_2024"]:,}', f'{c["current_liabilities"]:,}'], ["Total debt", f'{c["debt_2024"]:,}', f'{c["debt"]:,}']], [82 * mm, 44 * mm, 44 * mm]),
        Paragraph("Profit and cash-flow summary", styles["H1X"]),
        tbl([["AED", "Year 2024", "Year 2025"], ["Revenue", f'{c["revenue_2024"]:,}', f'{c["revenue"]:,}'], ["Net profit", f'{c["profit_2024"]:,}', f'{c["profit"]:,}'], ["Operating cash flow", f'{c["ocf_2024"]:,}', f'{c["ocf"]:,}']], [82 * mm, 44 * mm, 44 * mm]),
        PageBreak(),
        Paragraph("Financial assessment metrics", styles["TitleX"]),
        tbl([["Metric", "2025 value", "Unit", "Calculation / basis"], ["Return on assets (ROA)", c["roa"], "percent", "Net profit divided by total assets"], ["Revenue growth", c["growth"], "percent", "2025 revenue compared with 2024"], ["Current ratio", c["current_ratio"], "ratio", "Current assets divided by current liabilities"], ["Operating cash flow", f'{c["ocf"]:,}', "AED", "Cash flow from operations"], ["Debt to assets", c["debt_assets"], "percent", "Total debt divided by total assets"]], [46 * mm, 30 * mm, 28 * mm, 66 * mm]),
        Spacer(1, 9 * mm),
        Paragraph("Funding request", styles["H1X"]),
        tbl([["Investment metric", "Reported value", "Status"], ["Project title", c["project"], "Proposed"], ["Project cost", f'AED {c["project_cost"]:,}', "Supplier-supported estimate"], ["Requested amount", f'AED {c["requested"]:,}', "Funding requested"], ["SME contribution", f'AED {c["contribution"]:,}', "Applicant contribution"], ["Expected annual savings", f'AED {c["savings"]:,} per year', "Projection; not achieved performance"], ["Implementation period", c["timeline"], "Planned"]], [52 * mm, 67 * mm, 51 * mm]),
        PageBreak(),
        Paragraph("Project budget and readiness matrix", styles["TitleX"]),
        tbl([["Work package", "Budget AED", "Evidence reference"], *[[x[0], f'{x[1]:,}', x[2]] for x in c["packages"]]], [70 * mm, 35 * mm, 65 * mm]),
        Spacer(1, 8 * mm),
        tbl([["Readiness area", "Evidence state", "Short explanation"], *c["readiness"]], [46 * mm, 38 * mm, 86 * mm]),
        Spacer(1, 8 * mm),
        banner("Financial values remain separate from environmental performance. Readiness evidence is contextual and does not automatically change TOPSIS weights. No DEMATEL pairwise expert judgments are contained in this document."),
    ]


terra = {
    "company": "TerraPack Circular Industries LLC", "location": "Dubai Industrial City", "account": "FEIU-TP-88421", "site": "Dubai Industrial City, Plot D-118", "meter": "MTR-TP-44109", "statement": "TP-UTIL-2025", "opening": "1,844,210 kWh", "closing": "2,254,210 kWh",
    "electricity_2024": 460_000, "electricity": 410_000, "renewable_2024": 45, "renewable": 72, "renewable_kwh": 295_200, "nonrenewable_kwh": 114_800, "output_2024": 2_200_000, "output": 2_400_000, "intensity_2024": 0.209, "intensity": 0.171,
    "electricity_narrative": 408_000,
    "water_2024": 5_600, "water": 5_200, "water_intensity_2024": 2.55, "water_intensity": 2.17, "ghg_2024": 151.0, "ghg": 96.0, "ghg_intensity": 0.040, "waste": 84_000, "diverted_kg": 65_520, "disposed_kg": 18_480, "diversion": 78,
    "green_contribution": "The company replaces selected single-use plastic food containers with moulded products containing recovered paper fibre. Environmental contribution is demonstrated through recycled-content purchasing records, production records and customer delivery records rather than inferred from the company name.",
    "customer_effect": "Two food-service customers completed pilots in 2025. Customer records indicate replacement of conventional plastic trays in defined product lines. Avoided-impact claims are not converted to tonnes of emissions because a verified customer baseline is not yet available.",
    "transition": "Management approved a rooftop solar and closed-loop process-water project supported by a supplier quotation, implementation schedule and internal contribution. Expected savings remain projections until commissioning and post-project measurement.", "sustainability_manager": "Mariam Al Noor",
    "discovery_metric": "A voluntary habitat project established 1,250 square metres of native planting beside the facility. This biodiversity-related measure sits outside the current scored metric catalog and should be retained as source-linked additional context for later governance review.",
    "cash_2024": 900_000, "cash": 1_050_000, "receivables_2024": 2_050_000, "receivables": 2_300_000, "inventory_2024": 1_100_000, "inventory": 1_375_000, "current_assets_2024": 4_050_000, "current_assets": 4_725_000, "noncurrent_2024": 6_950_000, "noncurrent": 7_275_000, "assets_2024": 11_000_000, "assets": 12_000_000, "current_liabilities_2024": 3_200_000, "current_liabilities": 3_500_000, "debt_2024": 4_900_000, "debt": 5_040_000, "revenue_2024": 16_900_000, "revenue": 18_600_000, "profit_2024": 890_000, "profit": 1_020_000, "ocf_2024": 1_050_000, "ocf": 1_200_000, "roa": "8.5%", "growth": "10.1%", "current_ratio": "1.35", "debt_assets": "42.0%",
    "project": "Rooftop solar and closed-loop process-water upgrade", "project_cost": 1_800_000, "requested": 1_300_000, "contribution": 500_000, "savings": 480_000, "timeline": "January to September 2027", "packages": [("420 kWp rooftop solar", 1_080_000, "TP-Q-2026-118"), ("Water recirculation and filtration", 480_000, "TP-WR-44"), ("Metering, commissioning and training", 240_000, "TP-IMP-09")],
    "readiness": [("Leadership commitment", "Enabling evidence", "Board sponsor and monthly review"), ("Technical capability", "Enabling evidence", "Maintenance training scheduled"), ("Digital and data", "Enabling evidence", "Sub-metering plan approved"), ("Regulation and standards", "Enabling evidence", "Active permit and demo ISO record"), ("Access to finance", "Mixed evidence", "Applicant contribution available; facility pending")],
}

blue = {
    "company": "BlueMesa Sustainable Packaging LLC", "location": "Sharjah Industrial Area", "account": "FEIU-BM-21907", "site": "Sharjah Industrial Area 10, Plot S-72", "meter": "MTR-BM-77218", "statement": "BM-UTIL-2025", "opening": "3,107,550 kWh", "closing": "3,797,550 kWh",
    "electricity_2024": 720_000, "electricity": 690_000, "renewable_2024": 20, "renewable": 28, "renewable_kwh": 193_200, "nonrenewable_kwh": 496_800, "output_2024": 2_900_000, "output": 3_100_000, "intensity_2024": 0.248, "intensity": 0.223,
    "electricity_narrative": 705_000,
    "water_2024": 9_300, "water": 9_100, "water_intensity_2024": 3.21, "water_intensity": 2.94, "ghg_2024": 271.0, "ghg": 238.0, "ghg_intensity": 0.077, "waste": 142_000, "diverted_kg": 65_320, "disposed_kg": 76_680, "diversion": 46,
    "green_contribution": "The company manufactures moulded paper-fibre packaging intended to substitute selected plastic packaging formats. The contribution is supported by product specifications and delivery records. No universal claim is made for products without an identified customer baseline.",
    "customer_effect": "Buyer demand for lower-impact packaging increased in 2025. Customer pilot evidence exists, but full lifecycle verification has not been completed. The platform should therefore retain the distinction between demonstrated deployment and estimated future impact.",
    "transition": "The proposed investment combines a high-efficiency moulding line with onsite solar. Production growth may offset part of the absolute energy reduction, so both total consumption and intensity must be monitored.", "sustainability_manager": "Omar Rahman",
    "discovery_metric": "The facility recorded 38 employee-led environmental improvement suggestions during 2025, of which 14 entered operational trials. This is useful organisational context but is not a defined environmental performance criterion.",
    "cash_2024": 1_450_000, "cash": 2_200_000, "receivables_2024": 2_650_000, "receivables": 3_000_000, "inventory_2024": 1_400_000, "inventory": 1_520_000, "current_assets_2024": 5_500_000, "current_assets": 6_720_000, "noncurrent_2024": 7_000_000, "noncurrent": 6_780_000, "assets_2024": 12_500_000, "assets": 13_500_000, "current_liabilities_2024": 3_500_000, "current_liabilities": 3_200_000, "debt_2024": 3_500_000, "debt": 3_240_000, "revenue_2024": 20_350_000, "revenue": 24_000_000, "profit_2024": 1_420_000, "profit": 1_782_000, "ocf_2024": 2_700_000, "ocf": 3_400_000, "roa": "13.2%", "growth": "17.9%", "current_ratio": "2.10", "debt_assets": "24.0%",
    "project": "High-efficiency moulding line and onsite solar phase 1", "project_cost": 2_400_000, "requested": 1_200_000, "contribution": 1_200_000, "savings": 390_000, "timeline": "March to December 2027", "packages": [("High-efficiency moulding line", 1_520_000, "BM-Q-772"), ("180 kWp onsite solar", 620_000, "BM-SOL-18"), ("Controls, commissioning and training", 260_000, "BM-OPS-12")],
    "readiness": [("Leadership commitment", "Enabling evidence", "Finance and operations sponsors"), ("Technical capability", "Mixed evidence", "Supplier training; internal support needed"), ("Digital and data", "Constraining evidence", "Energy sub-metering not installed"), ("Regulation and standards", "Mixed evidence", "Permit renewal and ISO plan pending"), ("Access to finance", "Mixed evidence", "Applicant contribution available; debt under review")],
}


def guide_story():
    return [
        Paragraph("GREENSMECAPT Conference Demonstration Pack", styles["TitleX"]),
        Paragraph("Two-company, mixed-format evidence dossier", styles["SubX"]),
        banner("All companies, people, accounts and values in this pack are fictional. The files are designed to exercise the implemented document, evidence, assessment and comparison workflow."),
        Spacer(1, 7 * mm),
        Paragraph("What the pack tests", styles["H1X"]),
        tbl([
            ["Document", "Format", "Expected system route"],
            ["01 utility bill", "Image-only scanned PDF", "Google Document AI OCR, then Gemini structured extraction"],
            ["02 sustainability report", "Born-digital narrative PDF", "Native parsing, then Gemini structured extraction"],
            ["03 financial and funding tables", "Born-digital table-heavy PDF", "Native/table parsing, then Gemini structured extraction"],
        ], [48 * mm, 43 * mm, 79 * mm]),
        Paragraph("Designed evidence challenges", styles["H1X"]),
        Paragraph("Each company has current and baseline environmental measures, denominators, financial statements, a funding request, projected savings and readiness observations. Each dossier also contains one deliberate electricity-value conflict, one incomplete claim and one useful item outside the scored metric catalog. These cases test source linking, conflict handling, missing-context treatment and discovery without forcing unsupported values into scoring.", styles["BodyX"]),
        Paragraph("Recommended demonstration order", styles["H1X"]),
        tbl([
            ["Step", "Action", "Expected output"],
            ["1", "Create both SME records and upload all three files under the correct company.", "Six separately traceable source documents"],
            ["2", "Wait for document processing and inspect evidence grouped by document.", "OCR/native text, page provenance, extracted values and context"],
            ["3", "Resolve the deliberate conflict; accept review-ready evidence only.", "Human-validated evidence ledger"],
            ["4", "Confirm company context and complete any genuinely missing assessment fields.", "Environmental, financial and readiness inputs"],
            ["5", "Prepare, approve and publish both profiles; run investor comparison.", "Green Score, financial view, evidence strength, readiness interpretation and MCDM comparison"],
        ], [15 * mm, 78 * mm, 77 * mm]),
        Spacer(1, 8 * mm),
        banner("Use ground_truth.json for extraction evaluation. It identifies authoritative values and the intended treatment of the deliberately conflicting or incomplete claims."),
    ]


def create_company(prefix, values):
    utility_source = TMP / f"{prefix}_utility_native_source.pdf"
    SimpleDocTemplate(str(utility_source), pagesize=A4, rightMargin=19 * mm, leftMargin=19 * mm, topMargin=17 * mm, bottomMargin=20 * mm).build(utility_story(values), onFirstPage=footer, onLaterPages=footer)
    utility_target = OUT / f"{prefix}_01_utility_bill_scanned.pdf"
    raster_copy(utility_source, utility_target)
    doc(f"{prefix}_02_sustainability_report_text.pdf", text_story(values))
    doc(f"{prefix}_03_financial_and_funding_tables.pdf", table_story(values))


doc("00_demo_guide.pdf", guide_story())
create_company("terra_pack", terra)
create_company("blue_mesa", blue)

ground_truth = {
    "pack_id": "greensmecapt_conference_demo_pack_v1",
    "purpose": "Fictional held-out demonstration and extraction evaluation pack",
    "document_routes": {
        "*_01_utility_bill_scanned.pdf": "Google Document AI OCR (image-only PDF)",
        "*_02_sustainability_report_text.pdf": "native PDF parsing followed by Gemini schema-guided extraction",
        "*_03_financial_and_funding_tables.pdf": "native PDF/table parsing followed by Gemini schema-guided extraction"
    },
    "companies": {
        "terra_pack": {
            "legal_name": terra["company"],
            "sector": "moulded recycled-fibre food packaging manufacturing",
            "authoritative_2025": {
                "electricity_consumption_kwh": terra["electricity"],
                "renewable_energy_share_percent": terra["renewable"],
                "water_consumption_m3": terra["water"],
                "ghg_emissions_tco2e": terra["ghg"],
                "waste_generated_kg": terra["waste"],
                "waste_diversion_percent": terra["diversion"],
                "revenue_aed": terra["revenue"],
                "net_profit_aed": terra["profit"],
                "total_assets_aed": terra["assets"],
                "current_assets_aed": terra["current_assets"],
                "current_liabilities_aed": terra["current_liabilities"],
                "operating_cash_flow_aed": terra["ocf"],
                "total_debt_aed": terra["debt"],
                "requested_amount_aed": terra["requested"],
                "project_cost_aed": terra["project_cost"],
                "expected_annual_savings_aed": terra["savings"]
            },
            "deliberate_conflict": {
                "indicator": "electricity_consumption_kwh",
                "utility_value": terra["electricity"],
                "narrative_value": terra["electricity_narrative"],
                "expected_resolution": "flag conflict; retain both source-linked claims pending review"
            },
            "out_of_schema_context": "1,250 m2 native planting",
            "incomplete_claim": "11 percent recycled-input increase without baseline year or boundary"
        },
        "blue_mesa": {
            "legal_name": blue["company"],
            "sector": "moulded paper-fibre packaging manufacturing",
            "authoritative_2025": {
                "electricity_consumption_kwh": blue["electricity"],
                "renewable_energy_share_percent": blue["renewable"],
                "water_consumption_m3": blue["water"],
                "ghg_emissions_tco2e": blue["ghg"],
                "waste_generated_kg": blue["waste"],
                "waste_diversion_percent": blue["diversion"],
                "revenue_aed": blue["revenue"],
                "net_profit_aed": blue["profit"],
                "total_assets_aed": blue["assets"],
                "current_assets_aed": blue["current_assets"],
                "current_liabilities_aed": blue["current_liabilities"],
                "operating_cash_flow_aed": blue["ocf"],
                "total_debt_aed": blue["debt"],
                "requested_amount_aed": blue["requested"],
                "project_cost_aed": blue["project_cost"],
                "expected_annual_savings_aed": blue["savings"]
            },
            "deliberate_conflict": {
                "indicator": "electricity_consumption_kwh",
                "utility_value": blue["electricity"],
                "narrative_value": blue["electricity_narrative"],
                "expected_resolution": "flag conflict; retain both source-linked claims pending review"
            },
            "out_of_schema_context": "38 employee suggestions; 14 trials",
            "incomplete_claim": "11 percent recycled-input increase without baseline year or boundary"
        }
    }
}
(OUT / "ground_truth.json").write_text(
    json.dumps(ground_truth, indent=2) + "\n",
    encoding="utf-8",
)
for item in sorted(OUT.glob("*.pdf")):
    print(item)

"""pytest configuration and shared fixtures with clean HTML."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest


# ── Sample HTML snippets (exact format from real DataTable response) ──

SAMPLE_ENTRY_COMPLETE = (
    '<button type="button" role="link" class="btn btn-link p-0 text-start" '
    'id="link_0" '
    'aria-label="WP/12923/2016 of M. SEENAPPA, CHITTOOR DIST AND 3 OTHERS '
    '.Array[93]. PRL SECY, ANIMAL HUSBANDRY DAIRY DEV. AND FISHERIES DEPT., '
    'HYD pdf" class="noToken" href="#" '
    'onclick=javascript:open_pdf(\'0\',\'\',\''
    'court/cnrorders/aphc/orders/APHC010460892016_1_2024-11-19.pdf'
    '#page=&search=%20\'); >'
    '<font size="3">WP/12923/2016 of M. SEENAPPA, CHITTOOR DIST AND 3 OTHERS '
    'Vs PRL SECY, ANIMAL HUSBANDRY DAIRY DEV. AND FISHERIES DEPT., HYD'
    '</button></font><br>'
    '<strong>Judge : TARLADA RAJASEKHAR RAO</strong><br>'
    ' ANDHRA PRADESH AT AMARAVATHI MAIN CASE: W.P.No.12923 of 2016 '
    'and C.C.No.3039 of 2024 PROCEEDING SHEET<br>'
    '<strong class="caseDetailsTD" >'
    '<span style="color:#212F3D"> CNR :</span>'
    '<font color="green"> APHC010460892016</font>'
    '<span style="color:#212F3D" > | Date of registration :</span>'
    '<font color="green"> 18-04-2016</font>'
    '<span style="color:#212F3D" > | Decision Date :</span>'
    '<font color="green"> 01-12-5000</font>'
    '<span style="color:#212F3D" > | Disposal Nature :</span>'
    '<font color="green"> DISPOSED OF NO COSTS</font><br>'
    '<span style="opacity: 0.5;">Court : High Court of Andhra Pradesh</span>'
    '</strong>'
)

SAMPLE_ENTRY_BOMBAY = (
    '<button type="button" role="link" class="btn btn-link p-0 text-start" '
    'id="link_0" '
    'aria-label="APPLN/4098/2025 of PRABHABAI PRAKSHRAO JOSHI AND OTHERS '
    '.Array[93]. THE STATE OF MAHARASHTRA AND ANOTHER pdf" '
    'class="noToken" href="#" '
    'onclick=javascript:open_pdf(\'0\',\'\',\''
    'court/cnrorders/hcaurdb/orders/HCBM030439682025_1_2025-12-23.pdf'
    '#page=&search=%20\'); >'
    '<font size="3">APPLN/4098/2025 of PRABHABAI PRAKSHRAO JOSHI AND OTHERS '
    'Vs THE STATE OF MAHARASHTRA AND ANOTHER</button></font><br>'
    '<strong>Judge : HONBLE SHRI JUSTICE SANDIPKUMAR C. MORE,'
    'HONBLE SHRI JUSTICE Y. G. KHOBRAGADE</strong><br>'
    'Bombay High Court<br>'
    '<strong class="caseDetailsTD" >'
    '<span style="color:#212F3D"> CNR :</span>'
    '<font color="green"> HCBM030439682025</font>'
    '<span style="color:#212F3D" > | Date of registration :</span>'
    '<font color="green"> 29-10-2025</font>'
    '<span style="color:#212F3D" > | Decision Date :</span>'
    '<font color="green"> 23-12-2025</font>'
    '<span style="color:#212F3D" > | Disposal Nature :</span>'
    '<font color="green"> DISPOSED OFF</font><br>'
    '<span style="opacity: 0.5;">Court : Bombay High Court</span>'
    '</strong>'
)

SAMPLE_ENTRY_MINIMAL = (
    '<button aria-label="Case ABC pdf" '
    'onclick="open_pdf(\'0\',\'\',\'some/path.pdf\');">'
    '<font>Case ABC</font></button><br>'
    '<strong>Judge : JUSTICE X</strong><br>'
    '<strong class="caseDetailsTD">'
    '<span style="color:#212F3D"> CNR :</span>'
    '<font color="green"> XXHC0000000000</font>'
    '<span style="color:#212F3D"> | Decision Date :</span>'
    '<font color="green"> 01-01-2024</font><br>'
    '<span style="opacity: 0.5;">Court : High Court of Test</span>'
    '</strong>'
)


@pytest.fixture
def sample_entry_complete():
    return SAMPLE_ENTRY_COMPLETE


@pytest.fixture
def sample_entry_bombay():
    return SAMPLE_ENTRY_BOMBAY


@pytest.fixture
def sample_entry_minimal():
    return SAMPLE_ENTRY_MINIMAL


@pytest.fixture
def sample_datatable_response():
    """Simulated JSON from the DataTable endpoint with 2 results."""
    return {
        "reportrow": {
            "sEcho": 1,
            "iTotalRecords": 17622456,
            "iTotalDisplayRecords": 17622456,
            "aaData": [
                [1, SAMPLE_ENTRY_COMPLETE],
                [2, SAMPLE_ENTRY_BOMBAY],
            ],
        },
        "app_token": "abc123token",
    }

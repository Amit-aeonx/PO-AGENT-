import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

BASE_URL = "https://dev.api.supplierx.aeonx.digital"
API_TOKEN = os.getenv("SUPPLIERX_API_TOKEN")
SESSION_KEY = os.getenv("SUPPLIERX_SESSION_KEY")

def test_create_po_direct():
    print("Preparing payload...")
    
    # Raw payload dictionary as provided by user
    payload = {
        "line_items[0].short_text": "Scooty",
        "line_items[0].quantity": "2",
        "line_items[0].unit_id": "208",
        "line_items[0].price": "2000",
        "line_items[0].subServices": "",
        "line_items[0].control_code": "",
        "line_items[0].delivery_date": "Fri Jan 23 2026 13:15:24 GMT+0530 (India Standard Time)",
        "line_items[0].material_id": "95942",
        "line_items[0].short_desc": "Testing",
        "line_items[0].sub_total": "4000.00",
        "line_items[0].tax_code": "118",
        "line_items[0].material_group_id": "520",
        "line_items[0].tax": "5",
        "total": "4200.00",
        "currency": "INR",
        "alternate_supplier_name": "demo12312",
        "alternate_supplier_email": "demo@gmail.com",
        "alternate_supplier_contact_number": "2222111222",
        "po_date": "Wed Dec 30 2025 13:15:12 GMT+0530 (India Standard Time)",
        "validityEnd": "Wed Dec 31 2025 00:00:00 GMT+0530 (India Standard Time)",
        "is_epcg_applicable": "false",
        "remarks": "Testing",
        "is_pr_based": "false",
        "is_rfq_based": "false",
        "projects[0].project_code": "P000219",
        "projects[0].project_name": "hiii demo k liye 4",
        "payment_terms": "189",
        "inco_terms": "13",
        "datasupplier": "",
        "inco_terms_description": "",
        "noc": "",
        "payment_terms_description": "",
        "plant_id": "25b8ef1f-b058-4d48-80d4-6eee943f4930",
        "po_type": "regularPurchase",
        "purchase_grp_id": "365",
        "purchase_org_id": "40",
        "vendor_id": "50eb8a01-0eae-4cf3-aa18-73f3c10f99d5"
    }

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "x-session-key": SESSION_KEY
    }

    # Convert to multipart format
    multipart_data = {}
    for k, v in payload.items():
        multipart_data[k] = (None, str(v))

    print(f"Sending PO directly to {BASE_URL}/api/v1/supplier/purchase-order/create")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/supplier/purchase-order/create",
            headers=headers,
            files=multipart_data
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_create_po_direct()

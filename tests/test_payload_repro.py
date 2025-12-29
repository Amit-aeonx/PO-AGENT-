
import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://dev.api.supplierx.aeonx.digital"
API_TOKEN = os.getenv("SUPPLIERX_API_TOKEN")
SESSION_KEY = os.getenv("SUPPLIERX_SESSION_KEY")

def format_payload_values(value):
    if isinstance(value, dict):
        return {k: format_payload_values(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [format_payload_values(v) for v in value]
    elif isinstance(value, bool):
        return str(value).lower()
    elif value is None:
        return ""
    return value

def flatten_payload(y):
    out = {}
    def flatten(x, name=''):
        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + '.')
        elif type(x) is list:
            i = 0
            for a in x:
                flatten(a, name[:-1] + '[' + str(i) + '].')
                i += 1
        else:
            out[name[:-1]] = x
    flatten(y)
    return out

def test_repro():
    # Exact payload reconstructed from User Logs + Agent Logic processing
    # Note: Agent adds missing fields like control_code during processing
    
    payload = {
        "po_type": "regularPurchase",
        "vendor_id": "a888ee02-b479-45ba-899b-40daba67d7d7",
        "purchase_org_id": 40,
        "plant_id": "25b8ef1f-b058-4d48-80d4-6eee943f4930",
        "purchase_grp_id": 365,
        "po_date": "2025-12-29",
        "validityEnd": "2025-12-31",
        "currency": "INR",
        "is_epcg_applicable": False,
        "remarks": "",
        "is_pr_based": False,
        "is_rfq_based": False,
        "noc": "", 
        "payment_terms": "",
        "inco_terms": "",
        "datasupplier": "",
        "inco_terms_description": "",
        "payment_terms_description": "",
        "alternate_supplier_name": "",
        "alternate_supplier_email": "",
        "alternate_supplier_contact_number": "",
        "line_items": [
            {
                "material_id": "95942", # STRING
                "quantity": "2", # STRING
                "price": "153", # STRING
                "short_text": "Scooty",
                "material_group_id": "520", # STRING
                "unit_id": "208", # STRING
                "tax_code": "118", # STRING
                
                # Added by Agent Logic
                "control_code": "",
                "subServices": "",
                "short_desc": "Scooty", # Propagated
                "sub_total": "306.0", # Calculated
                "tax": "0",
                "delivery_date": "2025-12-31" # Propagated
            }
        ],
        "projects": [],
        "total": "306"
    }

    # Prepare for sending
    cleaned = format_payload_values(payload)
    
    # mimic cleaning in agent_logic
    if "delivery_date" in cleaned: del cleaned["delivery_date"]
    
    flat = flatten_payload(cleaned)
    
    print(f"Sending keys: {list(flat.keys())}")
    
    multipart_data = {}
    for k, v in flat.items():
        multipart_data[k] = (None, str(v))
        
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "x-session-key": SESSION_KEY
    }
    
    try:
        resp = requests.post(
            f"{BASE_URL}/api/v1/supplier/purchase-order/create",
            headers=headers,
            files=multipart_data
        )
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")
    except Exception as e:
        print(e)
        
if __name__ == "__main__":
    test_repro()

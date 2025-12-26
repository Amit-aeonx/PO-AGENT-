import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://dev.api.supplierx.aeonx.digital"
API_TOKEN = os.getenv("SUPPLIERX_API_TOKEN")

class MockAPI: # Keeping class name same to avoid breaking agent_logic.py import
    def __init__(self):
        # Force reload .env to ensure we have the latest artifacts
        load_dotenv(override=True)
        
        token = os.getenv("SUPPLIERX_API_TOKEN")
        session_key = os.getenv("SUPPLIERX_SESSION_KEY")
        
        print(f"DEBUG: Initializing MockAPI")
        print(f"DEBUG: Token loaded: {bool(token)}")
        print(f"DEBUG: Session loaded: {bool(session_key)}")
        
        self.headers = {
            "Authorization": f"Bearer {token}",
            "x-session-key": session_key,
            "Content-Type": "application/json"
        }

    def _get(self, endpoint, params=None):
        try:
            url = f"{BASE_URL}{endpoint}"
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"API Error ({endpoint}): {e}")
            return []

    def _post(self, endpoint, payload):
        try:
            url = f"{BASE_URL}{endpoint}"
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Capture actual error response body
            error_body = ""
            try:
                error_body = response.json()
            except:
                error_body = response.text
            
            print(f"API Error ({endpoint}): {e}")
            print(f"Response Status: {response.status_code}")
            print(f"Response Body: {error_body}")
            
            # Return structured error with details
            return {
                "success": False, 
                "error": True,
                "message": str(e),
                "details": error_body
            }
        except Exception as e:
            print(f"API Error ({endpoint}): {e}")
            return {"success": False, "error": True, "message": str(e)}

    # --- Wrapper Methods matching the original Interface ---

    def get_po_main_types(self):
        return [
            "Independent PO",
            "PR-Based PO"
        ]

    def get_po_sub_types(self):
        return [
            "Asset",
            "Service",
            "Regular Purchase",
            "Internal Order Material",
            "Internal Order Service",
            "Network",
            "Network Service",
            "Cost Center Material",
            "Cost Center Service",
            "Project Service",
            "Project Material",
            "Stock Transfer Inter",
            "Stock Transfer Intra"
        ]

    def search_suppliers(self, query=None, limit=10):
        # API: /api/v1/supplier/supplier/sapRegisteredVendorsList
        # DIAGNOSTICS: Confirmed this is a POST request
        # Payload: {} or {"search": query}
        
        payload = {}
        if query:
            payload["search"] = query

        # DEBUG LOGGING
        print(f"DEBUG: Calling Supplier API [POST]")
        print(f"DEBUG: Headers Auth Present: {bool(self.headers.get('Authorization'))}")
        print(f"DEBUG: Session Key Present: {bool(self.headers.get('x-session-key'))}")
        
        data = self._post("/api/v1/supplier/supplier/sapRegisteredVendorsList", payload)
        print(f"DEBUG: Raw Response keys: {data.keys() if isinstance(data, dict) else 'Not a dict'}")
        if isinstance(data, dict) and "data" in data:
            print(f"DEBUG: 'data' field length: {len(data['data'])}")
        
        # Logic matches verifed test_supplier_list.py
        items = []
        if isinstance(data, dict) and "data" in data:
            items = data["data"]
        elif isinstance(data, list):
            items = data

        normalized = []
        for item in items:
            normalized.append({
                "vendor_id": str(item.get("id", "")),  # UUID for API - CRITICAL FIX
                "sap_code": str(item.get("sap_code", "")),  # SAP code for display
                "name": item.get("supplier_name", ""),
                "email": item.get("email", ""),
                "contact": item.get("contact_no", "")
            })
        
        if not query:
            return normalized[:limit]
        
        return normalized[:limit]
    
    def get_alternate_supplier_details(self, vendor_id):
        """Fetch alternate supplier contact details for a given vendor"""
        endpoint = f"/api/v1/supplier/supplier/additional-supplier-details/{vendor_id}"
        data = self._get(endpoint)
        
        # Extract first alternate supplier if available
        if isinstance(data, dict) and "data" in data:
            alt_suppliers = data["data"]
            if isinstance(alt_suppliers, list) and len(alt_suppliers) > 0:
                first_alt = alt_suppliers[0]
                return {
                    "alternate_supplier_name": first_alt.get("alternate_supplier_name", ""),
                    "alternate_supplier_email": first_alt.get("alternate_supplier_email", ""),
                    "alternate_supplier_contact_number": first_alt.get("alternate_supplier_contact_number", "")
                }
        
        # Return empty if no alternate supplier found
        return {
            "alternate_supplier_name": "",
            "alternate_supplier_email": "",
            "alternate_supplier_contact_number": ""
        }

    def get_purchase_orgs(self):
        # API: /api/v1/supplier/purchaseOrg/listing
        data = self._post("/api/v1/supplier/purchaseOrg/listing", {})
        
        # Helper to extract list from data -> data -> rows (or data -> data if list)
        if isinstance(data, dict) and "data" in data:
            raw = data["data"]
            if isinstance(raw, dict) and "rows" in raw:
                raw = raw["rows"]
        else:
            raw = data

        if not isinstance(raw, list): raw = []
            
        # Map: id -> id (int), description -> name
        # User Example: {"id": 67, "code": "99", "description": "All", ...}
        return [{"id": str(x.get("id", "")), "name": x.get("description", x.get("purchaseOrgName", ""))} for x in raw if isinstance(x, dict)]

    def get_purchase_groups(self, org_ids=None):
        # API: /api/v1/admin/purchaseGroup/list
        # Payload: {dropdown: "0", purchase_org_id: [40], user_id: ...}
        # Note: org_ids should be a list of ints.
        
        payload = {"dropdown": "0"}
        if org_ids:
             # Ensure list of ints
             if isinstance(org_ids, (str, int)): org_ids = [int(org_ids)]
             payload["purchase_org_id"] = org_ids
             # payload["user_id"] = 7391 # Optional? Let's try without forcing ID first or use session owner if known.
             # Diagnostics showed 200 OK with empty body. Let's assume auth header handles user context 
             # but payload filters.

        data = self._post("/api/v1/admin/purchaseGroup/list", payload)
        
        if isinstance(data, dict) and "data" in data:
            raw = data["data"]
            if isinstance(raw, dict) and "rows" in raw:
                raw = raw["rows"]
        else:
            raw = data
            
        if not isinstance(raw, list): raw = []

        # Mapping based on User provided JSON (id, code, name)
        # Example: {"id": 426, "code": "SF", "name": "Service Freight", ...}
        return [{"id": str(x.get("id", "")), "name": x.get("name", x.get("description", ""))} for x in raw if isinstance(x, dict)]

    def get_plants(self, org_ids=None):
        # API: /api/v1/admin/plants/list
        # Payload similar to groups likely
        
        payload = {"dropdown": "0"}
        if org_ids:
             if isinstance(org_ids, (str, int)): org_ids = [int(org_ids)]
             payload["purchase_org_id"] = org_ids

        data = self._post("/api/v1/admin/plants/list", payload)
        
        if isinstance(data, dict) and "data" in data:
            raw = data["data"]
            if isinstance(raw, dict) and "rows" in raw:
                raw = raw["rows"]
        else:
            raw = data
            
        if not isinstance(raw, list): raw = []

        return [{"id": str(x.get("id", x.get("plantCode"))), "name": x.get("plantName", x.get("name"))} for x in raw if isinstance(x, dict)]

    def get_currencies(self):
        # API: /api/v1/admin/currency/getWithoutSlug
        # DIAGNOSTIC UPDATE: User test script succeeded with POST.
        
        data = self._post("/api/v1/admin/currency/getWithoutSlug", {})
        
        # Check structure
        items = []
        if isinstance(data, dict) and "data" in data:
            items = data["data"]
        elif isinstance(data, list):
            items = data
            
        # Extract Code
        return [str(x.get("currencyCode", x.get("id", ""))) for x in items if isinstance(x, dict)]

    def get_payment_terms(self):
        # API: /api/admin/paymentTerms/list
        # Switch to POST
        data = self._post("/api/admin/paymentTerms/list", {}) # Payload often empty or dropdown:0
        
        # Robust Extraction
        if isinstance(data, dict) and "data" in data:
            raw = data["data"]
            if isinstance(raw, dict) and "rows" in raw: raw = raw["rows"]
        else: raw = data
        if not isinstance(raw, list): raw = []
        
        return [{"id": str(x.get("id", x.get("paymentTermCode"))), "name": x.get("description", x.get("name"))} for x in raw if isinstance(x, dict)]

    def get_incoterms(self):
        # API: /api/admin/IncoTerm/list
        # Switch to POST
        data = self._post("/api/admin/IncoTerm/list", {})
        
        # Robust Extraction
        if isinstance(data, dict) and "data" in data:
            raw = data["data"]
            if isinstance(raw, dict) and "rows" in raw: raw = raw["rows"]
        else: raw = data
        if not isinstance(raw, list): raw = []

        return [{"id": str(x.get("id", x.get("incoTermCode"))), "name": x.get("description", x.get("name"))} for x in raw if isinstance(x, dict)]

    def get_projects(self):
        # API: /api/v1/supplier/purchase-order/list-project
        # Switch to POST
        data = self._post("/api/v1/supplier/purchase-order/list-project", {})
        
        # Robust Extraction
        if isinstance(data, dict) and "data" in data:
            raw = data["data"]
            if isinstance(raw, dict) and "rows" in raw: raw = raw["rows"]
        else: raw = data
        if not isinstance(raw, list): raw = []

        return [{"project_code": str(x.get("projectCode", x.get("id"))), "project_name": x.get("projectName", x.get("name"))} for x in raw if isinstance(x, dict)]

    def get_materials(self, plant_id=None, query=None):
        # API: /api/v1/supplier/materials/list
        # Switch to POST
        payload = {}
        if query: payload["search"] = query
        
        data = self._post("/api/v1/supplier/materials/list", payload)
        
        # Robust Extraction
        if isinstance(data, dict) and "data" in data:
            raw = data["data"]
            if isinstance(raw, dict) and "rows" in raw: raw = raw["rows"]
        else: raw = data
        if not isinstance(raw, list): raw = []
        
        normalized = []
        for x in raw:
            if isinstance(x, dict):
                # User JSON: id=95948, code="453", name="CAP", unit={"code":"GM2"}
                # FIX: Use internal ID (int) as material_id, keep code for display
                mat_id = x.get("id") # Keep as original type (int)
                mat_code = str(x.get("code", ""))
                mat_name = x.get("name", x.get("description", ""))
                
                # Unit extraction
                unit_val = "EA"
                unit_id = 0
                if isinstance(x.get("unit"), dict):
                    unit_val = x["unit"].get("code", "EA")
                    unit_id = x["unit"].get("id", 0)
                elif isinstance(x.get("unit"), str):
                    unit_val = x["unit"]
                
                # Material Group extraction
                mat_grp_id = 0
                if isinstance(x.get("material_group"), dict):
                    mat_grp_id = x["material_group"].get("id", 0)
                
                # HSN extraction
                hsn_id = 0
                if isinstance(x.get("hsn_code"), dict):
                    hsn_id = x["hsn_code"].get("id", 0)

                normalized.append({
                    "id": mat_id,
                    "code": mat_code,
                    "name": mat_name,
                    "price": float(x.get("price", 0)),
                    "unit": unit_val,
                    "unit_id": unit_id,
                    "material_group_id": mat_grp_id,
                    "tax_code": 119, # Default as per user payload example, or ask
                    "hsn_id": hsn_id
                })

        if not query: return normalized
        # If API search worked, we trust it. If not, fallback filter? 
        # API search key "search" usually works.
        return normalized

    def get_services(self, query=None):
        # API: /api/supplier/services/list
        # Switch to POST
        payload = {}
        if query: payload["search"] = query
        
        data = self._post("/api/supplier/services/list", payload)
        
        if isinstance(data, dict) and "data" in data:
            raw = data["data"]
            if isinstance(raw, dict) and "rows" in raw: raw = raw["rows"]
        else: raw = data
        if not isinstance(raw, list): raw = []
        
        normalized = []
        for x in raw:
            if isinstance(x, dict):
                 normalized.append({
                    "id": str(x.get("id", x.get("serviceCode"))),
                    "name": x.get("serviceDescription", x.get("name")),
                    "price": float(x.get("price", 0)),
                    "unit": x.get("uom", "AU")
                })
        
        return normalized
    
    def get_tax_codes(self):
        # API: /api/v1/supplier/purchase-order/tax-code-dropdown
        # Found via diagnostics: It accepts POST (and GET?) but structure is complex
        data = self._post("/api/v1/supplier/purchase-order/tax-code-dropdown", {})
        
        # Structure: error, message, data -> rows -> other_tax_codes (list)
        items = []
        if isinstance(data, dict) and "data" in data:
            d = data["data"]
            if isinstance(d, dict) and "rows" in d:
                # Merge related and other? or just other
                rows = d["rows"]
                items.extend(rows.get("other_tax_codes", []))
                items.extend(rows.get("related_tax_codes", []))
        
        normalized = []
        for x in items:
            if isinstance(x, dict):
                normalized.append({
                    "id": str(x.get("id", x.get("code"))), 
                    "description": x.get("description", x.get("code")),
                    "rate": 0.0 # Not in response?
                })
        return normalized

    def _flatten_payload(self, y):
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

    def create_po(self, payload):
        # Flatten payload for Form-Data
        # Expected format: line_items[0].short_text = "..."
        
        # 1. Format Values (Recursively)
        # Convert bool -> "true"/"false", None -> ""
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

        cleaned_payload = format_payload_values(payload)
        
        flat_data = self._flatten_payload(cleaned_payload)
        
        # Convert to Multipart format (forces multipart/form-data header)
        multipart_data = {}
        for k, v in flat_data.items():
            multipart_data[k] = (None, str(v))
        
        # We need to send this as form-data
        # Remove Content-Type so requests adds the boundary automatically
        headers = self.headers.copy()
        if "Content-Type" in headers:
            del headers["Content-Type"]
            
        print(f"DEBUG: Sending Flattened Form Data keys: {list(flat_data.keys())}")
            
        try:
            url = f"{BASE_URL}/api/v1/supplier/purchase-order/create"
            # USE files=multipart_data to force multipart encoding
            response = requests.post(url, headers=headers, files=multipart_data)
            print("Create PO Status Code:", response.status_code)
            print("Create PO Raw Response:", response.text)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            # Capture response text if available
            err_msg = str(e)
            if 'response' in locals():
                try:
                    return response.json()
                except:
                    err_msg += f" | Body: {response.text}"
                    
            print(f"API Error (Create PO): {err_msg}")
            return {"success": False, "error": True, "message": err_msg}

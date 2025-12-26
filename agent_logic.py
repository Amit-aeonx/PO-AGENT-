from mock_api import MockAPI
from bedrock_service import BedrockService
import datetime
import json

# States
STATE_INIT = "INIT"
STATE_PO_TYPE = "PO_TYPE"
STATE_SUPPLIER = "SUPPLIER"
STATE_SUPPLIER_DETAILS = "SUPPLIER_DETAILS"
STATE_ORG_DETAILS = "ORG_DETAILS"
STATE_COMMERCIALS = "COMMERCIALS"
STATE_LINE_ITEMS_START = "LINE_ITEMS_START"
STATE_LINE_ITEM_DETAILS = "LINE_ITEM_DETAILS"
STATE_CONFIRM = "CONFIRM"
STATE_DONE = "DONE"

class POAgent:
    def __init__(self):
        self.api = MockAPI()
        self.nlu = BedrockService()
        
    def get_initial_state(self):
        return {
            "current_step": STATE_PO_TYPE,
            "payload": {
                "line_items": [],
                "projects": [{"project_code": "", "project_name": ""}],
                "currency": "INR",
                "alternate_supplier_name": "",
                "alternate_supplier_email": "",
                "alternate_supplier_contact_number": "",
                "validityEnd": "",
                "is_epcg_applicable": False,
                "remarks": "",
                "inco_terms_description": "",
                "payment_terms_description": "",
                "is_pr_based": False,
                "is_rfq_based": False,
                "noc": "No",
                "datasupplier": ""
            },
            "history": [],
            "temp_data": {}
        }

    def process_input(self, user_text, state):
        current_step = state["current_step"]
        payload = state["payload"]
        response_text = ""
        
        # 1. NLU Analysis
        nlu_result = self.nlu.analyze_intent(user_text, current_step)
        entities = nlu_result.get("entities", {})
        
        # 2. State Machine Logic
        
        # GLOBAL OVERRIDE: If User clicks "Create PO" button
        if "create po" in user_text.lower() or "create purchase order" in user_text.lower():
             print(f"DEBUG: Create PO triggered. Line items count: {len(payload.get('line_items', []))}")
             
             if payload.get("line_items"):
                 # Trigger Create
                 # 1. Final Payload Polish
                 payload["total"] = sum(float(x.get("total_value", x.get("sub_total", 0))) for x in payload["line_items"])
                 
                 print(f"DEBUG: Calculated total: {payload['total']}")
                 
                 # 2. Transform payload for API
                 api_payload = payload.copy()
                 # DO NOT Rename to lineItems - User confirmed line_items is expected
                 # api_payload["lineItems"] = api_payload.pop("line_items") 
                 
                 # REMOVE EXTRA FIELDS removed - User requests all fields be sent even if empty
                 # keys_to_remove = [
                 #     "alternate_supplier_name", 
                 #     "alternate_supplier_email", 
                 #     "alternate_supplier_contact_number",
                 #     "inco_terms_description",
                 #     "payment_terms_description"
                 # ]
                 # for k in keys_to_remove:
                 #     api_payload.pop(k, None)
                     
                 # Clean Line Items
                 if "line_items" in api_payload:
                     for item in api_payload["line_items"]:
                         item.pop("short_desc", None)
                         # Force subServices to empty string as per user "Correct" JSON
                         item["subServices"] = ""
                         # Force control_code to empty string as per user "Correct" JSON
                         item["control_code"] = ""
                         
                         # Ensure all line item fields from user example are present
                         if "short_desc" not in item: item["short_desc"] = item.get("short_text", "")
                 
                 print(f"DEBUG: Sending payload keys: {list(api_payload.keys())}")
                 print(f"DEBUG: Line Items: {json.dumps(api_payload.get('line_items', []), indent=2)}")
                 
                 # 3. API Call
                 api_resp = self.api.create_po(api_payload)
                 
                 print(f"DEBUG: API Response keys: {api_resp.keys() if isinstance(api_resp, dict) else 'Not a dict'}")
                 print(f"DEBUG: Full Response: {str(api_resp)[:300]}")
                 
                 # Check success - handle both error:false and success:true
                 is_success = (api_resp.get("error") == False or api_resp.get("success") == True)
                 
                 if is_success:
                     po_num = api_resp.get("po_number", api_resp.get("data", {}).get("po_number", "Created"))
                     response_text = f"✅ **Success!** Purchase Order created.\n\n**PO Number:** {po_num}\n\n[Ref ID: {api_resp.get('id', 'N/A')}]"
                     state["current_step"] = STATE_DONE
                 else:
                     msg = api_resp.get("message", "Unknown Error")
                     
                     # Extract SAP errors from data array
                     if isinstance(api_resp.get("data"), list):
                         sap_errors = [d.get("msg", "") for d in api_resp["data"] if d.get("type") == "E"]
                         if sap_errors:
                             msg = "SAP Errors: " + " | ".join(sap_errors)
                     
                     response_text = f"❌ **Submission Failed**\n\nError: {msg}\n\nResponse: {str(api_resp)[:400]}"
                 
                 print(f"DEBUG: Returning response: {response_text[:100]}")
                 return response_text
             else:
                 return "You cannot create a PO without line items."
        
        if current_step == STATE_PO_TYPE:
            # Check if user provided PO Type info
            po_sub_type = entities.get("po_sub_type")
            
            # Simple keyword matching fallback if NLU fails or is generic
            if not po_sub_type:
                lower_text = user_text.lower()
                for pt in self.api.get_po_sub_types():
                    if pt.lower() in lower_text:
                        po_sub_type = pt
                        break
            
            if po_sub_type:
                # MAP DISPLAY NAME TO INTERNAL CODE (camelCase)
                po_type_map = {
                    "Regular Purchase": "regularPurchase",
                    "Service": "service",
                    "Asset": "asset",
                    "Internal Order Material": "internalOrderMaterial",
                    "Internal Order Service": "internalOrderService",
                    "Network": "network",
                    "Network Service": "networkService",
                    "Cost Center Material": "costCenterMaterial",
                    "Cost Center Service": "costCenterService",
                    "Project Service": "projectService",
                    "Project Material": "projectMaterial",
                    "Stock Transfer Inter": "stockTransferInter",
                    "Stock Transfer Intra": "stockTransferIntra"
                }
                payload["po_type"] = po_type_map.get(po_sub_type, "regularPurchase")
                payload["is_pr_based"] = entities.get("is_pr_based", False)
                state["current_step"] = STATE_SUPPLIER
                response_text = f"Selected PO Type: **{po_sub_type}**. \n\nNow, please select a **Supplier**. \nHere are the top suppliers:"
            else:
                response_text = "Please select a valid PO Type (e.g., 'Regular Purchase', 'Service', 'Asset')."

        elif current_step == STATE_SUPPLIER:
            supplier_name = entities.get("supplier_name") or user_text
            
            # Search API
            results = self.api.search_suppliers(query=supplier_name, limit=1)
            
            if results:
                selected_supplier = results[0]
                payload["vendor_id"] = selected_supplier["vendor_id"]
                
                # Fetch alternate supplier details from API
                alt_details = self.api.get_alternate_supplier_details(selected_supplier["vendor_id"])
                payload["alternate_supplier_name"] = alt_details["alternate_supplier_name"]
                payload["alternate_supplier_email"] = alt_details["alternate_supplier_email"]
                payload["alternate_supplier_contact_number"] = alt_details["alternate_supplier_contact_number"]
                
                # Fetch Currency automatically
                curr_list = self.api.get_currencies()
                payload["currency"] = curr_list[0] if curr_list else "INR" 
                
                state["current_step"] = STATE_SUPPLIER_DETAILS
                response_text = f"Selected Supplier: **{selected_supplier['name']}** ({selected_supplier['vendor_id']}). \n\nCurrency set to **{payload['currency']}**.\n\nPlease provide the **PO Date** (YYYY-MM-DD) and **Validity End Date**."
            else:
                response_text = f"I couldn't find a supplier matching '{supplier_name}'. Please try searching again (e.g., 'Tata', 'Infosys')."

        elif current_step == STATE_SUPPLIER_DETAILS:
            # Extract dates - CLEAN PARSING
            import re
            
            # Expected format: "PO Date: YYYY-MM-DD, Validity: YYYY-MM-DD"
            # OR simple text input: "2025-12-21"
            
            po_match = re.search(r'PO Date: (\d{4}-\d{2}-\d{2})', user_text)
            val_match = re.search(r'Validity: (\d{4}-\d{2}-\d{2})', user_text)
            
            # Fallback for simple typing
            simple_date = re.search(r'(\d{4}-\d{2}-\d{2})', user_text)
            
            clean_po_date = None
            if po_match:
                clean_po_date = po_match.group(1)
            elif simple_date:
                clean_po_date = simple_date.group(1)
                
            clean_validity = "2025-12-31" # Default
            if val_match:
                clean_validity = val_match.group(1)
            elif entities.get("validity_date"):
                clean_validity = entities.get("validity_date")

            if clean_po_date:
                payload["po_date"] = clean_po_date
                payload["validityEnd"] = clean_validity
                
                state["current_step"] = STATE_ORG_DETAILS
                response_text = f"PO Date set to {clean_po_date}. \n\nNow, please select the **Purchase Organization**, **Plant**, and **Purchase Group**."
            else:
                response_text = "Please provide a valid PO Date (YYYY-MM-DD format, e.g., 2025-12-21)."

        elif current_step == STATE_ORG_DETAILS:
            # Extraction
            p_org = entities.get("purchase_org")
            plant = entities.get("plant")
            p_grp = entities.get("purchase_group")
            
            # Mapping logic (simplified for Hackathon/Demo speed)
            # If NLU picked them up, great. If not, auto-select first ones for demo flow if user says "First one" or "Default"
            # Or enforce strictness. Let's try to map from text.
            
            # Mock mapping logic:
            if not payload.get("purchase_org_id") and p_org:
                # Find ID
                pass # Logic to match name to ID
            
            # For robustness in this demo, let's assume we set defaults if text is vague, or map strictly if specific.
            # Let's just set the IDs if we find loose matches in text, or ask again.
            
            # AUTO-RESOLVER - Use regex to extract exact IDs from structured message
            # Expected format: "Selected: Purchase Org 40, Plant 25b8ef1f..., Group 365"
            import re
            
            # Extract IDs using regex patterns
            org_match = re.search(r'Purchase Org (\d+)', user_text)
            plant_match = re.search(r'Plant ([a-f0-9\-]+)', user_text)
            group_match = re.search(r'Group (\d+)', user_text)
            
            if org_match:
                payload["purchase_org_id"] = int(org_match.group(1))
            if plant_match:
                payload["plant_id"] = plant_match.group(1)
            if group_match:
                payload["purchase_grp_id"] = int(group_match.group(1))
            
            # Check if we have all 3
            missing = []
            if "purchase_org_id" not in payload: missing.append("Purchase Org")
            if "plant_id" not in payload: missing.append("Plant")
            if "purchase_grp_id" not in payload: missing.append("Purchase Group")
            
            if not missing:
                state["current_step"] = STATE_COMMERCIALS
                response_text = f"Organization details set. (Org: {payload['purchase_org_id']}, Plant: {payload['plant_id']}, Grp: {payload['purchase_grp_id']}).\n\nNow, please provide **Project**, **Payment Terms**, and **Incoterms**."
            else:
                response_text = f"I identified: {', '.join([k for k in ['purchase_org_id','plant_id','purchase_grp_id'] if k in payload])}. \n\nPlease specify the missing: **{', '.join(missing)}**."

        elif current_step == STATE_COMMERCIALS:
            # Similar extraction
            proj = entities.get("project")
            pay = entities.get("payment_terms")
            inco = entities.get("incoterms")
            remarks = entities.get("remarks")
            
            # Set defaults for demo if missing, but ideally ask
            # Assume user input "Project 001, Pay immediately, CIF"
            
            # Search Lists
            all_projects = self.api.get_projects()
            all_pay = self.api.get_payment_terms()
            all_inco = self.api.get_incoterms()
            
            if proj:
                # Match code or name
                p_obj = next((x for x in all_projects if proj.lower() in x["project_name"].lower() or proj in x["project_code"]), None)
                if p_obj: 
                    payload["projects"][0]["project_code"] = p_obj["project_code"]
                    payload["projects"][0]["project_name"] = p_obj["project_name"]
            
            # Fallback for Project
            if not payload["projects"][0]["project_code"]:
                 if all_projects:
                     # Pick first valid project for demo flow
                     p0 = all_projects[0]
                     payload["projects"][0]["project_code"] = p0["project_code"]
                     payload["projects"][0]["project_name"] = p0["project_name"]
                 else:
                     payload["projects"][0]["project_code"] = "P01"
                     payload["projects"][0]["project_name"] = "Default Helper"

            # Payment Terms ID (Int)
            valid_pay_id = 1
            if all_pay:
                # Try to find match if user text has "Immediate" etc
                # for now default to first for valid submission
                # Ensure we parse ID as int
                try: 
                    valid_pay_id = int(all_pay[0]["id"])
                except: pass
            payload["payment_terms"] = valid_pay_id
            
            # Inco Terms ID (Int)
            valid_inco_id = 1
            if all_inco:
                try:
                    valid_inco_id = int(all_inco[0]["id"])
                except: pass
            payload["inco_terms"] = valid_inco_id
            
            payload["remarks"] = remarks if remarks else "Created via AI Agent"
            
            state["current_step"] = STATE_LINE_ITEMS_START
            response_text = f"Commercials captured (PayTerm:{valid_pay_id}, Inco:{valid_inco_id}). \n\nLet's add Line Items. "
            
            # Auto-transition logic
            if payload.get("po_type") == "Regular Purchase":
                response_text += "Since this is a **Regular Purchase**, please search for a **Material** (e.g., 'Steel', 'Cement')."
            else:
                response_text += "Please provided the **Service** description."
                
            state["current_step"] = STATE_LINE_ITEM_DETAILS
            state["temp_data"] = {"new_item": {}}

        elif current_step == STATE_LINE_ITEM_DETAILS:
             # This is a repeatable loop
             item = state["temp_data"].get("new_item", {})
             is_regular = payload.get("po_type") == "Regular Purchase"
             
             # Extract item details
             mat_name = entities.get("material_name")
             srv_name = entities.get("service_name")
             qty = entities.get("quantity")
             price = entities.get("price")
             
             # 1. Identify Material/Service
             if is_regular and not item.get("material_id"):
                 # Search Material
                 query = mat_name or user_text
                 mat_results = self.api.get_materials(query=query)
                 if mat_results:
                     found = mat_results[0]
                     item["material_id"] = found["id"]
                     item["short_text"] = found["name"]
                     item["unit_id"] = int(found["unit_id"])
                     item["price"] = float(found["price"]) 
                     # Store extra metadata
                     item["material_group_id"] = int(found["material_group_id"])
                     item["tax_code"] = int(found["tax_code"])
                     response_text = f"Found **{found['name']}**. "
                 else:
                     return "Could not find that material. Please try 'Steel' or 'Cement'."
             
             elif not is_regular and not item.get("short_text"):
                 item["short_text"] = srv_name or user_text
                 item["material_id"] = "" # No material ID for services usually
                 response_text = f"Added Service: **{item['short_text']}**. "

             # 2. Update Quantity / Price if provided
             if qty: item["quantity"] = float(qty)
             if price: item["price"] = float(price)
             
             # Check completeness
             needed = []
             if not item.get("quantity"): needed.append("Quantity")
             if not item.get("price") and not item.get("material_id"): needed.append("Price") # Mat usually has price
             
             if needed:
                 response_text += f"\nPlease provide: **{', '.join(needed)}**."
                 state["temp_data"]["new_item"] = item
             else:
                 # Calculate totals
                 # FIX: Quantity should be int if whole number? API might accept float. 
                 # User working payload has int. Let's force int if matches.
                 qty_val = float(item.get("quantity", 0))
                 if qty_val.is_integer(): qty_val = int(qty_val)
                 item["quantity"] = qty_val
                 
                 price_val = float(item.get("price", 0))
                 item["sub_total"] = qty_val * price_val
                 
                 # Tax 
                 # Use stored values or defaults matching working JSON
                 if "tax_code" not in item: item["tax_code"] = 118 # Default from working JSON
                 if "material_group_id" not in item: item["material_group_id"] = 520 # Default
                 
                 # Calculate tax
                 item["tax"] = 12 # Hardcoded/Mock tax amount logic
                 item["total_value"] = item["sub_total"] + item["tax"]
                 
                 # Delivery Date
                 # Use PO Date + 7 days or just PO Date?
                 # Working JSON has delivery_date "2025-12-23" (PO Date was Dec 16 -> +7 days)
                 start_date = payload.get("po_date", "2025-12-16")
                 try:
                     import datetime
                     dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                     res_dt = dt + datetime.timedelta(days=7)
                     item["delivery_date"] = res_dt.strftime("%Y-%m-%d")
                 except:
                     item["delivery_date"] = start_date
                 
                 # item["material_group_id"] is set above
                 
                 # Add to main payload
                 payload["line_items"].append(item)
                 
                 # Calculate Grand Total
                 total = sum([x["sub_total"] for x in payload["line_items"]])
                 payload["total"] = total
                 
                 state["current_step"] = STATE_CONFIRM
                 response_text = f"Added Item: {item['short_text']} (Qty: {qty_val}, Total: {item['sub_total']}).\n\nDo you want to **add another item** or **Create PO**?"
                 state["temp_data"] = {} # Clear temp

        elif current_step == STATE_CONFIRM:
            if "add" in user_text.lower() or "another" in user_text.lower():
                 state["current_step"] = STATE_LINE_ITEM_DETAILS
                 state["temp_data"] = {"new_item": {}}
                 
                 if payload.get("po_type") == "Regular Purchase":
                     response_text = "Okay, search for the next **Material**."
                 else:
                     response_text = "Okay, describe the next **Service**."
            elif "create" in user_text.lower() or "yes" in user_text.lower():
                # Trigger Create
                api_resp = self.api.create_po(payload)
                if api_resp["success"]:
                    response_text = f"✅ **Success!** Purchase Order created.\n\n**PO Number:** {api_resp['po_number']}"
                    state["current_step"] = STATE_DONE
                else:
                    response_text = f"❌ Error: {api_resp['message']}"
            else:
                 response_text = "Please say 'Create' to finalize or 'Add item' to continue."

        return response_text

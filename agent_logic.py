from mock_api import MockAPI
from bedrock_service import BedrockService
import datetime
import json
import re


# Conversational States
STATE_ACTIVE = "ACTIVE"
STATE_DONE = "DONE"

class POAgent:
    def __init__(self):
        self.api = MockAPI()
        self.nlu = BedrockService()
        
    def get_initial_state(self):
        return {
            "current_step": STATE_ACTIVE,
            "payload": {
                "line_items": [],
                "projects": [],
                "currency": "INR", # Default
                "is_epcg_applicable": False,
                "remarks": "",
                "is_pr_based": False,
                "is_rfq_based": False,
                "noc": "No"
            },
            "conversation_history": [],
            "last_analysis": None
        }

    def identify_missing_fields(self, payload):
        """Identify which mandatory fields are still missing"""
        missing = []
        if not payload.get("po_type"): missing.append("po_type (e.g. Regular Purchase)")
        if not payload.get("vendor_id"): missing.append("supplier")
        if not payload.get("purchase_org_id"): missing.append("purchase organization")
        if not payload.get("plant_id"): missing.append("plant")
        
        # Check purchase group (handle alias)
        if not payload.get("purchase_grp_id") and not payload.get("purchase_group_id"):
             missing.append("purchase group")
             
        if not payload.get("po_date"): missing.append("PO Date")
        
        # Check validity end (handle common key variations)
        if not payload.get("validityEnd") and not payload.get("validity_end") and not payload.get("validity_end_date"):
            missing.append("validity end date")
            
        if not payload.get("currency"): missing.append("currency")
            
        if not payload.get("line_items") or len(payload["line_items"]) == 0:
            missing.append("at least one line item")
        else:
            # Check items
            for i, item in enumerate(payload["line_items"]):
                if not item.get("material_id") and not item.get("short_text"):
                    missing.append(f"item {i+1} material")
                if not item.get("quantity"):
                    missing.append(f"item {i+1} quantity")
                if not item.get("price") and not item.get("net_price"):
                    missing.append(f"item {i+1} price")
        
        return missing

    def process_input(self, user_text, state):
        current_payload = state["payload"]
        
        # 1. Analyze User Input
        print(f"DEBUG: Analyzing input: {user_text}")
        try:
            analysis = self.nlu.analyze_user_input(user_text, current_payload, state["conversation_history"])
        except Exception as e:
            print(f"Analysis Error: {e}")
            return "I encountered an error analyzing your request. Please try again."

        print(f"DEBUG: Analysis Result: {json.dumps(analysis, indent=2)}")
        
        intents = analysis.get("intents", [])
        actions = analysis.get("actions", [])
        to_resolve = analysis.get("items_to_resolve", [])
        
        execution_results = []
        state["last_analysis"] = analysis
        
        # 2. Resolve Entities
        resolution_map = self._resolve_entities(to_resolve, current_payload)
        for term, res in resolution_map.items():
            if res["found"]:
                # Log success
                pass
            else:
                execution_results.append(f"Note: Could not find '{term}' in the database.")
                
        # 3. Apply Actions
        for action in actions:
            try:
                msg = self._apply_action(current_payload, action, resolution_map)
                if msg: execution_results.append(msg)
            except Exception as e:
                execution_results.append(f"Failed to update {action.get('field_path')}: {str(e)}")
                print(f"Action Error: {e}")

        # Recalculate totals if line items changed
        if any("line_item" in a.get("field_path", "") for a in actions):
            try:
                total = sum(float(i.get("quantity", 0)) * float(i.get("price", 0)) for i in current_payload.get("line_items", []))
                current_payload["total"] = total
            except:
                pass

        # 4. Handle Special Intents
        final_response_override = None
        
        if "CANCEL_PO" in intents:
            state["payload"] = self.get_initial_state()["payload"]
            execution_results.append("Conversation reset.")
            final_response_override = "I've cancelled the current PO and reset the form. What ID you like to do?"
            
        elif "CONFIRM_PO" in intents:
            # 0. SELF-HEAL: Fix common data issues before validation
            # Fix Material ID if it ended up in short_text
            for item in current_payload.get("line_items", []):
                s_text = str(item.get("short_text", ""))
                if not item.get("material_id") and s_text.isdigit():
                    item["material_id"] = int(s_text)
                    item["short_text"] = f"Material {s_text}" # Temp description
            
            # Fix Purchase Group key alias in main payload
            if "purchase_group_id" in current_payload and not current_payload.get("purchase_grp_id"):
                 current_payload["purchase_grp_id"] = current_payload.pop("purchase_group_id")
            
            # Map PO Type to API format
            pt = current_payload.get("po_type", "")
            if pt.lower() == "regular purchase":
                current_payload["po_type"] = "regularPurchase"

            # 1. Identify Missing Fields
            missing = self.identify_missing_fields(current_payload)
            
            if not missing:
                # 2. CONSTRUCT STRICT PAYLOAD (Whitelist approach)
                
                # Helper for Date Format: "Fri Jan 23 2026 13:15:24 GMT+0530 (India Standard Time)"
                def format_date_api(date_val):
                    if not date_val: return ""
                    try:
                        # Try parsing YYYY-MM-DD
                        dt = datetime.datetime.strptime(str(date_val).split(" ")[0], "%Y-%m-%d")
                        # Set a default time if none (using fixed time from example or current)
                        # User example has 13:15:24. Let's use current time 
                        now = datetime.datetime.now()
                        dt = dt.replace(hour=now.hour, minute=now.minute, second=now.second)
                        # Hardcoded timezone part as per user requirement to match "correct" payload
                        return dt.strftime(f"%a %b %d %Y %H:%M:%S GMT+0530 (India Standard Time)")
                    except:
                        return str(date_val) # Fallback

                allowed_header_keys = [
                    "po_type", "vendor_id", "purchase_org_id", "plant_id", "purchase_grp_id",
                    "po_date", "validityEnd", "currency", "line_items", "projects",
                    "is_epcg_applicable", "remarks", "is_pr_based", "is_rfq_based", "noc",
                    "total", "payment_terms", "inco_terms", "datasupplier", "inco_terms_description",
                    "payment_terms_description", "alternate_supplier_name", 
                    "alternate_supplier_email", "alternate_supplier_contact_number"
                ]
                
                api_payload = {}
                for key in allowed_header_keys:
                    val = current_payload.get(key)
                    
                    # Date Formatting
                    if key in ["po_date", "validityEnd"] and val:
                        val = format_date_api(val)
                    
                    # Handle Boolean/None defaults
                    if key not in ["line_items", "projects"]:
                         if val is None:
                             api_payload[key] = ""
                         elif isinstance(val, bool):
                             api_payload[key] = val # Sent as bool, mock_api will stringify
                         else:
                             api_payload[key] = val
                    elif key in current_payload:
                        api_payload[key] = val

                # Fix 'noc' if it is "No" -> ""
                if api_payload.get("noc") == "No":
                    api_payload["noc"] = ""
                    
                # Ensure Defaults for critical fields
                if "projects" not in api_payload: api_payload["projects"] = []
                # Projects cleanup
                clean_projects = []
                for p in api_payload.get("projects", []):
                    clean_projects.append({
                        "project_code": p.get("project_code", ""),
                        "project_name": p.get("project_name", "")
                    })
                if clean_projects:
                    api_payload["projects"] = clean_projects
                
                # Payment Terms & Inco Terms defaults (from user example)
                if not api_payload.get("payment_terms"): api_payload["payment_terms"] = "189" 
                if not api_payload.get("inco_terms"): api_payload["inco_terms"] = "13"

                # 3. CLEAN LINE ITEMS
                clean_items = []
                header_del_date = current_payload.get("delivery_date")
                
                total_sum = 0.0
                
                for item in api_payload.get("line_items", []):
                    # Ensure numeric types
                    try: mat_grp = int(item.get("material_group_id", 1)) 
                    except: mat_grp = 1
                    try: u_id = int(item.get("unit_id", 1))
                    except: u_id = 1
                    try: tax_c = int(item.get("tax_code", 118)) # User example defaulted to 118
                    except: tax_c = 118
                    try: m_id = int(item.get("material_id"))
                    except: m_id = 0
                    
                    qty = float(item.get("quantity", 0))
                    price = float(item.get("price", 0))
                    item_total = qty * price
                    total_sum += item_total

                    clean_item = {
                        "material_id": m_id,
                        "quantity": str(qty).rstrip("0").rstrip(".") if qty.is_integer() else str(qty),
                        "price": str(price).rstrip("0").rstrip(".") if price.is_integer() else str(price),
                        "short_text": str(item.get("short_text", "") or "Item"),
                        "material_group_id": mat_grp,
                        "unit_id": u_id,
                        "tax_code": tax_c,
                        "control_code": "",
                        "subServices": "",
                        "short_desc": str(item.get("short_text", "") or "Item"),
                        "sub_total": f"{item_total:.2f}",
                        "tax": str(item.get("tax", "5")), # Defaulting to 5 as per example
                        "delivery_date": format_date_api(item.get("delivery_date") or header_del_date)
                    }
                    clean_items.append(clean_item)
                
                api_payload["line_items"] = clean_items
                
                # 2.1 Final Total Calculation
                api_payload["total"] = f"{total_sum:.2f}"
                
                print(f"DEBUG: Submitting PO: {json.dumps(api_payload, indent=2)}")
                result = self.api.create_po(api_payload)
                
                if result.get("success") or result.get("po_number"):
                    po_num = result.get("po_number", "Created")
                    execution_results.append(f"SUCCESS: PO Created! Number: {po_num}")
                    state["current_step"] = STATE_DONE
                else:
                    err_msg = result.get("message", "Unknown Error")
                    if "unexpected field" in str(result) or "extra fields" in str(result):
                        err_msg += " (API Validation Error: The backend rejected the data format.)"
                    if "data" in result and isinstance(result["data"], list):
                         sap_errs = [d.get("msg") for d in result["data"] if d.get("type") == "E"]
                         if sap_errs: err_msg = "; ".join(sap_errs)
                    execution_results.append(f"ERROR: Submission Failed. {err_msg}")
            else:
                execution_results.append(f"Validation Failed: Missing fields {', '.join(missing)}")

        # 5. Generate Response
        if final_response_override:
            response = final_response_override
        else:
            missing_fields = self.identify_missing_fields(current_payload)
            response = self.nlu.generate_response(user_text, analysis, execution_results, current_payload, missing_fields)
        
        # Update History
        state["conversation_history"].append({"role": "user", "content": user_text})
        state["conversation_history"].append({"role": "assistant", "content": response})
        
        return response

    def _resolve_entities(self, to_resolve, current_payload):
        """
        Resolve entity text to IDs using MockAPI.
        Returns: {"Original Text": {"found": True, "id": 123, "details": {...}}}
        """
        results = {}
        
        # Pre-scan for Purchase Org to help dependent lookups (Plant, Group)
        temp_org_id = current_payload.get("purchase_org_id")
        
        # 1. Resolve Purchase Org First
        for item in to_resolve:
            kind = item.get("entity_type", "").lower()
            text = item.get("value")
            if "org" in kind or "organization" in kind:
                try:
                    matches = self.api.get_purchase_orgs()
                    found = self._fuzzy_match(text, matches)
                    if found:
                        temp_org_id = int(found["id"])
                        print(f"DEBUG: Pre-resolved Org '{text}' -> {temp_org_id}")
                except: pass

        # 2. Resolve Others
        for item in to_resolve:
            text = item.get("value")
            kind = item.get("entity_type", "").lower()
            if not text: continue
            
            print(f"DEBUG: Resolving entity '{kind}': {text}")
            
            res = {"found": False, "id": None, "details": None}
            
            try:
                if "supplier" in kind:
                    # Search Supplier
                    matches = self.api.search_suppliers(query=text)
                    if matches:
                        res = {"found": True, "id": matches[0]["vendor_id"], "details": matches[0]}
                
                elif "material" in kind:
                    matches = self.api.get_materials(query=text)
                    if matches:
                        match = matches[0]
                        res = {"found": True, "id": int(match["id"]), "details": match}
                
                elif "plant" in kind:
                    # Use pre-resolved org ID if available
                    matches = self.api.get_plants(org_ids=[temp_org_id] if temp_org_id else None)
                    found = self._fuzzy_match(text, matches)
                    if found:
                        res = {"found": True, "id": found["id"], "details": found}
                    else:
                         print(f"DEBUG: Plant '{text}' not found in {len(matches)} candidates (Org: {temp_org_id})")

                elif "org" in kind or "organization" in kind:
                    # Already tried, but run again to populate results map
                    matches = self.api.get_purchase_orgs()
                    found = self._fuzzy_match(text, matches)
                    if found:
                        res = {"found": True, "id": int(found["id"]), "details": found}
                        
                elif "group" in kind or "purch" in kind: # catch 'purchase group' or 'group'
                    matches = self.api.get_purchase_groups(org_ids=[temp_org_id] if temp_org_id else None)
                    found = self._fuzzy_match(text, matches)
                    if found:
                            res = {"found": True, "id": int(found["id"]), "details": found}
                    else:
                         print(f"DEBUG: Group '{text}' not found in {len(matches)} candidates")

            except Exception as e:
                print(f"Error resolving {kind} '{text}': {e}")
            
            results[str(text).strip().lower()] = res
        return results

    def _fuzzy_match(self, text, candidates):
        """Helper to match text against name/id in a list of dicts"""
        text = str(text).lower().strip()
        # 1. Extract ID match
        for cand in candidates:
            if str(cand.get("id")).lower() == text:
                return cand
        # 2. Substring match
        for cand in candidates:
            if text in cand.get("name", "").lower():
                return cand
        # 3. All words match
        words = text.replace("-", " ").split()
        for cand in candidates:
            c_name = cand.get("name", "").lower()
            if all(w in c_name for w in words):
                return cand
        return None

    def _apply_action(self, payload, action, resolution_map):
        op = action.get("operation", "").upper()
        path = action.get("field_path", "")
        raw_val = action.get("value")
        
        # Field Aliases
        ALIASES = {
            "supplier": "vendor_id",
            "vendor": "vendor_id",
            "val_end_date": "validityEnd",
            "validity_end": "validityEnd",
            "purchase_org": "purchase_org_id",
            "organization": "purchase_org_id",
            "org": "purchase_org_id",
            "plant": "plant_id",
            "purchase_group": "purchase_grp_id",
            "purchase_group_id": "purchase_grp_id", # Fix common alias
            "group": "purchase_grp_id",
            "material": "material_id",
            "currency": "currency",
            "po_date": "po_date"
        }
        
        # Normalize Path using Aliases
        # Handle indexed paths like line_items[0].material
        base_key = path
        idx_str = ""
        if "[" in path and "]" in path:
            base_key = path.split("[")[0] # e.g. line_items
            remainder = path.split("]")[1] # e.g. .material
            idx_str = path[path.find("["):path.find("]")+1] # e.g. [0]
            if remainder.startswith("."):
                sub_key = remainder[1:]
                if sub_key in ALIASES:
                    path = f"{base_key}{idx_str}.{ALIASES[sub_key]}"
        elif path in ALIASES:
            path = ALIASES[path]
            
        print(f"DEBUG: Action {op} on {path} with val '{raw_val}'")

        # 1. Substitute Value if Resolved
        val = raw_val
        is_resolved = False
        
        # Special normalization for PO Type
        if path == "po_type" and isinstance(val, str):
            if val.lower() == "regular purchase":
                val = "regularPurchase"
            elif val.lower() == "service po" or val.lower() == "service":
                val = "service"
        
        # Check explicit resolution (case-insensitive lookup)
        if isinstance(raw_val, str):
            lookup_key = raw_val.strip().lower()
            if lookup_key in resolution_map and resolution_map[lookup_key]["found"]:
                val = resolution_map[lookup_key]["id"]
                is_resolved = True
                print(f"DEBUG: Resolved '{raw_val}' to ID {val}")
        
        # 2. Logic to map resolved objects (like Material) to multiple fields
        # If we found a material, we shouldn't just set 'material_id', we might need 'price', 'short_text', etc.
        # Check if this executed action is about a material
        if ("material_id" in path or "material" in path) and is_resolved:
             # Try to hydrate line item from resolved details
             details = resolution_map.get(lookup_key, {}).get("details")
             if details:
                 # We need to find which line item we are touching
                 # Assuming path is like line_items[0].material_id OR line_items[0].material
                 if "[" in path and "]" in path:
                     idx = int(path.split("[")[1].split("]")[0])
                     items = payload.setdefault("line_items", [])
                     while len(items) <= idx:
                        items.append({})
                        
                     if idx < len(items):
                         item = items[idx]
                         item["material_id"] = int(details["id"]) # Ensure ID is set
                         item["short_text"] = details.get("name")
                         # Only override price if it's 0 or missing, to allow user override
                         if not item.get("price"):
                             item["price"] = float(details.get("price", 0))
                         item["material_group_id"] = int(details.get("material_group_id", 1))
                         item["unit_id"] = int(details.get("unit_id", 1))
                         item["tax_code"] = None 
                         
                         # If path was generic "material", redirect to 'material_id' for final set
                         if path.endswith(".material"):
                             path = path.replace(".material", ".material_id")
                             key = "material_id"
                             val = int(details["id"]) 
        
        # 3. Navigate and Apply
        # Handle 'ADD' to list (special case)
        if op == "ADD" and (path == "line_items" or path.endswith("line_items")):
            # Create new item
            new_item = {
                "short_text": "",
                "quantity": 1,
                "price": 0,
                "material_id": None
            }
            # If value provided is a dict, merge it
            if isinstance(val, dict):
                new_item.update(val)
            elif is_resolved: # Use resolved material
                # If the ADD action value was a material name
                 details = resolution_map.get(raw_val.strip().lower(), {}).get("details")
                 if details:
                     new_item["material_id"] = int(details["id"])
                     new_item["short_text"] = details.get("name")
                     new_item["price"] = float(details.get("price", 0))
                     new_item["material_group_id"] = int(details.get("material_group_id", 1))

            payload.setdefault("line_items", []).append(new_item)

            return "Added new line item."

        # Handle Standard Path Navigation
        parts = path.split('.')
        target = payload
        
        for i, part in enumerate(parts[:-1]):
            key = part
            idx = None
            if "[" in part:
                 key = part.split("[")[0]
                 idx = int(part.split("[")[1].rstrip("]"))
                 
            if isinstance(target, dict):
                target = target.setdefault(key, [] if idx is not None else {})
            
            if idx is not None:
                if isinstance(target, list):
                    while len(target) <= idx:
                         target.append({}) # Expand list if needed
                    target = target[idx]

        # Final Set
        last_part = parts[-1]
        key = last_part
        idx = None
        if "[" in last_part:
             key = last_part.split("[")[0]
             idx = int(last_part.split("[")[1].rstrip("]"))
        
        if idx is not None:
            # Setting a list item directly? Rare.
            pass
        else:
            if isinstance(target, dict):
                # Type Conversion for IDs
                if key.endswith("_id") and str(val).isdigit():
                    val = int(val)
                # Type Conversion for Booleans
                if isinstance(val, str):
                    if val.lower() == "true": val = True
                    elif val.lower() == "false": val = False
                    
                target[key] = val
                return f"Updated {key} to {val}"

        return None

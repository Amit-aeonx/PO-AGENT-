from mock_api import MockAPI
from bedrock_service import BedrockService
import datetime
import json
import re

# Conversational States
STATE_GREETING = "GREETING"
STATE_PO_INTENT = "PO_INTENT"
STATE_COLLECTING = "COLLECTING"
STATE_CONFIRM = "CONFIRM"
STATE_DONE = "DONE"

class POAgent:
    def __init__(self):
        self.api = MockAPI()
        self.nlu = BedrockService()
        
    def get_initial_state(self):
        return {
            "current_step": STATE_GREETING,
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
            "conversation_history": [],
            "missing_fields": [],
            "last_question": None,
            "extracted_entities": {},
            "temp_line_item": {}
        }

    def identify_missing_fields(self, payload, state=None):
        """Identify which mandatory fields are still missing"""
        missing = []
        
        # Check dates
        if not payload.get("po_date"):
            missing.append("po_date")
        if not payload.get("validityEnd"):
            missing.append("validityEnd")
        if not payload.get("currency"):
            missing.append("currency")
            
        # Check organization
        if not payload.get("purchase_org_id"):
            missing.append("purchase_org_id")
        if not payload.get("plant_id"):
            missing.append("plant_id")
        if not payload.get("purchase_grp_id"):
            missing.append("purchase_grp_id")
            
        # Check commercials (optional but ask)
        # Check commercials (optional but ask) MOVED to optional logic below
        # if not payload.get("payment_terms"):
        #     missing.append("payment_terms")
        # if not payload.get("inco_terms"):
        #     missing.append("inco_terms")
            
        # Check line items
        # If we have a temp line item, we are "working on it", so don't flag "line_items" as missing yet
        # Instead, check if that temp item has what it needs
        if state and state.get("temp_line_item"):
            item = state["temp_line_item"]
            if not item.get("delivery_date"):
                missing.append("delivery_date")
            elif not item.get("tax_code"):
                missing.append("tax_code")
        
        # Only flag "line_items" if we have NO items and NO temp item
        elif not payload.get("line_items") or len(payload["line_items"]) == 0:
            missing.append("line_items")
            
        # Optional Fields Logic
        # If core fields (dates, orgs, line items) are done, ask about optional fields
        if not missing and state and not state.get("optional_asked"):
            return ["optional_prompt"]
            
        # If user agreed to fill optional fields, check them
        if state and state.get("fill_optional"):
            if not payload.get("payment_terms"):
                missing.append("payment_terms")
            if not payload.get("inco_terms"):
                missing.append("inco_terms")
            # Projects is optional-optional but let's ask if they wanted optional fields
            if not payload.get("projects") or (len(payload["projects"]) > 0 and not payload["projects"][0]["project_code"]):
                 missing.append("projects")
        
        return missing

    def ask_next_question(self, state):
        """Generate next question based on missing fields"""
        missing = self.identify_missing_fields(state["payload"], state)
        
        if not missing:
            return None
            
        field = missing[0]
        
        questions = {
            "po_date": "What is the PO date? (Format: YYYY-MM-DD)",
            "validityEnd": "What is the validity end date? (Format: YYYY-MM-DD)",
            "purchase_org_id": "What is the Purchase Organization? (Type name or ID)",
            "plant_id": "What is the Plant? (Type name or ID)",
            "purchase_grp_id": "What is the Purchase Group? (Type name or ID)",
            "payment_terms": "What are the payment terms? (Type 'show options' to see list, or 'default')",
            "inco_terms": "What are the incoterms? (Type 'show options' to see list, or 'default')",
            "delivery_date": "What is the delivery date for the line item? (Format: YYYY-MM-DD)",
            "tax_code": "What is the tax code? (Type 'show options' to see list, or ID)",
            "currency": "What is the currency? (e.g., INR, USD)",
            "optional_prompt": "Do you want to fill these optional fields: **Payment Terms**, **Incoterms**, **Projects**? (Type **yes** or **no**)",
            "projects": "What is the Project Code? (Type 'show options' to see list, or code)"
        }
        
        question = questions.get(field, f"Please provide: {field}")
        state["last_question"] = question
        state["missing_fields"] = missing
        
        return question

    def format_options(self, items, id_key="id", name_key="name", limit=10):
        """Format list of options for display"""
        if not items:
            return "No options available."
            
        lines = ["Found options:"]
        for item in items[:limit]:
            item_id = item.get(id_key, "")
            item_name = item.get(name_key, "")
            lines.append(f"**{item_id}** – {item_name}")
            
        if len(items) > limit:
            lines.append(f"\n_(Showing {limit} of {len(items)} results)_")
            
        lines.append("\nType the ID to select.")
        return "\n".join(lines)

    def process_input(self, user_text, state):
        current_step = state["current_step"]
        payload = state["payload"]
        response_text = ""
        
        # Add to conversation history
        state["conversation_history"].append({"role": "user", "content": user_text})
        
        # ===== STATE: GREETING =====
        if current_step == STATE_GREETING:
            lower_text = user_text.lower().strip()
            
            # Handle number selection or text
            if lower_text in ["1", "independent", "independent po"] or "independ" in lower_text:
                payload["is_pr_based"] = False
                payload["is_rfq_based"] = False
                state["current_step"] = STATE_PO_INTENT
                response_text = "Great! What PO do you want to create?\n\n_Example: \"create a po for 2 scooty of regular purchase from supplier Smartsaa, each of 123 rupees\"_"
                
            elif lower_text in ["2", "pr", "pr-based", "pr based"] or ("pr" in lower_text and "based" in lower_text):
                response_text = "PR-based PO flow is coming soon. Please select **Independent PO** for now."
                
            elif lower_text in ["3", "rfq", "rfq-based", "rfq based"]:
                response_text = "RFQ-based PO flow is coming soon. Please select **Independent PO** for now."
                
            else:
                response_text = "Please select one of:\n1. **Independent PO**\n2. PR-based PO _(coming soon)_\n3. RFQ-based PO _(coming soon)_"
        
        # ===== STATE: PO_INTENT =====
        elif current_step == STATE_PO_INTENT:
            # Extract all entities from the intent message
            extracted = self.nlu.extract_po_intent(user_text)
            print(f"DEBUG: Extracted PO Intent: {extracted}")
            
            # Store extracted entities
            state["extracted_entities"] = extracted
            
            # Process PO Type
            if extracted.get("po_type"):
                payload["po_type"] = extracted["po_type"]
            
            # Process Supplier
            if extracted.get("supplier_name"):
                suppliers = self.api.search_suppliers(query=extracted["supplier_name"], limit=1)
                if suppliers:
                    payload["vendor_id"] = suppliers[0]["vendor_id"]
                    # Fetch alternate details
                    alt_details = self.api.get_alternate_supplier_details(suppliers[0]["vendor_id"])
                    payload["alternate_supplier_name"] = alt_details["alternate_supplier_name"]
                    payload["alternate_supplier_email"] = alt_details["alternate_supplier_email"]
                    payload["alternate_supplier_contact_number"] = alt_details["alternate_supplier_contact_number"]
                    
                    payload["alternate_supplier_email"] = alt_details["alternate_supplier_email"]
                    payload["alternate_supplier_contact_number"] = alt_details["alternate_supplier_contact_number"]
                    
                    # Auto-set currency REMOVED to ask user
                    # curr_list = self.api.get_currencies()
                    # payload["currency"] = curr_list[0] if curr_list else "INR"
            
            # Process Material and create line item
            if extracted.get("material_name"):
                materials = self.api.get_materials(query=extracted["material_name"])
                if materials:
                    mat = materials[0]
                    
                    # Create line item
                    # Create line item
                    new_item = {
                        "short_text": mat["name"],
                        "material_id": int(mat["id"]),
                        "unit_id": int(mat.get("unit_id", 0)), # Use pre-extracted unit_id
                        "price": float(mat["price"]),
                        "material_group_id": int(mat["material_group_id"]),
                        "tax_code": None, # Force manual collection
                        "quantity": int(extracted.get("quantity", 1)),
                        "subServices": "",
                        "control_code": ""
                    }
                    
                    # Override price if extracted
                    if extracted.get("price"):
                        new_item["price"] = float(extracted["price"])
                        
                    # Set delivery date if extracted
                    if extracted.get("delivery_date"):
                        new_item["delivery_date"] = extracted["delivery_date"]
                    
                    # Calculate subtotal
                    new_item["sub_total"] = new_item["quantity"] * new_item["price"]
                    # tax field is internal only, will be popped or ignored by API if not in schema
                    # But prompt says: Keep tax internal only.
                    new_item["tax"] = 0 
                    new_item["total_value"] = new_item["sub_total"]
                    
                    # Store in temp for delivery date
                    state["temp_line_item"] = new_item
            
            # Process Dates
            if extracted.get("po_date"):
                payload["po_date"] = extracted["po_date"]
            if extracted.get("validity_end"):
                payload["validityEnd"] = extracted["validity_end"]
                
            # Process Organization
            if extracted.get("purchase_org"):
                orgs = self.api.get_purchase_orgs()
                # Check for ID (digits) or Name match
                org_text = str(extracted["purchase_org"]).lower()
                if org_text.isdigit():
                    payload["purchase_org_id"] = int(org_text)
                else:
                    matches = [o for o in orgs if org_text in o['name'].lower()]
                    if len(matches) == 1:
                        payload["purchase_org_id"] = int(matches[0]["id"])
            
            # Process Plant (Requires Org ID)
            if extracted.get("plant") and payload.get("purchase_org_id"):
                plants = self.api.get_plants(org_ids=[payload["purchase_org_id"]])
                plant_text = str(extracted["plant"]).lower()
                
                # STRICT FIX: Never assign text directly. Must match ID/name.
                matches = [p for p in plants if plant_text in p['name'].lower() or plant_text == str(p['id']).lower()]
                if len(matches) == 1:
                    payload["plant_id"] = matches[0]["id"] # Valid UUID
            
            # Process Purchase Group (Requires Org ID)
            if extracted.get("purchase_group") and payload.get("purchase_org_id"):
                groups = self.api.get_purchase_groups(org_ids=[payload["purchase_org_id"]])
                group_text = str(extracted["purchase_group"]).lower()
                matches = [g for g in groups if group_text in g['name'].lower()]
                if len(matches) == 1:
                    payload["purchase_grp_id"] = int(matches[0]["id"])
            
            # Transition to collecting
            state["current_step"] = STATE_COLLECTING
            
            # Build response
            response_parts = ["Got it! I've captured:"]
            if payload.get("po_type"):
                response_parts.append(f"- PO Type: **{payload['po_type']}**")
            if payload.get("vendor_id"):
                response_parts.append(f"- Supplier: **{extracted.get('supplier_name')}**")
            if state.get("temp_line_item"):
                item = state["temp_line_item"]
                response_parts.append(f"- Material: **{item['short_text']}** (Qty: {item['quantity']}, Price: {item['price']})")
            
            # Add confirmation for new fields
            if payload.get("po_date"):
                response_parts.append(f"- PO Date: **{payload['po_date']}**")
            if payload.get("validityEnd"):
                response_parts.append(f"- Validity: **{payload['validityEnd']}**")
            if payload.get("purchase_org_id"):
                response_parts.append(f"- Purchase Org ID: **{payload['purchase_org_id']}**")
            if payload.get("plant_id"):
                response_parts.append(f"- Plant ID: **{payload['plant_id']}**")
            if payload.get("purchase_grp_id"):
                response_parts.append(f"- Purchase Group ID: **{payload['purchase_grp_id']}**")
            
            response_parts.append("\nLet me collect the remaining details...")
            response_text = "\n".join(response_parts)
            
            # Ask next question
            next_q = self.ask_next_question(state)
            if next_q:
                response_text += f"\n\n{next_q}"
        
        # ===== STATE: COLLECTING =====
        elif current_step == STATE_COLLECTING:
            missing = state.get("missing_fields", [])
            last_q = state.get("last_question", "")
            
            if not missing:
                missing = self.identify_missing_fields(payload, state)
                state["missing_fields"] = missing
            
            if not missing:
                # All fields collected, move to confirm
                state["current_step"] = STATE_CONFIRM
                
                # Finalize line item
                if state.get("temp_line_item"):
                    payload["line_items"].append(state["temp_line_item"])
                    state["temp_line_item"] = {}
                
                # Calculate total
                payload["total"] = sum([item["sub_total"] for item in payload["line_items"]])
                
                # Show summary
                response_text = self._generate_summary(payload)
                response_text += "\n\n**Should I create the Purchase Order now?** (Type 'yes' to confirm)"
                
            else:
                current_field = missing[0]
                
                # Check for "show options" intent
                intent_type = self.nlu.detect_intent_type(user_text)
                
                if intent_type == "show_options":
                    # Show options for current field
                    if current_field == "payment_terms":
                        terms = self.api.get_payment_terms()
                        response_text = self.format_options(terms, "id", "name")
                    elif current_field == "inco_terms":
                        terms = self.api.get_incoterms()
                        response_text = self.format_options(terms, "id", "name")
                    elif current_field == "tax_code":
                        codes = self.api.get_tax_codes()
                        response_text = self.format_options(codes, "id", "description")
                    else:
                        response_text = "Options not available for this field. Please provide a value."
                
                else:
                    # Process the value
                    if current_field == "po_date":
                        date_result = self.nlu.extract_date_with_context(user_text, last_q)
                        if date_result.get("purpose") == "unclear":
                            response_text = f"You mentioned a date ({date_result.get('date')}). Is this the **PO date**, **validity date**, or **delivery date**?"
                        else:
                            payload["po_date"] = date_result.get("date")
                            missing.remove("po_date")
                            next_q = self.ask_next_question(state)
                            response_text = f"✅ PO Date set to {date_result.get('date')}.\n\n{next_q}" if next_q else "✅ PO Date set."
                    
                    elif current_field == "validityEnd":
                        date_result = self.nlu.extract_date_with_context(user_text, last_q)
                        payload["validityEnd"] = date_result.get("date")
                        missing.remove("validityEnd")
                        next_q = self.ask_next_question(state)
                        response_text = f"✅ Validity End set to {date_result.get('date')}.\n\n{next_q}" if next_q else "✅ Validity set."
                    
                    elif current_field == "delivery_date":
                        date_result = self.nlu.extract_date_with_context(user_text, last_q)
                        if state.get("temp_line_item"):
                            state["temp_line_item"]["delivery_date"] = date_result.get("date")
                        missing.remove("delivery_date")
                        next_q = self.ask_next_question(state)
                        response_text = f"✅ Delivery Date set to {date_result.get('date')}.\n\n{next_q}" if next_q else "✅ Delivery date set."
                    
                    elif current_field == "purchase_org_id":
                        # Try to match organization
                        orgs = self.api.get_purchase_orgs()
                        
                        # Check if user provided ID directly
                        if user_text.strip().isdigit():
                            org_id = int(user_text.strip())
                            payload["purchase_org_id"] = org_id
                            missing.remove("purchase_org_id")
                            next_q = self.ask_next_question(state)
                            response_text = f"✅ Purchase Org set to {org_id}.\n\n{next_q}" if next_q else "✅ Org set."
                        else:
                            # Search by name
                            matches = [o for o in orgs if user_text.lower() in o['name'].lower()]
                            if len(matches) == 1:
                                payload["purchase_org_id"] = int(matches[0]["id"])
                                missing.remove("purchase_org_id")
                                next_q = self.ask_next_question(state)
                                response_text = f"✅ Purchase Org set to **{matches[0]['name']}**.\n\n{next_q}" if next_q else "✅ Org set."
                            elif len(matches) > 1:
                                response_text = self.format_options(matches, "id", "name")
                            else:
                                response_text = "No matches found. Please try again or type the ID."
                    
                    elif current_field == "plant_id":
                        org_id = payload.get("purchase_org_id")
                        if not org_id:
                            response_text = "Please set Purchase Org first."
                        else:
                            plants = self.api.get_plants(org_ids=[org_id])
                            
                            # Strict validation against API list
                            target_uuid = None
                            
                            # Normalize user text
                            u_text = user_text.strip().lower()
                            
                            # 1. Check for exact ID match in list
                            id_matches = [p for p in plants if str(p['id']).lower() == u_text]
                            if id_matches:
                                target_uuid = id_matches[0]['id']
                            else:
                                # 2. Check for name substring match
                                # Try full substring first
                                name_matches = [p for p in plants if u_text in p['name'].lower()]
                                
                                # If no match, try "all words present" (flexible for typos/spacing)
                                if not name_matches:
                                    search_words = u_text.replace("-", " ").split()
                                    name_matches = [p for p in plants if all(word in p['name'].lower() for word in search_words)]

                                if len(name_matches) == 1:
                                    target_uuid = name_matches[0]['id']
                                else:
                                    matches = name_matches # For options display
                            
                            if target_uuid:
                                payload["plant_id"] = target_uuid
                                missing.remove("plant_id")
                                next_q = self.ask_next_question(state)
                                # Fetch name for display
                                plant_name = next((p['name'] for p in plants if p['id'] == target_uuid), target_uuid)
                                response_text = f"✅ Plant set to **{plant_name}**.\n\n{next_q}" if next_q else "✅ Plant set."
                            elif 'matches' in locals() and len(matches) > 1:
                                response_text = self.format_options(matches, "id", "name")
                            else:
                                response_text = "No matches found. Please try again or type the ID."

                    
                    elif current_field == "purchase_grp_id":
                        org_id = payload.get("purchase_org_id")
                        if not org_id:
                            response_text = "Please set Purchase Org first."
                        else:
                            groups = self.api.get_purchase_groups(org_ids=[org_id])
                            
                            if user_text.strip().isdigit():
                                payload["purchase_grp_id"] = int(user_text.strip())
                                missing.remove("purchase_grp_id")
                                next_q = self.ask_next_question(state)
                                response_text = f"✅ Purchase Group set.\n\n{next_q}" if next_q else "✅ Group set."
                            else:
                                matches = [g for g in groups if user_text.lower() in g['name'].lower()]
                                if len(matches) == 1:
                                    payload["purchase_grp_id"] = int(matches[0]["id"])
                                    missing.remove("purchase_grp_id")
                                    next_q = self.ask_next_question(state)
                                    response_text = f"✅ Purchase Group set to **{matches[0]['name']}**.\n\n{next_q}" if next_q else "✅ Group set."
                                elif len(matches) > 1:
                                    response_text = self.format_options(matches, "id", "name")
                                else:
                                    response_text = "No matches found. Please try again or type the ID."
                    
                    elif current_field == "optional_prompt":
                        if user_text.lower().strip() in ["yes", "y"]:
                            state["fill_optional"] = True
                            state["optional_asked"] = True
                            # Missing fields will be re-calculated next turn to include optional ones
                            response_text = "Okay, let's fill them."
                        else:
                            state["fill_optional"] = False
                            state["optional_asked"] = True
                            # Set defaults immediately so they aren't "missing"
                            # Payment Terms Default
                            terms = self.api.get_payment_terms()
                            if terms: payload["payment_terms"] = int(terms[0]["id"])
                            # Inco Terms Default
                            inco = self.api.get_incoterms()
                            if inco: payload["inco_terms"] = int(inco[0]["id"])
                            # Projects Default (set to empty list to skip)
                            payload["projects"] = []
                            
                            # Check if we are done (should be yes)
                            rem_missing = self.identify_missing_fields(payload, state)
                            if not rem_missing:
                                state["current_step"] = STATE_CONFIRM
                                
                                # Finalize line item
                                if state.get("temp_line_item"):
                                    item = state["temp_line_item"]
                                    # Ensure defaults for internal logic
                                    if item.get("tax_code") is None: item["tax_code"] = 119 
                                    if not item.get("total_value"): item["total_value"] = item["sub_total"]
                                    state["payload"]["line_items"].append(item)
                                    state["temp_line_item"] = {}
                                
                                # Calculate Total
                                total = sum(i["total_value"] for i in state["payload"]["line_items"])
                                payload["total"] = total
                                
                                summary = self._generate_summary(payload)
                                response_text = f"Skipping optional fields.\n\n{summary}\n\nShould I create the Purchase Order now? (Type 'yes' to confirm)"
                            else:
                                next_q = self.ask_next_question(state)
                                response_text = f"Skipping optional fields.\n\n{next_q}"

                    elif current_field == "projects":
                         p_text = user_text.strip()
                         # Fetch projects to validate
                         projs = self.api.get_projects()
                         matches = [p for p in projs if p_text.lower() in p['project_code'].lower() or p_text.lower() in p['project_name'].lower()]
                         
                         if matches:
                             # Set the FIRST match
                             payload["projects"] = [{
                                 "project_code": matches[0]["project_code"], 
                                 "project_name": matches[0]["project_name"]
                             }]
                             if "projects" in missing: missing.remove("projects")
                             next_q = self.ask_next_question(state)
                             response_text = f"✅ Project set to **{matches[0]['project_name']}**.\n\n{next_q}" if next_q else "✅ Project set."
                         elif p_text.lower() == "show options":
                             response_text = self.format_options(projs, "project_code", "project_name")
                         else:
                             response_text = "No matching project found. Type 'show options' to see list."

                    elif current_field == "payment_terms":
                        if user_text.lower().strip() == "default":
                            terms = self.api.get_payment_terms()
                            if terms:
                                payload["payment_terms"] = int(terms[0]["id"])
                                missing.remove("payment_terms")
                                next_q = self.ask_next_question(state)
                                response_text = f"✅ Payment Terms set to default.\n\n{next_q}" if next_q else "✅ Payment terms set."
                        elif user_text.strip().isdigit():
                            payload["payment_terms"] = int(user_text.strip())
                            missing.remove("payment_terms")
                            next_q = self.ask_next_question(state)
                            response_text = f"✅ Payment Terms set.\n\n{next_q}" if next_q else "✅ Payment terms set."
                        else:
                            response_text = "Please provide the payment term ID or type 'default' or 'show options'."
                    
                    elif current_field == "inco_terms":
                        if user_text.lower().strip() == "default":
                            terms = self.api.get_incoterms()
                            if terms:
                                payload["inco_terms"] = int(terms[0]["id"])
                                missing.remove("inco_terms")
                                next_q = self.ask_next_question(state)
                                response_text = f"✅ Incoterms set to default.\n\n{next_q}" if next_q else "✅ Incoterms set."
                        elif user_text.strip().isdigit():
                            payload["inco_terms"] = int(user_text.strip())
                            missing.remove("inco_terms")
                            next_q = self.ask_next_question(state)
                            response_text = f"✅ Incoterms set.\n\n{next_q}" if next_q else "✅ Incoterms set."
                        else:
                            response_text = "Please provide the incoterm ID or type 'default' or 'show options'."
                    
                    elif current_field == "currency":
                        curr_text = user_text.strip().upper()
                        # Basic validation
                        if len(curr_text) == 3:
                            payload["currency"] = curr_text
                            missing.remove("currency")
                            next_q = self.ask_next_question(state)
                            response_text = f"✅ Currency set to **{curr_text}**.\n\n{next_q}" if next_q else "✅ Currency set."
                        else:
                            response_text = "Please provide a valid 3-letter currency code (e.g., INR, USD)."
                            
                    elif current_field == "tax_code":
                        if user_text.strip().isdigit():
                            if state.get("temp_line_item"):
                                state["temp_line_item"]["tax_code"] = int(user_text.strip())
                            missing.remove("tax_code")
                            next_q = self.ask_next_question(state)
                            response_text = f"✅ Tax Code set.\n\n{next_q}" if next_q else "✅ Tax code set."
                        else:
                            response_text = "Please provide the tax code ID or type 'show options'."
        
        # ===== STATE: CONFIRM =====
        elif current_step == STATE_CONFIRM:
            intent_type = self.nlu.detect_intent_type(user_text)
            
            if intent_type == "confirm":
                # Create PO
                print(f"DEBUG: Creating PO with payload keys: {list(payload.keys())}")
                
                # Clean payload before submission
                api_payload = payload.copy()
                
                # Remove total_value from line items
                if "line_items" in api_payload:
                    for item in api_payload["line_items"]:
                        item.pop("total_value", None)
                        item["subServices"] = ""
                        item["control_code"] = ""
                
                # Set default project if empty
                # Set default project if empty
                # Check if first project has empty code
                if not api_payload.get("projects") or (len(api_payload["projects"]) > 0 and not api_payload["projects"][0]["project_code"]):
                    projects = self.api.get_projects()
                    if projects:
                        api_payload["projects"] = [{
                            "project_code": projects[0]["project_code"],
                            "project_name": projects[0]["project_name"]
                        }]
                    else:
                        api_payload["projects"] = [] # Send empty list if no project found
                
                # Set remarks if empty
                if not api_payload.get("remarks"):
                    api_payload["remarks"] = "Created via AI Agent"
                
                print(f"DEBUG: Sending payload: {json.dumps(api_payload, indent=2)}")
                
                # Call API
                api_resp = self.api.create_po(api_payload)
                
                print(f"DEBUG: API Response: {str(api_resp)[:300]}")
                
                # Check success
                is_success = (api_resp.get("error") == False or api_resp.get("success") == True)
                
                if is_success:
                    po_num = api_resp.get("po_number", api_resp.get("data", {}).get("po_number", "Created"))
                    response_text = f"✅ **Success!** Purchase Order created.\n\n**PO Number:** {po_num}\n\n[Ref ID: {api_resp.get('id', 'N/A')}]"
                    state["current_step"] = STATE_DONE
                else:
                    msg = api_resp.get("message", "Unknown Error")
                    
                    # Extract SAP errors
                    if isinstance(api_resp.get("data"), list):
                        sap_errors = [d.get("msg", "") for d in api_resp["data"] if d.get("type") == "E"]
                        if sap_errors:
                            msg = "SAP Errors: " + " | ".join(sap_errors)
                    
                    response_text = f"❌ **Submission Failed**\n\nError: {msg}\n\nResponse: {str(api_resp)[:400]}"
            
            elif intent_type == "reject":
                response_text = "PO creation cancelled. Type 'Hi' to start over."
                state["current_step"] = STATE_GREETING
            
            else:
                response_text = "Please confirm: Type **'yes'** to create the PO, or **'no'** to cancel."
        
        # ===== STATE: DONE =====
        elif current_step == STATE_DONE:
            response_text = "PO has been created. Type 'Hi' to create another PO."
            if "hi" in user_text.lower() or "hello" in user_text.lower():
                # Reset
                new_state = self.get_initial_state()
                state.update(new_state)
                response_text = "Hi 👋 What type of PO do you want to create?\n\n1. **Independent PO**\n2. PR-based PO _(coming soon)_\n3. RFQ-based PO _(coming soon)_"
        
        return response_text

    def _generate_summary(self, payload):
        """Generate summary for confirmation"""
        lines = ["📋 **Purchase Order Summary:**\n"]
        
        if payload.get("po_type"):
            lines.append(f"**PO Type:** {payload['po_type']}")
        
        if payload.get("vendor_id"):
            lines.append(f"**Supplier ID:** {payload['vendor_id']}")
        
        if payload.get("po_date"):
            lines.append(f"**PO Date:** {payload['po_date']}")
        
        if payload.get("validityEnd"):
            lines.append(f"**Validity:** {payload['validityEnd']}")
        
        if payload.get("line_items"):
            lines.append(f"\n**Line Items ({len(payload['line_items'])}):**")
            for i, item in enumerate(payload["line_items"], 1):
                lines.append(f"{i}. {item['short_text']} - Qty: {item['quantity']}, Price: {item['price']}, Subtotal: {item['sub_total']}")
        
        if payload.get("total"):
            lines.append(f"\n**Total Amount:** ₹{payload['total']}")
        
        return "\n".join(lines)

import streamlit as st
import pandas as pd
import json
from agent_logic import POAgent, STATE_SUPPLIER, STATE_INIT, STATE_PO_TYPE, STATE_ORG_DETAILS, STATE_COMMERCIALS, STATE_LINE_ITEMS_START, STATE_LINE_ITEM_DETAILS, STATE_SUPPLIER_DETAILS

# Page Config
st.set_page_config(page_title="SupplierX AI Agent", layout="wide")

# Custom CSS
st.markdown("""
<style>
    .reportview-container {
        background: #f0f2f6;
    }
    .main-header {
        font-size: 24px;
        font-weight: bold;
        color: #1E3A8A;
    }
    .stButton button {
        width: 100%;
        text-align: left;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.title("🤖 SupplierX Enterprise Agent")
st.markdown("Create a Purchase Order through conversation.")

# Initialize Session State
if "agent" not in st.session_state:
    st.session_state.agent = POAgent()

if "conversation_state" not in st.session_state:
    st.session_state.conversation_state = st.session_state.agent.get_initial_state()
    # Add initial greeting
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I am your Purchase Order Assistant. \n\nLet's start. Please tell me the **PO Type** (e.g., 'Regular Purchase' or 'Service PO')?"}
    ]

# Sidebar - Payload Monitor (Debug View)
with st.sidebar:
    st.header("📄 Live Payload Monitor")
    st.info("This shows the JSON building in real-time.")
    st.json(st.session_state.conversation_state["payload"])
    
    if st.button("Reset Conversation"):
        del st.session_state.conversation_state
        del st.session_state.messages
        st.rerun()

# Chat Interface
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- UI INTERACTIVE BLOCKS ---
current_step = st.session_state.conversation_state["current_step"]

# 1. PO TYPE SELECTOR
if current_step == STATE_PO_TYPE:
    st.markdown("### Select PO Type")
    po_types = st.session_state.agent.api.get_po_sub_types()
    
    # Use pills if available (Streamlit 1.40+)
    if hasattr(st, "pills"):
        selected_type = st.pills("Purchase Order Types", po_types, selection_mode="single", key="po_type_pills")
        if selected_type:
            st.session_state.messages.append({"role": "user", "content": selected_type})
            response = st.session_state.agent.process_input(selected_type, st.session_state.conversation_state)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()
    else:
        cols = st.columns(4)
        for i, pt in enumerate(po_types):
            if cols[i % 4].button(pt, key=f"btn_po_{i}"):
                 st.session_state.messages.append({"role": "user", "content": pt})
                 response = st.session_state.agent.process_input(pt, st.session_state.conversation_state)
                 st.session_state.messages.append({"role": "assistant", "content": response})
                 st.rerun()

# 2. SUPPLIER SELECTOR
elif current_step == STATE_SUPPLIER:
    st.markdown("### Select Supplier")
    
    # Fetch Data
    # For better UX, maybe fetch once or cache? 
    # Calling API every rerun is okay for mock/dev.
    data = st.session_state.agent.api.search_suppliers(limit=10)
    
    if not data:
         st.warning("No suppliers found.")
    else:
        # Render as a list of buttons with details
        for i, sup in enumerate(data):
            # Format: Name (SAP Code) - Email
            label = f"🏢 {sup['name']} ({sup.get('sap_code', sup['vendor_id'])})"
            if st.button(label, key=f"sup_btn_{i}"):
                # User clicked a supplier - send name to process_input
                selection_text = sup['name']
                st.session_state.messages.append({"role": "user", "content": selection_text})
                response = st.session_state.agent.process_input(selection_text, st.session_state.conversation_state)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()

# 2.5 SUPPLIER DETAILS (PO DATE & VALIDITY)
elif current_step == STATE_SUPPLIER_DETAILS:
    st.markdown("### PO Date & Validity")
    
    col1, col2 = st.columns(2)
    with col1:
        po_date = st.date_input("PO Date", value="today", key="picker_po_date")
    with col2:
        valid_date = st.date_input("Validity End Date", value="today", key="picker_valid_date")
        
    if st.button("Confirm Dates", type="primary"):
        # Format as text for the agent to parse
        date_msg = f"PO Date: {po_date}, Validity: {valid_date}"
        
        st.session_state.messages.append({"role": "user", "content": date_msg})
        response = st.session_state.agent.process_input(date_msg, st.session_state.conversation_state)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()
elif current_step == STATE_ORG_DETAILS:
    st.markdown("### Select Organization Details")
    
    # Initialize UI state for this step if needed
    if "selected_org_id" not in st.session_state:
        st.session_state.selected_org_id = None
    
    # 1. Fetch Purchase Orgs
    orgs = st.session_state.agent.api.get_purchase_orgs()
    org_opts = {f"{o['name']} ({o['id']})": o['id'] for o in orgs}
    
    # Org Selection Dropdown
    # We use a key that updates session state automatically if possible, or handle manually
    s_org_key = st.selectbox("Purchase Org", options=list(org_opts.keys()), key="org_selector")
    
    # Update state if changed
    if s_org_key:
        current_id = org_opts[s_org_key]
        if st.session_state.selected_org_id != current_id:
             st.session_state.selected_org_id = current_id
             # Force rerun to fetch dependents? Streamlit might handle it on next pass naturally
             # But we need to clear old plant/group selections potentialy.
    
    # 2. Fetch Dependents if Org Selected
    if st.session_state.selected_org_id:
        org_id = st.session_state.selected_org_id
        
        # Fetch Plants and Groups using the confirmed Org ID
        plants = st.session_state.agent.api.get_plants(org_ids=[org_id])
        groups = st.session_state.agent.api.get_purchase_groups(org_ids=[org_id])
        
        plant_opts = {f"{p['name']} ({p['id']})": p['id'] for p in plants}
        group_opts = {f"{g['name']} ({g['id']})": g['id'] for g in groups}
        
        c2, c3 = st.columns(2)
        with c2:
            s_plant = st.selectbox("Plant", options=list(plant_opts.keys()), key="plant_selector")
        with c3:
            s_grp = st.selectbox("Purchase Group", options=list(group_opts.keys()), key="group_selector")
            
        if st.button("Confirm Selection", type="primary"):
            # Construct text that the Agent Logic can parse confidently.
            sel_plant_id = plant_opts[s_plant] if s_plant else ""
            sel_grp_id = group_opts[s_grp] if s_grp else ""
            
            msg = f"Selected: Purchase Org {org_id}, Plant {sel_plant_id}, Group {sel_grp_id}"
            
            st.session_state.messages.append({"role": "user", "content": msg})
            response = st.session_state.agent.process_input(msg, st.session_state.conversation_state)
            st.session_state.messages.append({"role": "assistant", "content": response})
            # Clear UI state for next time or just leave it
            del st.session_state.selected_org_id 
            st.rerun()
    else:
        st.info("Please select a Purchase Organization to see available Plants and Groups.")

# 4. COMMERCIALS SELECTOR
elif current_step == STATE_COMMERCIALS:
    st.markdown("### Commercial Details (Optional)")
    
    # Fetch Options
    projects = st.session_state.agent.api.get_projects()
    pay_terms = st.session_state.agent.api.get_payment_terms()
    inco_terms = st.session_state.agent.api.get_incoterms()
    
    # Format
    # Assuming standard {id, name} or {project_code, project_name} from updated mock_api
    proj_opts = {f"{p.get('project_name','')} ({p.get('project_code','')})": p.get('project_code','') for p in projects}
    pay_opts = {f"{t['name']} ({t['id']})": t['id'] for t in pay_terms}
    inco_opts = {f"{t['name']} ({t['id']})": t['id'] for t in inco_terms}
    
    with st.expander("Commercials Form", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            s_proj = st.selectbox("Project", options=["None"] + list(proj_opts.keys()))
        with c2:
            s_pay = st.selectbox("Payment Term", options=["None"] + list(pay_opts.keys()))
        with c3:
            s_inco = st.selectbox("Inco Term", options=["None"] + list(inco_opts.keys()))
            
        col_submit, col_skip = st.columns([1, 1])
        with col_submit:
            if st.button("Submit Details", type="primary"):
                # Extract values
                sel_proj_code = proj_opts[s_proj] if s_proj != "None" else ""
                sel_pay_id = pay_opts[s_pay] if s_pay != "None" else ""
                sel_inco_id = inco_opts[s_inco] if s_inco != "None" else ""
                
                msg = []
                if sel_proj_code: msg.append(f"Project: {sel_proj_code}")
                if sel_pay_id: msg.append(f"Payment Term: {sel_pay_id}")
                if sel_inco_id: msg.append(f"Inco Term: {sel_inco_id}")
                
                final_msg = ", ".join(msg) if msg else "No commercials selected."
                
                st.session_state.messages.append({"role": "user", "content": final_msg})
                response = st.session_state.agent.process_input(final_msg, st.session_state.conversation_state)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()
                
        with col_skip:
            if st.button("Skip / No Details"):
                 st.session_state.messages.append({"role": "user", "content": "Skip commercials."})
                 response = st.session_state.agent.process_input("Skip commercials.", st.session_state.conversation_state)
                 st.session_state.messages.append({"role": "assistant", "content": response})
                 st.rerun()

# 5. LINE ITEMS
elif current_step in [STATE_LINE_ITEMS_START, STATE_LINE_ITEM_DETAILS]:
    st.markdown("### Line Items")
    
    # Init temp storage
    if "current_line_item" not in st.session_state:
        st.session_state.current_line_item = {}

    # Display added items
    payload = st.session_state.conversation_state["payload"]
    items = payload.get("line_items", [])
    if items:
        st.write(f"**Added Items ({len(items)}):**")
        df_items = pd.DataFrame(items)
        # Show specific columns
        cols_to_show = ["short_text", "quantity", "price", "sub_total"]
        st.dataframe(df_items[cols_to_show] if not df_items.empty else df_items)

    st.markdown("#### Add New Item")
    
    # Step A: Select Material
    if not st.session_state.current_line_item.get("id"):
        st.markdown("Select a Material from the list:")
        
        try:
             mats = st.session_state.agent.api.get_materials()
        except Exception as e:
             st.error(f"Failed to fetch materials: {e}")
             mats = []
        
        mat_opts = {f"{m['name']} ({m['id']}) - {m['price']} {m['unit']}": m['id'] for m in mats}
        
        if "material_selector" not in st.session_state:
            st.session_state["material_selector"] = "Select..."
            
        # 1. Selectbox (Selection Source)
        st.selectbox(
            "Available Materials", 
            options=["Select..."] + list(mat_opts.keys()),
            key="material_selector"
        )
        
        # 2. Confirmation Button (Action Trigger)
        if st.button("Select This Material"):
            # READ VALUE DIRECTLY FROM STATE (Bypassing any UI return value lag)
            sel_val = st.session_state.get("material_selector")
            
            if sel_val and sel_val != "Select...":
                 mat_id = mat_opts[sel_val]
                 selected_m = next((m for m in mats if m['id'] == mat_id), None)
                 
                 if selected_m:
                      st.session_state.current_line_item = selected_m
                      # Init defaults
                      st.session_state.current_line_item["quantity"] = 1
                      st.session_state.current_line_item["price"] = selected_m['price']
                      
                      # FORCE RERUN TO SHOW DETAILS FORM
                      st.rerun()
            else:
                st.warning("Please select a valid material from the list above.")

        st.caption("Don't see it? Type to search:")
        search_q = st.text_input("Search (Optional)", placeholder="e.g. Steel")
        if search_q:
             try:
                 mats_filtered = st.session_state.agent.api.get_materials(query=search_q)
                 if mats_filtered:
                      for m in mats_filtered:
                           if st.button(f"{m['name']} ({m['id']})", key=f"search_{m['id']}"):
                                st.session_state.current_line_item = m
                                st.session_state.current_line_item["quantity"] = 1
                                st.session_state.current_line_item["price"] = m['price']
                                st.rerun()
             except Exception:
                 st.warning("Search failed.")

    # Step B: Enter Details (if material selected)
    else:
        m = st.session_state.current_line_item
        st.info(f"Adding Details for: **{m['name']}** ({m['id']})")
        
        # Row 1: Qty, Price, Date
        c1, c2, c3 = st.columns(3)
        with c1:
            qty = st.number_input("Quantity", min_value=1, value=m.get("quantity", 1))
        with c2:
            price = st.number_input("Price per Unit", min_value=0.0, value=float(m.get("price", 0.0)))
        with c3:
            import datetime
            del_date = st.date_input("Delivery Date", value=datetime.date.today())

        # Row 2: Tax, Remarks
        c4, c5 = st.columns(2)
        with c4:
            # Fetch tax codes if possible, else text
            # mock_api has get_tax_codes
            tax_codes = st.session_state.agent.api.get_tax_codes()
            tax_opts = {f"{t['description']} ({t['id']})": t['id'] for t in tax_codes}
            # Default to first or user text
            s_tax = st.selectbox("Tax Code", options=list(tax_opts.keys()))
            sel_tax_id = tax_opts[s_tax] if s_tax else 119
            
        with c5:
            remarks = st.text_input("Remarks", placeholder="Item specific remarks")
            
        # Calculate Subtotal for display
        sub_total = qty * price
        st.write(f"**Sub Total:** {sub_total}")

        col_add, col_cancel = st.columns([1,1])

        with col_add:
            if st.button("Confirm & Add Item", type="primary"):
                
                new_item = {
                    "short_text": m["name"],
                    "short_desc": remarks if remarks else m["name"],
                    "quantity": qty,
                    "unit_id": m.get("unit_id", 0),
                    "price": price,
                    "subServices": [],
                    "control_code": m.get("hsn_id", ""),
                    "delivery_date": str(del_date),
                    "material_id": int(m["id"]) if str(m["id"]).isdigit() else m["id"],  # CONVERT TO INT
                    "sub_total": float(sub_total),
                    "tax_code": int(sel_tax_id),
                    "material_group_id": m.get("material_group_id", 0),
                    "tax": 12
                }
                
                # Append to payload
                st.session_state.conversation_state["payload"]["line_items"].append(new_item)
                
                # Notify Agent
                response = st.session_state.agent.process_input("Confirmed line item.", st.session_state.conversation_state)
                
                # Clear temp
                st.session_state.current_line_item = {}
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()
            
        with col_cancel:
            if st.button("Cancel Selection"):
                st.session_state.current_line_item = {}
                st.rerun()

    # Finish Button and Payload Preview
    items = payload.get("line_items", [])
    if items and not st.session_state.current_line_item.get("material_id"):
        st.divider()
        st.markdown("### Ready to Submit?")
        with st.expander("View Complete Payload (JSON)", expanded=False):
             import json
             # Show both Python dict view and actual JSON string
             st.markdown("**Python Dict View:**")
             st.json(st.session_state.conversation_state["payload"])
             st.markdown("**Actual JSON String (sent to API):**")
             st.code(json.dumps(st.session_state.conversation_state["payload"], indent=2), language="json")
             
        if st.button("Create Purchase Order", type="primary"):
            st.session_state.messages.append({"role": "user", "content": "Create PO"})
            response = st.session_state.agent.process_input("Create PO", st.session_state.conversation_state)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()

# User Input
if prompt := st.chat_input("Type your response here..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            # Capture prev state for rerun check
            prev_step = st.session_state.conversation_state["current_step"]
            
            # FIX: Use session state directly to avoid NameError
            response = st.session_state.agent.process_input(prompt, st.session_state.conversation_state)
            
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
            
            # If step changed to an interactive step, rerun to show the UI
            new_step = st.session_state.conversation_state["current_step"]
            if new_step != prev_step:
                st.rerun()

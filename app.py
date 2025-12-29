import streamlit as st
import json
from agent_logic import POAgent

# Page Config
st.set_page_config(page_title="SupplierX AI Agent", layout="wide")

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 28px;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 10px;
    }
    .sub-header {
        font-size: 14px;
        color: #6B7280;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.markdown('<div class="main-header">🤖 SupplierX Conversational PO Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Create Purchase Orders through natural conversation</div>', unsafe_allow_html=True)

# Initialize Session State
if "agent" not in st.session_state:
    st.session_state.agent = POAgent()
    st.session_state.conversation_state = st.session_state.agent.get_initial_state()
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi 👋 What type of PO do you want to create?\n\n1. **Independent PO**\n2. PR-based PO _(coming soon)_\n3. RFQ-based PO _(coming soon)_"}
    ]

# Sidebar - Payload Monitor
with st.sidebar:
    st.header("📄 Live Payload Monitor")
    st.info("This shows the JSON building in real-time.")
    
    # Show payload in collapsible sections
    with st.expander("View Full Payload", expanded=False):
        st.json(st.session_state.conversation_state["payload"])
    
    # Show key fields
    payload = st.session_state.conversation_state["payload"]
    st.markdown("### Quick View")
    if payload.get("po_type"):
        st.success(f"✅ PO Type: {payload['po_type']}")
    if payload.get("vendor_id"):
        st.success(f"✅ Supplier: {payload['vendor_id'][:8]}...")
    if payload.get("po_date"):
        st.success(f"✅ PO Date: {payload['po_date']}")
    if payload.get("line_items"):
        st.success(f"✅ Line Items: {len(payload['line_items'])}")
    
    st.divider()
    
    # Current State
    current_state = st.session_state.conversation_state["current_step"]
    st.markdown(f"**Current State:** `{current_state}`")
    
    st.divider()
    
    if st.button("🔄 Reset Conversation", type="secondary"):
        del st.session_state.conversation_state
        del st.session_state.messages
        st.rerun()

# Chat Display
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Function to handle button click as user input
def handle_po_type_selection(po_type_text):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": po_type_text})
    
    # Process with agent
    with st.spinner("Thinking..."):
        try:
            response = st.session_state.agent.process_input(
                po_type_text, 
                st.session_state.conversation_state
            )
            st.session_state.messages.append({"role": "assistant", "content": response})
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
    
    st.rerun() # Rerun to update the chat UI

# Initial Helper Buttons
if len(st.session_state.messages) == 1:
    st.write("### Select PO Type:")
    c1, c2, c3 = st.columns(3)
    if c1.button("Independent PO", type="primary", use_container_width=True):
        handle_po_type_selection("Independent PO")
    
    if c2.button("PR-based PO (Coming Soon)", disabled=True, use_container_width=True):
        pass
        
    if c3.button("RFQ-based PO (Coming Soon)", disabled=True, use_container_width=True):
        pass

# User Input
if prompt := st.chat_input("Type your message here..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Process with agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = st.session_state.agent.process_input(
                    prompt, 
                    st.session_state.conversation_state
                )
                
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                
            except Exception as e:
                error_msg = f"❌ Error: {str(e)}\n\nPlease try again or type 'Hi' to restart."
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                print(f"ERROR in process_input: {e}")
                import traceback
                traceback.print_exc()

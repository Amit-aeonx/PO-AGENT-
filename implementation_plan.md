# Implementation Plan - SupplierX PO Agent (Streamlit + AWS Bedrock)

I will build the **SupplierX Enterprise Conversational AI Agent** as a **Streamlit** web application, powered by **AWS Bedrock (Claude 3.7 Sonnet)** for natural language understanding, while maintaining a **Strict State Machine** that enforces the specific flow you defined.

## User Review Required
> [!IMPORTANT]
> **Flow Update**: I have re-ordered the State Machine to match your latest instructions:
> 1.  **PO Type** (First) -> 2. **Supplier** -> 3. **Org & Dates** -> 4. **Commercials** -> 5. **Line Items** (Material vs Service logic).

> [!NOTE]
> **Search Features**: I will implement the "Top 10" list and "Auto-suggest" for Supplier and Purchase Group search as requested.

## Proposed Changes

### Project Structure

#### [NEW] [.env](file:///d:/OneDrive%20-%20aeonx.digital/Desktop/PO_create_agent/.env)
- Stores `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `AWS_REGION`, and `ANTHROPIC_MODEL_ID`.

#### [NEW] [mock_api.py](file:///d:/OneDrive%20-%20aeonx.digital/Desktop/PO_create_agent/mock_api.py)
- **Updates**:
    -   `get_po_types`: Returns list from screenshot (Asset, Service, Regular Purchase, Internal Order, etc.).
    -   `search_suppliers(query)`: Logic to return Top 10 if query is empty, or filter if text is provided.
    -   `get_materials` vs `get_services`: Separate endpoints to support the logic branch.

#### [NEW] [bedrock_service.py](file:///d:/OneDrive%20-%20aeonx.digital/Desktop/PO_create_agent/bedrock_service.py)
- **Function**: `analyze_intent(user_text, current_state)`
- **Role**: Extracts entities like "Tata Steel" (Supplier) or "Regular Purchase" (PO Type) to auto-fill the state machine.

#### [NEW] [agent_logic.py](file:///d:/OneDrive%20-%20aeonx.digital/Desktop/PO_create_agent/agent_logic.py)
- **State Machine Revised Flow**:
    1.  `STATE_PO_TYPE`: Ask "Independent vs PR" & "PO Type" (Regular, Service, etc.).
    2.  `STATE_SUPPLIER`: Show Top 10 list. Handle user search query.
    3.  `STATE_SUPPLIER_DETAILS`: Fetch Currency. Ask PO Date, Validity.
    4.  `STATE_ORG_DETAILS`: Ask Purchase Org, Plant, Purchase Group (Auto-suggest).
    5.  `STATE_COMMERCIALS`: Ask Projects, Payment Terms, Inco Terms.
    6.  `STATE_LINE_ITEMS`:
        -   **IF** `po_type == 'Regular Purchase'`: Ask **Material**.
        -   **ELSE**: Ask **Service**.
        -   Collect: Remarks, Price, Qty, Tax Code.
    7.  `STATE_CONFIRM`: Show summary -> Create Payload.

#### [NEW] [app.py](file:///d:/OneDrive%20-%20aeonx.digital/Desktop/PO_create_agent/app.py)
- **UI**: Streamlit Chat.
- **Components**: 
    -   Uses `st.dataframe` or `st.markdown` tables to show "Top 10 Suppliers" cleanly.
    -   Displays the "Exact Payload" in the sidebar for real-time validation.

#### [NEW] [requirements.txt](file:///d:/OneDrive%20-%20aeonx.digital/Desktop/PO_create_agent/requirements.txt)
- `streamlit`
- `boto3`
- `python-dotenv`
- `pandas`

## Verification Plan

### Manual Verification
1.  **Test Flow Alignment**:
    -   Launch App.
    -   **Verify Step 1**: Must ask "PO Type" immediately. Select "Regular Purchase".
    -   **Verify Step 2**: See "Top 10 Suppliers". Type "Tat" -> Expect auto-suggest/filter for "Tata".
    -   **Verify Step 6**: Since "Regular Purchase" was selected, verify it asks for **Material**, NOT Service.
    -   **Restart**: Select "Service PO" -> Verify it asks for **Service**.

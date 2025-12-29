
import boto3
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

class BedrockService:
    def __init__(self):
        self.client = boto3.client(
            'bedrock-runtime',
            region_name=os.getenv('AWS_REGION'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY'),
            aws_secret_access_key=os.getenv('AWS_SECRET_KEY')
        )
        self.model_id = os.getenv('ANTHROPIC_MODEL_ID')

    def _call_claude(self, system_prompt, user_text):
        """Internal method to call Claude API"""
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1500,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_text}],
            "temperature": 0
        }
        
        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(payload)
            )
            
            result_body = json.loads(response['body'].read())
            content_text = result_body['content'][0]['text']
            
            # Extract JSON from the text
            if "```json" in content_text:
                json_str = content_text.split("```json")[1].split("```")[0].strip()
            elif "{" in content_text:
                json_str = content_text[content_text.find('{'):content_text.rfind('}')+1]
            else:
                json_str = "{}"
            
            return json.loads(json_str)
            
        except Exception as e:
            print(f"Error calling Bedrock: {e}")
            return {"error": str(e)}

    def extract_po_intent(self, user_text, conversation_history=None):
        """
        Extract complete PO intent from natural language.
        Example: "create a po for 2 scooty of regular purchase from supplier Smartsaa, each of 123 rupees"
        Returns: {po_type, material, quantity, supplier, price, po_date, purchase_org, plant, purchase_group}
        """
        system_prompt = """You are an expert entity extractor for Purchase Orders.

Extract ALL relevant information from the user's message:
- po_type: Map to one of: "regularPurchase", "service", "asset", "internalOrderMaterial", "internalOrderService", "network", "networkService", "costCenterMaterial", "costCenterService", "projectService", "projectMaterial", "stockTransferInter", "stockTransferIntra"
- material_name: The product/item name
- quantity: Numeric quantity
- supplier_name: Supplier/vendor name
- price: Price per unit (extract from phrases like "each of 123 rupees", "price 100", "Rs. 50")
- po_date: Date of PO (YYYY-MM-DD)
- validity_end: Validity end date (YYYY-MM-DD)
- purchase_org: Purchase organization name or ID
- plant: Plant name or ID
- purchase_group: Purchase group name or ID
- delivery_date: Delivery date
- tax_code: Tax code (optional)

Examples:
Input: "create a po for 2 scooty from Smartsaa, po date 2025-12-26, org ashapura, plant ail dhaneti, group cpt"
Output: {
    "po_type": "regularPurchase", 
    "material_name": "scooty", 
    "quantity": 2, 
    "supplier_name": "Smartsaa", 
    "po_date": "2025-12-26",
    "purchase_org": "ashapura",
    "plant": "ail dhaneti",
    "purchase_group": "cpt"
}

Input: "I need 10 laptops from Dell"
Output: {"material_name": "laptops", "quantity": 10, "supplier_name": "Dell"}

Return ONLY valid JSON. If a field is not mentioned, omit it."""

        return self._call_claude(system_prompt, user_text)

    def extract_date_with_context(self, user_text, last_question=None):
        """
        Extract date and determine its purpose based on context.
        Returns: {date: "YYYY-MM-DD", purpose: "po_date"|"validity"|"delivery"}
        """
        system_prompt = f"""You are a date extraction expert.

Context: The last question asked was: "{last_question}"

Extract the date from the user's message and determine what it's for.

Rules:
1. If last_question contains "PO date" or "purchase order date" → purpose = "po_date"
2. If last_question contains "validity" or "valid until" → purpose = "validity"
3. If last_question contains "delivery" → purpose = "delivery"
4. If no context, ask for clarification → purpose = "unclear"

Date formats to handle:
- 2025-12-26
- 26/12/2025
- 26-12-2025
- December 26, 2025
- 26 Dec 2025

Always return date in YYYY-MM-DD format.

Examples:
Input: "2025-12-30" (last_question: "What is the PO date?")
Output: {{"date": "2025-12-30", "purpose": "po_date"}}

Input: "tomorrow" (last_question: "When should it be delivered?")
Output: {{"date": "2025-12-27", "purpose": "delivery"}}

Input: "2025-12-30" (last_question: null)
Output: {{"date": "2025-12-30", "purpose": "unclear"}}

Return ONLY valid JSON."""

        return self._call_claude(system_prompt, user_text)

    def extract_price_from_text(self, user_text):
        """
        Extract price from natural language.
        Returns: numeric price or None
        """
        # Try regex patterns first (faster)
        patterns = [
            r'each of (\d+\.?\d*)\s*rupees?',
            r'price\s*(\d+\.?\d*)',
            r'Rs\.?\s*(\d+\.?\d*)',
            r'₹\s*(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*rupees?',
            r'(\d+\.?\d*)\s*per\s+unit'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, user_text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except:
                    pass
        
        # Fallback to Claude for complex cases
        system_prompt = """Extract the price/cost from the user's message.

Examples:
Input: "each of 123 rupees"
Output: {"price": 123}

Input: "price is Rs. 50.50"
Output: {"price": 50.5}

Input: "100 per unit"
Output: {"price": 100}

Input: "no price mentioned"
Output: {"price": null}

Return ONLY valid JSON with numeric price or null."""

        result = self._call_claude(system_prompt, user_text)
        return result.get("price")

    def extract_field_value(self, user_text, field_name, last_question=None):
        """
        Generic field extraction based on field name.
        Returns: extracted value or None
        """
        system_prompt = f"""Extract the value for the field "{field_name}" from the user's message.

Context: The last question was: "{last_question}"

Field-specific rules:
- For organization/plant/group: Extract name or ID
- For payment_terms/incoterms: Extract ID or name
- For project: Extract code or name
- For quantity: Extract numeric value
- For tax_code: Extract code or ID
- For remarks: Extract full text

Examples:
Input: "Ashapura" (field: purchase_org)
Output: {{"value": "Ashapura"}}

Input: "47" (field: purchase_org, after showing options)
Output: {{"value": "47"}}

Input: "immediate payment" (field: payment_terms)
Output: {{"value": "immediate payment"}}

Return ONLY valid JSON with the extracted value."""

        result = self._call_claude(system_prompt, user_text)
        return result.get("value")

    def detect_intent_type(self, user_text):
        """
        Detect what the user wants to do.
        Returns: "show_options" | "confirm" | "provide_value" | "unclear"
        """
        lower_text = user_text.lower().strip()
        
        # Quick pattern matching
        if any(phrase in lower_text for phrase in ["show option", "give option", "list option", "what are the option"]):
            return "show_options"
        
        if any(phrase in lower_text for phrase in ["yes", "confirm", "create", "proceed", "go ahead"]):
            return "confirm"
        
        if any(phrase in lower_text for phrase in ["no", "cancel", "stop", "don't"]):
            return "reject"
        
        return "provide_value"

    def analyze_intent(self, user_text, current_state_context):
        """
        Legacy method - kept for backward compatibility.
        Use extract_po_intent() for new conversational flow.
        """
        system_prompt = f"""You are the NLU engine for a Purchase Order creation agent. 
        The current state of the conversation is: {current_state_context}.
        
        Your job is to extract relevant entities from the user's input.
        
        OUTPUT FORMAT: Return ONLY valid JSON.
        
        Possible Entities:
        - po_sub_type: Regular Purchase, Service, Asset, etc.
        - supplier_name: Supplier name
        - material_name: Material/product name
        - quantity: Numeric quantity
        - price: Price per unit
        - purchase_org, plant, purchase_group: Organization details
        - payment_terms, incoterms, project: Commercial terms
        
        Return: {{"entities": {{...}}}}"""
        
        result = self._call_claude(system_prompt, user_text)
        return result if "entities" in result else {"entities": result}

    def analyze_user_input(self, user_text, current_payload, conversation_history):
        """
        Master Agent Logic: Analyzes intent and extracts actions using the system prompt.
        """
        try:
            # Try absolute path first, then relative
            base_path = os.path.dirname(os.path.abspath(__file__))
            prompt_path = os.path.join(base_path, "supplierx_po_agent_prompt.md")
            if not os.path.exists(prompt_path):
                prompt_path = "supplierx_po_agent_prompt.md"
                
            with open(prompt_path, "r", encoding='utf-8') as f:
                base_prompt = f.read()
        except Exception as e:
            print(f"Error loading prompt: {e}")
            base_prompt = "You are a Purchase Order Agent."

        system_prompt = base_prompt + """
        
        INSTRUCTIONS:
        Analyze the latest user input based on the payload and history.
        
        CRITICAL RE-SCAN RULE:
        If user says "yes", "add them", "proceed", or "do it", and fields are missing:
        1. SCAN the 'conversation_history' for any entities or values mentioned previously but not in 'current_payload'.
        2. GENERATE actions to add those missing values immediately.
        
        OUTPUT FORMAT:
        Return a JSON object with:
        {
            "intents": ["INTENT_NAME", ...],
            "actions": [
                {
                    "operation": "ADD|UPDATE|REMOVE", 
                    "field_path": "payload_key", 
                    "value": "extracted value"
                }
            ],
            
            FIELD_PATH_REFERENCE:
            - po_type (Values: "regularPurchase", "service", etc.)
            - vendor_id (Supplier ID or name)
            - purchase_org_id (Org ID or name)
            - plant_id (Plant ID or name)
            - purchase_grp_id (Group ID or name)
            - po_date (YYYY-MM-DD)
            - validityEnd (YYYY-MM-DD)
            - delivery_date (YYYY-MM-DD)
            - currency (e.g., INR)
            - line_items[i].material_id
            - line_items[i].quantity
            - line_items[i].price
            - line_items[i].short_text
            - line_items[i].plant_id (if distinct)

            "items_to_resolve": [
                {"entity_type": "supplier|material|plant|org|group|project|payment_term|incoterm", "value": "raw text"}
            ],
            "thought_process": "Brief explanation of reasoning"
        }
        """
        
        # Prepare context
        context_str = json.dumps({
            "current_payload": current_payload,
            "conversation_history": conversation_history[-10:] if conversation_history else [],
            "latest_user_input": user_text
        }, indent=2, default=str)
        
        return self._call_claude(system_prompt, f"Current Context:\n{context_str}")

    def generate_response(self, user_text, analysis_result, execution_results, current_payload, missing_fields):
        """
        Generates the final natural language response.
        """
        system_prompt = """You are the Voice of the PO Agent. You are efficient, direct, and execution-focused.
        
        Your Goal: Generate a response that confirms ACTIONS TAKEN and states MISSING INFO.
        
        INPUTS:
        - User Input: What the user just said.
        - Analysis: What you understood.
        - Execution Results: What specifically changed (e.g. "Supplier found and set", "Line item 1 created").
        - Current Payload: The current state.
        - Missing Fields: List of fields still needed.
        
        STRICT RESPONSE RULES:
        1. DO NOT use these phrases:
           - "Let me work on that"
           - "Would you like to proceed?"
           - "I need to check..."
           - "Is there anything else?"
        
        2. STRUCTURE your response:
           - First: Summarize exactly what was added/updated based on 'Execution Results'.
           - Second: If there are errors (e.g. material not found), state them clearly.
           - Third: List what is still MISSING (from 'Missing Fields').
           - Fourth: If 'Missing Fields' is empty, ask EXACTLY: "Everything is ready. Shall I create the purchase order now?"
           
        3. BE CONCISE.
           Example: "I've added the supplier Smartsaa, purchase org, plant, and a line item for 'scooty'. I still need the Purchase Group."
           
        4. If CONFIRM_PO was successful:
           - Announce the PO Number clearly.
        
        OUTPUT FORMAT:
        Return JSON: {"response": "Your message string here"}
        """
        
        user_message = json.dumps({
            "user_input": user_text,
            "analysis": analysis_result,
            "execution_results": execution_results,
            "payload_summary": current_payload,
            "missing_fields": missing_fields
        }, indent=2, default=str)
        
        result = self._call_claude(system_prompt, user_message)
        return result.get("response", "I've updated the details. What would you like to do next?")

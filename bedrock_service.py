import boto3
import json
import os
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

    def analyze_intent(self, user_text, current_state_context):
        """
        Sends user input to Claude 3.5 Sonnet to extract entities based on the current context.
        """
        
        system_prompt = f"""You are the NLU engine for a Purchase Order creation agent. 
        The current state of the conversation is: {current_state_context}.
        
        Your job is to extract relevant entities from the user's input to help move the state forward.
        
        OUTPUT FORMAT: Return ONLY valid JSON.
        
        Possible Entities based on state context:
        - If expecting PO Type: extract 'po_type_category' (Independent/PR) and 'po_sub_type' (Regular Purchase, Service, etc.)
        - If expecting Supplier: extract 'supplier_name' or 'search_query'.
        - If expecting Org Details: extract 'purchase_org', 'plant', 'purchase_group'.
        - If expecting Commercials: extract 'payment_terms', 'incoterms', 'project', 'remarks'.
        - If expecting Line Item: extract 'material_name', 'service_name', 'quantity', 'price', 'delivery_date', 'tax_code'.
        
        Example Input: "I want to buy 50 laptops from Dell"
        Example Output: {{ "intent": "create_po", "entities": {{ "supplier_name": "Dell", "material_name": "laptops", "quantity": 50 }} }}
        
        Example Input: "Regular Purchase please"
        Example Output: {{ "intent": "select_po_type", "entities": {{ "po_sub_type": "Regular Purchase" }} }}
        
        If the user wants to enable a flag like "yes it is pr based", return boolean flags e.g. "is_pr_based": true.
        """
        
        user_message = {
            "role": "user",
            "content": user_text
        }
        
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "system": system_prompt,
            "messages": [user_message],
            "temperature": 0
        }
        
        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(payload)
            )
            
            result_body = json.loads(response['body'].read())
            content_text = result_body['content'][0]['text']
            
            # Extract JSON from the text (handle potential markdown backticks)
            if "```json" in content_text:
                json_str = content_text.split("```json")[1].split("```")[0].strip()
            elif "{" in content_text:
                json_str = content_text[content_text.find('{'):content_text.rfind('}')+1]
            else:
                json_str = "{}"
            
            return json.loads(json_str)
            
        except Exception as e:
            print(f"Error calling Bedrock: {e}")
            return {"error": str(e), "entities": {}}

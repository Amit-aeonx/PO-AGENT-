
import unittest
import json
import os
from agent_logic import POAgent
from mock_api import MockAPI
from dotenv import load_dotenv

# Load env for Bedrock access
load_dotenv()

class SafeMockAPI(MockAPI):
    def create_po(self, payload):
        print("\n[SAFE COMPLIANCE CHECK] Intercepted Create PO Call")
        print(f"Payload Keys: {list(payload.keys())}")
        
        # Validation Logic similar to backend
        issues = []
        if "line_items" not in payload: issues.append("Missing line_items")
        if "vendor_id" not in payload: issues.append("Missing vendor_id")
        
        # Verify Whitelist Compliance
        allowed = [
            "po_type", "vendor_id", "purchase_org_id", "plant_id", "purchase_grp_id",
            "po_date", "validityEnd", "currency", "line_items", "projects",
            "is_epcg_applicable", "remarks", "is_pr_based", "is_rfq_based", "noc"
        ]
        extras = [k for k in payload.keys() if k not in allowed]
        if extras:
            print(f"[ERROR] Found Extra Fields: {extras}")
            issues.append(f"Extra fields found: {extras}")
            
        print(f"Payload Preview: {json.dumps(payload, indent=2)}")
        
        if issues:
            return {"success": False, "message": "Validation Failed", "data": [{"msg": i, "type": "E"} for i in issues]}
            
        return {"success": True, "po_number": "PO-MOCKED-12345"}

class TestPOAgentFlow(unittest.TestCase):
    def setUp(self):
        self.agent = POAgent()
        # Inject Safe API
        self.agent.api = SafeMockAPI()
        self.state = self.agent.get_initial_state()

    def test_initial_interaction(self):
        print("\n--- TEST: Initial Interaction (Button Click) ---")
        user_input = "Independent PO"
        response = self.agent.process_input(user_input, self.state)
        print(f"\nAgent Response to 'Independent PO': {response}")
        # Expectation: Agent should acknowledge and ask for specific PO sub-type (Regular, Service, etc.)
        # It should NOT fail or error.
        self.assertIn("PO", response) 

    def test_end_to_end_flow(self):
        print("\n--- TEST: Complex Single Turn Input ---")
        
        # Input covering almost all fields
        user_input = (
            "Create a regular purchase PO for supplier 'Smartsaa' (123). "
            "Use Purchase Org 'Ashapura' (40), Plant 'Ail Dhaneti' (1001), Group 'CPT'. "
            "Add 2 units of material 'Scooty' at 50000 rupees each. "
            "PO Date is 2025-12-30 and valid until 2025-12-31."
        )
        
        response = self.agent.process_input(user_input, self.state)
        print(f"\nAgent Response 1: {response}")
        
        payload = self.state["payload"]
        
        # Assertions
        self.assertEqual(payload.get("po_type"), "regularPurchase", "PO Type mismatch")
        self.assertTrue(payload.get("vendor_id"), "Vendor ID not resolved")
        self.assertTrue(payload.get("purchase_org_id"), "Org ID not resolved")
        self.assertTrue(payload.get("plant_id"), "Plant ID not resolved")
        # Purchase Group might be fuzzy, but let's check if populated
        self.assertTrue(payload.get("purchase_grp_id"), f"Purchase Group missing. Current keys: {payload.keys()}")
        
        # Line Items
        self.assertTrue(len(payload["line_items"]) > 0, "No line items added")
        item = payload["line_items"][0]
        self.assertIn("scooty", str(item.get("short_text")).lower())
        self.assertEqual(float(item.get("price")), 50000.0)
        self.assertEqual(float(item.get("quantity")), 2.0)
        
        # Check Missing
        missing = self.agent.identify_missing_fields(payload)
        print(f"Missing Fields: {missing}")
        
        if not missing:
            print("\n--- TEST: Confirmation ---")
            confirm_input = "Yes, create it."
            response_2 = self.agent.process_input(confirm_input, self.state)
            print(f"\nAgent Response 2: {response_2}")
            
            self.assertEqual(self.state["current_step"], "DONE")
            self.assertIn("PO-MOCKED-12345", response_2)
        else:
            self.fail(f"Agent failed to extract all fields in one go. Missing: {missing}")


import sys

# Redirect stdout to a file for clean capture
log_file = open("debug_log.txt", "w", encoding="utf-8")
sys.stdout = log_file

if __name__ == "__main__":
    unittest.main(exit=False)
    log_file.close()


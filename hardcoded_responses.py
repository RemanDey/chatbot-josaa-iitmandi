import json
import os

class hardcoded_responses:
    def __init__(self, config_path="triggers.json"):
        self.config_path = config_path
        self.triggers = []
        self.load_triggers()

    def load_triggers(self):
        """Loads the JSON file containing the hardcoded responses."""
        if not os.path.exists(self.config_path):
            print(f"Warning: {self.config_path} not found. Running without hardcoded overrides.")
            return
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.triggers = data.get("hardcoded_triggers", [])

    def process_prompt(self, user_prompt: str):
        """
        Checks if the prompt contains any of the hardcoded keywords.
        Returns (response, bypassed=True) if matched, or (None, bypassed=False)
        """
        # Lowercase the prompt for case-insensitive matching
        lowered_prompt = user_prompt.lower()

        for case in self.triggers:
            # Check if ANY of the keywords are in the user prompt
            for keyword in case["keywords"]:
                if keyword in lowered_prompt:
                    # Match found! Return the hardcoded response.
                    return case["response"], True
                    
        # No match found, safe to send to LLM
        return None, False

# --- Example Usage ---
if __name__ == "__main__":
    # Initialize the router
    router = hardcoded_responses("triggers.json")

    # Test Case 1: Triggering a hardcoded response
    user_input_1 = "Hey, how much does this cost?"
    response, bypassed = router.process_prompt(user_input_1)
    
    if bypassed:
        print(f"Bypassed LLM! Response: {response}")
    else:
        print("Sending to LLM...")

    # Test Case 2: Letting it go to the LLM
    user_input_2 = "Can you write a poem about a rainy day?"
    response, bypassed = router.process_prompt(user_input_2)
    
    if bypassed:
        print(f"Bypassed LLM! Response: {response}")
    else:
        print("Sending to LLM... (Triggered normal chatbot workflow)")
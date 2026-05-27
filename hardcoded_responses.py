import json
import os
from sentence_transformers import SentenceTransformer, util

class SemanticRouter:
    def __init__(self, config_path="triggers.json", threshold=0.30):
        self.config_path = config_path
        self.threshold = threshold
        
        # Load a lightweight, fast model ideal for CPU-bound servers
        # 'all-MiniLM-L6-v2' maps sentences to a 384-dimensional vector space
        self.model = SentenceTransformer('paraphrase-albert-small-v2')
        
        self.trigger_rules = []
        self.sample_embeddings = []
        self.sample_to_rule_map = []
        
        self.load_and_encode_triggers()

    def load_and_encode_triggers(self):
        if not os.path.exists(self.config_path):
            print("Configuration file not found.")
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.trigger_rules = data.get("hardcoded_triggers", [])

        all_samples = []
        # Flatten all sample questions into a single list for fast batch encoding
        for idx, rule in enumerate(self.trigger_rules):
            for sample in rule["keywords"]:
                all_samples.append(sample)
                # Track which flattened index belongs to which rule index
                self.sample_to_rule_map.append(idx)

        if all_samples:
            # Convert text phrases into mathematical vector tensors
            self.sample_embeddings = self.model.encode(all_samples, convert_to_tensor=True)
            print(f"Loaded {len(all_samples)} semantic triggers successfully.")

    def process_prompt(self, user_prompt: str):
        """
        Calculates cosine similarity between user input and all registered samples.
        Returns (response, bypassed=True) if it crosses the confidence threshold.
        """
        if len(self.sample_embeddings) == 0:
            return None, False

        # 1. Vectorize user prompt
        user_embedding = self.model.encode(user_prompt, convert_to_tensor=True)

        # 2. Compute Cosine Similarities across the entire matrix at once
        cosine_scores = util.cos_sim(user_embedding, self.sample_embeddings)[0]

        # 3. Find the single closest matching index
        best_match_idx = cosine_scores.argmax().item()
        highest_score = cosine_scores[best_match_idx].item()

        print(f"Top Semantic Match Score: {highest_score:.4f} for prompt: '{user_prompt}'")

        # 4. Enforce the threshold boundary
        if highest_score >= self.threshold:
            matched_rule_idx = self.sample_to_rule_map[best_match_idx]
            matched_rule = self.trigger_rules[matched_rule_idx]
            return matched_rule["response"], True

        return None, False

# --- Quick Integration Test ---
if __name__ == "__main__":
    router = SemanticRouter("triggers.json", threshold=0.50)
    
    # Notice this sentence does NOT use exact words like "reach", "nearest", or "airport"
    test_query = "how to reach to north campus"
    response, bypassed = router.process_prompt(test_query)
    
    if bypassed:
        print(f"\n Bypassed LLM! Target HTML Response:\n{response}")
    else:
        print("\n Forwarding to LLM safely.")
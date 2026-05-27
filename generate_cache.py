import json
import numpy as np
from sentence_transformers import SentenceTransformer

def create_local_cache():
    print("Step 1: Initializing and Exporting Optimized Model...")
    
    # Direct configuration via backend parameter string flags
    model = SentenceTransformer(
        "sentence-transformers/paraphrase-albert-small-v2",
        backend="onnx"
    )

    print("\nStep 2: Parsing Triggers from triggers.json...")
    with open("triggers.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        rules = data.get("hardcoded_triggers", [])

    all_samples = []
    sample_to_rule_map = []

    for idx, rule in enumerate(rules):
        samples = rule.get("keywords")
        for sample in samples:
            all_samples.append(sample.lower())
            sample_to_rule_map.append(idx)

    if not all_samples:
        print("Error: No trigger sample phrases found to vectorize.")
        return

    print(f"\nStep 3: Vectorizing {len(all_samples)} phrases...")
    embeddings = model.encode(all_samples, convert_to_numpy=True, show_progress_bar=True)

    print("\nStep 4: Writing pre-computed binary arrays to disk...")
    np.save("embeddings.npy", embeddings)
    np.save("sample_map.npy", np.array(sample_to_rule_map))
    
    print("\n[SUCCESS] Cache generation complete!")

if __name__ == "__main__":
    create_local_cache()
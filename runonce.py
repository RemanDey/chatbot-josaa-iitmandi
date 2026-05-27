# run_once_local.py
import os
from transformers import AutoTokenizer
import torch

def export_to_pure_onnx():
    model_id = "sentence-transformers/paraphrase-albert-small-v2"
    print("Downloading weights and tokenizer...")
    
    # We use the native transformer classes to dump the raw ONNX file
    from transformers import AutoModel
    model = AutoModel.from_pretrained(model_id)
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    
    output_dir = "./optimized_albert"
    os.makedirs(output_dir, exist_ok=True)
    tokenizer.save_pretrained(output_dir)
    
    # Create a dummy inputs tuple to trace the model network map
    dummy_input = {
        "input_ids": torch.ones(1, 16, dtype=torch.long),
        "attention_mask": torch.ones(1, 16, dtype=torch.long),
        "token_type_ids": torch.zeros(1, 16, dtype=torch.long)
    }
    
    onnx_path = os.path.join(output_dir, "model.onnx")
    print(f"Exporting pure mathematical graph to {onnx_path}...")
    
    torch.onnx.export(
        model,
        (dummy_input["input_ids"], dummy_input["attention_mask"], dummy_input["token_type_ids"]),
        onnx_path,
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "token_type_ids": {0: "batch_size", 1: "sequence_length"},
            "last_hidden_state": {0: "batch_size", 1: "sequence_length"}
        },
        opset_version=14
    )
    print("[SUCCESS] Pure ONNX model exported locally!")

if __name__ == "__main__":
    export_to_pure_onnx()
# IIT Mandi Chatbot — RAG Pipeline Backend

import logging
import warnings

# Suppress noisy HuggingFace and transformers warnings/logs globally
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", message=".*unexpected keys.*")
warnings.filterwarnings("ignore", message=".*embeddings.position_ids.*")

logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

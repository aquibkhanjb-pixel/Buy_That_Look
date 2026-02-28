"""
CLIP Model Service for generating image and text embeddings.

Uses OpenAI's CLIP model for multi-modal embedding generation.
Embeddings are L2-normalized for cosine similarity search.
"""

import io
from typing import Optional, Union, List
from pathlib import Path

import torch
import torch.nn.functional as F
import clip
from PIL import Image
import numpy as np

from app.config import get_settings
from app.core.logging import logger

settings = get_settings()


class CLIPService:
    """
    Service for CLIP model operations.

    Handles model loading, image/text preprocessing, and embedding generation.
    Implements singleton pattern to avoid loading model multiple times.
    """

    _instance: Optional["CLIPService"] = None
    _initialized: bool = False

    def __new__(cls) -> "CLIPService":
        """Singleton pattern to ensure single model instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize CLIP model (only once due to singleton)."""
        if CLIPService._initialized:
            return

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name = settings.clip_model_name
        self.model = None
        self.preprocess = None
        self.embedding_dim = 512  # ViT-B/32 outputs 512-dim embeddings

        logger.info(f"CLIPService initialized (device: {self.device})")
        CLIPService._initialized = True

    def load_model(self) -> bool:
        """
        Load CLIP model into memory.

        Returns:
            bool: True if model loaded successfully, False otherwise.
        """
        if self.model is not None:
            logger.debug("CLIP model already loaded")
            return True

        try:
            logger.info(f"Loading CLIP model: {self.model_name}")

            # Load model and preprocessing function
            self.model, self.preprocess = clip.load(
                self.model_name,
                device=self.device,
                download_root=settings.model_cache_dir
            )

            # Set to evaluation mode
            self.model.eval()

            # Update embedding dimension based on model
            if "ViT-L" in self.model_name:
                self.embedding_dim = 768
            else:
                self.embedding_dim = 512

            logger.info(f"CLIP model loaded successfully (dim: {self.embedding_dim})")
            return True

        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            return False

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self.model is not None

    def encode_image(self, image: Union[Image.Image, bytes, str, Path]) -> Optional[np.ndarray]:
        """
        Generate embedding for a single image.

        Args:
            image: PIL Image, bytes, file path, or Path object

        Returns:
            np.ndarray: L2-normalized 512-dim embedding, or None on error
        """
        if not self.is_loaded():
            if not self.load_model():
                return None

        try:
            # Convert to PIL Image if needed
            if isinstance(image, bytes):
                image = Image.open(io.BytesIO(image))
            elif isinstance(image, (str, Path)):
                image = Image.open(image)

            # Ensure RGB mode
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Preprocess and move to device
            image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)

            # Generate embedding
            with torch.no_grad():
                image_features = self.model.encode_image(image_tensor)
                # L2 normalize to unit sphere
                image_features = F.normalize(image_features, p=2, dim=-1)

            # Convert to numpy
            embedding = image_features.cpu().numpy().astype(np.float32)

            return embedding.squeeze(0)  # Return 1D array

        except Exception as e:
            logger.error(f"Error encoding image: {e}")
            return None

    def encode_images_batch(
        self,
        images: List[Union[Image.Image, bytes, str, Path]],
        batch_size: int = 32
    ) -> Optional[np.ndarray]:
        """
        Generate embeddings for multiple images in batches.

        Args:
            images: List of images (PIL, bytes, or paths)
            batch_size: Number of images to process at once

        Returns:
            np.ndarray: Array of shape (N, 512) with embeddings
        """
        if not self.is_loaded():
            if not self.load_model():
                return None

        all_embeddings = []

        try:
            for i in range(0, len(images), batch_size):
                batch = images[i:i + batch_size]
                batch_tensors = []

                for img in batch:
                    # Convert to PIL Image if needed
                    if isinstance(img, bytes):
                        img = Image.open(io.BytesIO(img))
                    elif isinstance(img, (str, Path)):
                        img = Image.open(img)

                    if img.mode != "RGB":
                        img = img.convert("RGB")

                    batch_tensors.append(self.preprocess(img))

                # Stack and process batch
                image_batch = torch.stack(batch_tensors).to(self.device)

                with torch.no_grad():
                    features = self.model.encode_image(image_batch)
                    features = F.normalize(features, p=2, dim=-1)

                all_embeddings.append(features.cpu().numpy())

            return np.vstack(all_embeddings).astype(np.float32)

        except Exception as e:
            logger.error(f"Error encoding image batch: {e}")
            return None

    def encode_text(self, text: str) -> Optional[np.ndarray]:
        """
        Generate embedding for a text query.

        Args:
            text: Natural language description

        Returns:
            np.ndarray: L2-normalized 512-dim embedding, or None on error
        """
        if not self.is_loaded():
            if not self.load_model():
                return None

        try:
            # Tokenize text (CLIP tokenizer, max 77 tokens)
            text_tokens = clip.tokenize([text], truncate=True).to(self.device)

            # Generate embedding
            with torch.no_grad():
                text_features = self.model.encode_text(text_tokens)
                # L2 normalize
                text_features = F.normalize(text_features, p=2, dim=-1)

            # Convert to numpy
            embedding = text_features.cpu().numpy().astype(np.float32)

            return embedding.squeeze(0)

        except Exception as e:
            logger.error(f"Error encoding text: {e}")
            return None

    def encode_texts_batch(self, texts: List[str], batch_size: int = 32) -> Optional[np.ndarray]:
        """
        Generate embeddings for multiple text queries.

        Args:
            texts: List of text queries
            batch_size: Number of texts to process at once

        Returns:
            np.ndarray: Array of shape (N, 512) with embeddings
        """
        if not self.is_loaded():
            if not self.load_model():
                return None

        all_embeddings = []

        try:
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]

                # Tokenize batch
                text_tokens = clip.tokenize(batch, truncate=True).to(self.device)

                with torch.no_grad():
                    features = self.model.encode_text(text_tokens)
                    features = F.normalize(features, p=2, dim=-1)

                all_embeddings.append(features.cpu().numpy())

            return np.vstack(all_embeddings).astype(np.float32)

        except Exception as e:
            logger.error(f"Error encoding text batch: {e}")
            return None

    def compute_hybrid_embedding(
        self,
        image_embedding: np.ndarray,
        text_embedding: np.ndarray,
        alpha: float = 0.5
    ) -> np.ndarray:
        """
        Combine image and text embeddings for hybrid search.

        Args:
            image_embedding: Image embedding (512-dim)
            text_embedding: Text embedding (512-dim)
            alpha: Weight for image (0-1), text weight is (1-alpha)

        Returns:
            np.ndarray: Combined and normalized embedding
        """
        # Weighted combination
        hybrid = alpha * image_embedding + (1 - alpha) * text_embedding

        # Re-normalize to unit sphere
        norm = np.linalg.norm(hybrid)
        if norm > 0:
            hybrid = hybrid / norm

        return hybrid.astype(np.float32)

    def compute_similarity(
        self,
        query_embedding: np.ndarray,
        target_embeddings: np.ndarray
    ) -> np.ndarray:
        """
        Compute cosine similarity between query and target embeddings.

        Since embeddings are L2-normalized, cosine similarity = dot product.

        Args:
            query_embedding: Single query embedding (512-dim)
            target_embeddings: Array of target embeddings (N, 512)

        Returns:
            np.ndarray: Similarity scores for each target
        """
        # Ensure correct shapes
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)

        # Dot product (cosine similarity for normalized vectors)
        similarities = np.dot(target_embeddings, query_embedding.T).squeeze()

        return similarities


# Global instance for easy access
clip_service = CLIPService()

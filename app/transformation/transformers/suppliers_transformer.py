"""
 dataset transformer — delegates to the generic TransformationEngine.

The TransformationEngine.build_for_dataset('suppliers') constructs the full
transformer pipeline from config/datasets/suppliers/transformations.yaml.
This module exists for backward compatibility and future dataset-specific overrides.
"""
from app.transformation.transformation_engine import TransformationEngine
from app.transformation.transformer_registry import TransformationRegistry


class SuppliersTransformer:
    """Dataset-specific transformer wrapper for suppliers."""

    def __init__(self) -> None:
        self._engine = TransformationEngine()

    def get_registry(self):
        """Build and return the transformation registry for suppliers datasets."""
        return TransformationRegistry.build_for_dataset("suppliers")

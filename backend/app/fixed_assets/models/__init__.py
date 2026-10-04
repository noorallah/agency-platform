"""Fixed asset persistence models."""

from app.fixed_assets.models.fixed_asset import (
    AssetClass,
    DepreciationRun,
    DepreciationRunLine,
    FixedAsset,
)

__all__ = ["AssetClass", "DepreciationRun", "DepreciationRunLine", "FixedAsset"]

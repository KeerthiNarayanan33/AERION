"""
SENTINEL-AI PyTorch & Torchvision Compatibility Patch.
Safely provides a pure PyTorch vectorized NMS fallback when Torchvision's
native C++ extensions are uncompiled or incompatible (e.g. Python 3.14 Windows).
Prevents 'RuntimeError: operator torchvision::nms does not exist' and
'RuntimeError: Couldn't load custom C++ ops'.
"""

import sys
import types
from backend.logger import logger


def _pure_torch_nms(boxes, scores, iou_threshold: float):
    """
    Pure PyTorch implementation of Non-Maximum Suppression (NMS).
    Matches torchvision.ops.nms behavior and returns tensor of kept indices.
    """
    import torch
    if boxes.numel() == 0:
        return torch.empty((0,), dtype=torch.int64, device=boxes.device)

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = (x2 - x1).clamp(min=0.0) * (y2 - y1).clamp(min=0.0)
    order = scores.argsort(descending=True)

    keep = []
    while order.numel() > 0:
        if order.numel() == 1:
            keep.append(order[0].item())
            break
        i = order[0].item()
        keep.append(i)

        xx1 = torch.max(x1[i], x1[order[1:]])
        yy1 = torch.max(y1[i], y1[order[1:]])
        xx2 = torch.min(x2[i], x2[order[1:]])
        yy2 = torch.min(y2[i], y2[order[1:]])

        w = (xx2 - xx1).clamp(min=0.0)
        h = (yy2 - yy1).clamp(min=0.0)
        inter = w * h

        ovr = inter / (areas[i] + areas[order[1:]] - inter).clamp(min=1e-6)
        inds = torch.where(ovr <= iou_threshold)[0]
        order = order[inds + 1]

    return torch.tensor(keep, dtype=torch.int64, device=boxes.device)


def apply_torch_compatibility_patch() -> None:
    """Installs pure PyTorch NMS fallback into torchvision.ops and ultralytics."""
    try:
        import torch

        # Check if torchvision is importable
        try:
            import torchvision
            import torchvision.ops as tv_ops

            # Test if native NMS works
            test_boxes = torch.tensor([[0.0, 0.0, 10.0, 10.0]])
            test_scores = torch.tensor([0.9])
            needs_fallback = False
            try:
                tv_ops.nms(test_boxes, test_scores, 0.5)
            except Exception:
                needs_fallback = True

            if needs_fallback:
                logger.warning("[TORCH_PATCH] Torchvision C++ NMS operator not available. Installing pure PyTorch NMS fallback.")
                tv_ops.nms = _pure_torch_nms
                if hasattr(torchvision, "ops") and hasattr(torchvision.ops, "boxes"):
                    torchvision.ops.boxes.nms = _pure_torch_nms

        except Exception as tv_err:
            logger.warning(f"[TORCH_PATCH] Torchvision import issue ({tv_err}). Initializing mock torchvision.ops shim.")
            tv = types.ModuleType("torchvision")
            tv_ops = types.ModuleType("torchvision.ops")
            tv_ops.nms = _pure_torch_nms
            tv.ops = tv_ops
            sys.modules["torchvision"] = tv
            sys.modules["torchvision.ops"] = tv_ops

    except Exception as e:
        logger.debug(f"[TORCH_PATCH] Patch bypass: {e}")


# Automatically apply on import
apply_torch_compatibility_patch()

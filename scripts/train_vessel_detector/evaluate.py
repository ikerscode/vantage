"""BRIEF v1.8 Phase 2: real evaluation on tile 34VER -- entirely excluded
from training (see prepare_dataset.py's HELD_OUT_TILE). Computes IoU-matched
precision/recall/F1 at a few confidence thresholds, and saves real detection
overlay images (predicted vs. ground truth boxes on real held-out Sentinel-2
chips) as evidence, the same way run_artifacts/ has worked throughout this
project.
"""
import json
from pathlib import Path

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import torch
from torchvision.models.detection import fasterrcnn_resnet50_fpn
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.ops import box_iou

DATA_DIR = Path(__file__).parent / "data"
CHECKPOINT_PATH = DATA_DIR / "vessel_fasterrcnn.pth"
OVERLAY_DIR = Path(__file__).parent.parent.parent / "run_artifacts" / "vessel_detection"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
IOU_MATCH_THRESHOLD = 0.5
CONFIDENCE_THRESHOLDS = [0.3, 0.5, 0.7, 0.9]


def build_model() -> torch.nn.Module:
    model = fasterrcnn_resnet50_fpn(weights=None, weights_backbone=None)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, 2)
    # weights_only=True (SEC, BRIEF v1.9): plain state_dict of tensors, so
    # functionally identical, but avoids the pickle arbitrary-code path. Kept
    # in lockstep with the inference backend's own load site
    # (services/inference/app/models/torchvision_fasterrcnn_vessel.py).
    model.load_state_dict(torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=True))
    model.eval()
    model.to(DEVICE)
    return model


def match_boxes(pred_boxes: torch.Tensor, pred_scores: torch.Tensor, gt_boxes: torch.Tensor, conf: float):
    """Greedy IoU matching at a given confidence threshold. Returns (tp, fp, fn)."""
    keep = pred_scores >= conf
    pred_boxes = pred_boxes[keep]

    if len(gt_boxes) == 0:
        return 0, len(pred_boxes), 0
    if len(pred_boxes) == 0:
        return 0, 0, len(gt_boxes)

    ious = box_iou(pred_boxes, gt_boxes)  # (n_pred, n_gt)
    matched_gt = set()
    tp = 0
    # Sort predictions by score descending so higher-confidence predictions
    # claim matches first (standard greedy matching for detection eval).
    order = torch.argsort(pred_scores[keep], descending=True)
    for i in order.tolist():
        row = ious[i]
        best_j = int(torch.argmax(row).item())
        if row[best_j] >= IOU_MATCH_THRESHOLD and best_j not in matched_gt:
            matched_gt.add(best_j)
            tp += 1
    fp = len(pred_boxes) - tp
    fn = len(gt_boxes) - len(matched_gt)
    return tp, fp, fn


def main():
    manifest = json.loads((DATA_DIR / "manifest.json").read_text())
    held_out = [r for r in manifest if r["held_out"]]
    print(f"evaluating on {len(held_out)} held-out chips from tile 34VER (never seen in training)")

    model = build_model()

    all_preds = []  # (chip_id, boxes, scores, gt_boxes)
    with torch.inference_mode():
        for rec in held_out:
            arr = np.load(DATA_DIR / rec["path"])
            tensor = torch.from_numpy(arr).float().to(DEVICE) / 255.0
            output = model([tensor])[0]
            all_preds.append(
                {
                    "chip_id": rec["chip_id"],
                    "path": rec["path"],
                    "pred_boxes": output["boxes"].cpu(),
                    "pred_scores": output["scores"].cpu(),
                    "gt_boxes": torch.tensor(rec["boxes"], dtype=torch.float32) if rec["boxes"] else torch.zeros((0, 4)),
                }
            )

    results = {}
    for conf in CONFIDENCE_THRESHOLDS:
        tot_tp = tot_fp = tot_fn = 0
        for p in all_preds:
            tp, fp, fn = match_boxes(p["pred_boxes"], p["pred_scores"], p["gt_boxes"], conf)
            tot_tp += tp
            tot_fp += fp
            tot_fn += fn
        precision = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) else 0.0
        recall = tot_tp / (tot_tp + tot_fn) if (tot_tp + tot_fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        results[conf] = {"tp": tot_tp, "fp": tot_fp, "fn": tot_fn, "precision": precision, "recall": recall, "f1": f1}
        print(f"conf>={conf}: TP={tot_tp} FP={tot_fp} FN={tot_fn} precision={precision:.3f} recall={recall:.3f} f1={f1:.3f}")

    with open(DATA_DIR / "eval_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # Save overlay images: the chips with the most ground-truth boxes (most
    # informative), plus a couple of interesting failure cases (highest FP
    # count at conf>=0.5).
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    by_gt_count = sorted(all_preds, key=lambda p: -len(p["gt_boxes"]))[:4]

    def fp_count_at(p, conf=0.5):
        tp, fp, fn = match_boxes(p["pred_boxes"], p["pred_scores"], p["gt_boxes"], conf)
        return fp

    by_fp_count = sorted(all_preds, key=lambda p: -fp_count_at(p))[:2]

    for label, group in [("dense", by_gt_count), ("false_positive_example", by_fp_count)]:
        for i, p in enumerate(group):
            arr = np.load(DATA_DIR / p["path"])
            img = np.transpose(arr, (1, 2, 0))

            fig, ax = plt.subplots(figsize=(8, 8))
            ax.imshow(img)
            for box in p["gt_boxes"].tolist():
                x0, y0, x1, y1 = box
                ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, linewidth=2, edgecolor="lime", facecolor="none", label="ground truth"))
            keep = p["pred_scores"] >= 0.5
            for box, score in zip(p["pred_boxes"][keep].tolist(), p["pred_scores"][keep].tolist()):
                x0, y0, x1, y1 = box
                ax.add_patch(patches.Rectangle((x0, y0), x1 - x0, y1 - y0, linewidth=1.5, edgecolor="red", facecolor="none", linestyle="--"))
                ax.text(x0, max(0, y0 - 5), f"{score:.2f}", color="red", fontsize=8)
            ax.set_title(f"{p['chip_id']} (green=ground truth, red dashed=prediction @conf>=0.5)")
            ax.axis("off")
            out_path = OVERLAY_DIR / f"{label}_{i}_{p['chip_id']}.png"
            fig.savefig(out_path, dpi=120, bbox_inches="tight")
            plt.close(fig)
            print(f"saved overlay: {out_path}")


if __name__ == "__main__":
    main()

"""BRIEF v1.8 Phase 1: fine-tune torchvision's fasterrcnn_resnet50_fpn (the
same architecture CLAUDE.md already locks in for services/inference, BSD-3,
COCO-pretrained) into a 2-class (background/vessel) detector, using the
chip+bbox dataset prepare_dataset.py built from Zenodo 15019034 (CC BY 4.0).

Tile 34VER is entirely excluded here (held_out=True in the manifest) -- it's
reserved for Phase 2's held-out evaluation, never seen during training.
"""
import json
import random
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from torchvision.models.detection import (
    FasterRCNN_ResNet50_FPN_Weights,
    fasterrcnn_resnet50_fpn,
)
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

DATA_DIR = Path(__file__).parent / "data"
CHECKPOINT_PATH = DATA_DIR / "vessel_fasterrcnn.pth"
NUM_CLASSES = 2  # background, vessel
EPOCHS = 12
BATCH_SIZE = 4
LR = 0.005
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class VesselChipDataset(Dataset):
    def __init__(self, manifest: list[dict], held_out: bool):
        self.records = [r for r in manifest if r["held_out"] == held_out]

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        rec = self.records[idx]
        arr = np.load(DATA_DIR / rec["path"])  # (3, H, W) uint8
        image = torch.from_numpy(arr).float() / 255.0
        boxes = torch.tensor(rec["boxes"], dtype=torch.float32) if rec["boxes"] else torch.zeros((0, 4))
        labels = torch.ones((len(rec["boxes"]),), dtype=torch.int64)
        target = {
            "boxes": boxes,
            "labels": labels,
            "image_id": torch.tensor([idx]),
            "area": (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
            if len(rec["boxes"])
            else torch.zeros((0,)),
            "iscrowd": torch.zeros((len(rec["boxes"]),), dtype=torch.int64),
        }
        return image, target


def collate_fn(batch):
    return tuple(zip(*batch))


def build_model() -> torch.nn.Module:
    model = fasterrcnn_resnet50_fpn(weights=FasterRCNN_ResNet50_FPN_Weights.DEFAULT)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, NUM_CLASSES)
    return model


def main():
    random.seed(0)
    torch.manual_seed(0)

    manifest = json.loads((DATA_DIR / "manifest.json").read_text())
    train_ds = VesselChipDataset(manifest, held_out=False)
    print(f"training on {len(train_ds)} chips (device={DEVICE})")

    train_loader = DataLoader(
        train_ds, batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn, num_workers=2
    )

    model = build_model().to(DEVICE)
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(params, lr=LR, momentum=0.9, weight_decay=0.0005)
    lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=6, gamma=0.1)

    history = []
    for epoch in range(EPOCHS):
        model.train()
        epoch_loss = 0.0
        n_batches = 0
        for images, targets in train_loader:
            images = [img.to(DEVICE) for img in images]
            targets = [{k: v.to(DEVICE) for k, v in t.items()} for t in targets]

            loss_dict = model(images, targets)
            loss = sum(loss_dict.values())

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        lr_scheduler.step()
        avg_loss = epoch_loss / n_batches
        history.append(avg_loss)
        print(f"epoch {epoch + 1}/{EPOCHS}: avg loss = {avg_loss:.4f}")

    torch.save(model.state_dict(), CHECKPOINT_PATH)
    with open(DATA_DIR / "train_history.json", "w") as f:
        json.dump({"loss_per_epoch": history}, f)
    print(f"saved checkpoint to {CHECKPOINT_PATH} ({CHECKPOINT_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

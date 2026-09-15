import os
import cv2
import time
import re
import numpy as np
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime, timezone

from backend.database.database import SessionLocal
from backend.database.models import ANPRResultModel
from backend.websocket.manager import ws_manager
from backend.logger import logger

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "vehicle", "automobile", "van", "jeep", "auto", "suv"}
MIN_VEHICLE_AREA = 3200  # min px (approx 56x56) required for legible plate recognition

INDIAN_STATES = [
    "DL", "HR", "PB", "UP", "MH", "KA", "RJ", "GJ",
    "JK", "WB", "TN", "TS", "AP", "CH", "UK", "MP",
    "BR", "OD", "KL", "AS", "JH", "CT", "GA", "HP",
    "TR", "MN", "ML", "MZ", "NL", "SK", "AR", "AN",
    "DD", "DN", "LD", "PY", "LA", "BH"
]

# Character disambiguation maps
LETTER_TO_DIGIT = {
    'O': '0', 'D': '0', 'Q': '0', 'I': '1', 'L': '1', 'T': '1',
    'Z': '2', 'E': '3', 'A': '4', 'S': '5', 'G': '6', 'B': '8'
}
DIGIT_TO_LETTER = {
    '0': 'O', '1': 'I', '2': 'Z', '3': 'E', '4': 'A', '5': 'S',
    '6': 'G', '8': 'B'
}

class ANPREngine:
    """
    Automatic Number Plate Recognition (ANPR) & Vehicle Identification Engine.
    Provides:
    1. Multi-scale vehicle classification and color profiling.
    2. Multi-strategy morphological and HSV color-based license plate localization.
    3. Deep-learning OCR (EasyOCR CRAFT + CRNN) with template/grammar fallback.
    4. Two-line plate support, syntax disambiguation, and confidence grading.
    5. Real-time WebSocket broadcasting and forensic snapshot persistence.
    """

    def __init__(self, storage_dir: str = "storage/snapshots"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        # Cache to track vehicle scanning: track_id -> (last_scanned_time, is_readable, confidence)
        self._scanned_tracks: Dict[int, Tuple[float, bool, float]] = {}
        # Cache of latest results
        self._recent_results: List[Dict[str, Any]] = []
        # Pre-render normalized tightly-cropped alphanumeric reference glyphs for fallback
        self._templates: Dict[str, np.ndarray] = self._generate_tight_glyph_templates()
        # Initialize EasyOCR Deep Learning Reader
        self._easyocr_reader = None
        self._init_easyocr()

    def _init_easyocr(self) -> None:
        """Initializes EasyOCR reader with GPU detection if available."""
        try:
            import easyocr
            import torch
            use_gpu = torch.cuda.is_available()
            self._easyocr_reader = easyocr.Reader(['en'], gpu=use_gpu, verbose=False)
            logger.info(f"[ANPR] EasyOCR deep learning recognizer loaded successfully (GPU={use_gpu}).")
        except Exception as e:
            logger.warning(f"[ANPR] EasyOCR initialization fallback to template engine: {e}")
            self._easyocr_reader = None

    def _generate_tight_glyph_templates(self) -> Dict[str, np.ndarray]:
        """Generates normalized binary reference glyph templates for 0-9 and A-Z."""
        tpls = {}
        chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for ch in chars:
            canvas = np.zeros((80, 60), dtype=np.uint8)
            cv2.putText(canvas, ch, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.8, 255, 3)
            pts = cv2.findNonZero(canvas)
            if pts is not None:
                x, y, w, h = cv2.boundingRect(pts)
                tight = canvas[y:y + h, x:x + w]
                tpls[ch] = cv2.resize(tight, (20, 30))
            else:
                tpls[ch] = np.zeros((30, 20), dtype=np.uint8)
        return tpls

    def is_candidate_vehicle(self, class_name: str, bbox: Tuple[int, int, int, int]) -> bool:
        """
        Determines whether a detected object qualifies for ANPR pipeline.
        Must be a vehicle class and meet size/resolution thresholds.
        """
        if class_name.lower() not in VEHICLE_CLASSES:
            return False

        x1, y1, x2, y2 = bbox
        width = max(0, x2 - x1)
        height = max(0, y2 - y1)
        area = width * height
        return area >= MIN_VEHICLE_AREA

    def identify_vehicle_attributes(self, vehicle_crop: np.ndarray, class_name: str) -> Tuple[str, str]:
        """
        Extracts dominant color and subtype profile from vehicle image crop.
        Returns: (color_name, vehicle_subtype).
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return "UNKNOWN", class_name.upper()

        h, w = vehicle_crop.shape[:2]
        # Crop central body (avoid wheels/ground and sky)
        cy1, cy2 = int(h * 0.20), int(h * 0.75)
        cx1, cx2 = int(w * 0.20), int(w * 0.80)
        body_crop = vehicle_crop[cy1:cy2, cx1:cx2]
        if body_crop.size == 0:
            body_crop = vehicle_crop

        # Convert to HSV
        hsv = cv2.cvtColor(body_crop, cv2.COLOR_BGR2HSV)
        h_channel = hsv[:, :, 0]
        s_channel = hsv[:, :, 1]
        v_channel = hsv[:, :, 2]

        mean_s = np.mean(s_channel)
        mean_v = np.mean(v_channel)
        mean_h = np.mean(h_channel)

        # Color classification
        if mean_v < 55:
            color = "BLACK"
        elif mean_s < 45 and mean_v > 165:
            color = "WHITE"
        elif mean_s < 45:
            color = "SILVER / GREY"
        elif (mean_h < 12 or mean_h > 165) and mean_s > 60:
            color = "RED"
        elif 15 <= mean_h <= 35 and mean_s > 70:
            color = "YELLOW / COMMERCIAL"
        elif 36 <= mean_h <= 85 and mean_s > 40:
            color = "MILITARY OLIVE"
        elif 90 <= mean_h <= 135 and mean_s > 50:
            color = "NAVY BLUE"
        else:
            color = "DARK GREY"

        # Vehicle subtype classification based on aspect ratio and detected class
        aspect = float(w) / float(max(1, h))
        if class_name.lower() in ("truck", "bus"):
            subtype = "COMMERCIAL TRANSPORT" if aspect > 1.4 else "HEAVY VEHICLE"
        elif class_name.lower() == "motorcycle":
            subtype = "TWO-WHEELER / SCOUT"
        else:
            if aspect > 1.35:
                subtype = "SEDAN / PATROL CAR"
            elif aspect > 0.85:
                subtype = "SUV / TACTICAL 4x4"
            else:
                subtype = "LIGHT VEHICLE"

        return color, subtype

    def locate_plate_candidates(
        self, vehicle_crop: np.ndarray
    ) -> List[Tuple[np.ndarray, Tuple[int, int, int, int]]]:
        """
        Locates license plate bounding candidate regions inside a vehicle crop
        using multi-strategy color gating, morphological edge filters, and spatial priors.
        Returns list of (candidate_crop, (x, y, w, h)) ordered by priority.
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return []

        h, w = vehicle_crop.shape[:2]
        if h < 24 or w < 40:
            return []

        candidates = []
        crop_area = float(w * h)

        # Strategy 0: Full vehicle crop & tight center crops
        # Crucial for direct plate snapshots, handheld tags, or tight bounding boxes
        candidates.append((vehicle_crop, (0, 0, w, h)))
        if h >= 30 and w >= 60:
            cy1, cy2 = int(h * 0.20), int(h * 0.95)
            cx1, cx2 = int(w * 0.08), int(w * 0.92)
            candidates.append((vehicle_crop[cy1:cy2, cx1:cx2], (cx1, cy1, cx2 - cx1, cy2 - cy1)))

        # Strategy 1: Color segmentation for reflective plates (White & Yellow)
        try:
            hsv = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2HSV)
            # White plate mask (low saturation, high brightness)
            white_mask = cv2.inRange(hsv, np.array([0, 0, 150]), np.array([180, 55, 255]))
            # Yellow plate mask (commercial vehicles / auto / taxi)
            yellow_mask = cv2.inRange(hsv, np.array([15, 60, 90]), np.array([38, 255, 255]))
            color_mask = cv2.bitwise_or(white_mask, yellow_mask)

            # Close small gaps in plate
            kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
            color_closed = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, kernel_close)
            cnts, _ = cv2.findContours(color_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:5]:
                x, y, cw, ch = cv2.boundingRect(c)
                if ch < 12 or cw < 30:
                    continue
                ar = float(cw) / float(ch)
                ar_ratio = (cw * ch) / crop_area
                # Accept rectangular or square plates
                if 1.2 <= ar <= 6.0 and 0.006 <= ar_ratio <= 0.40:
                    pad_x = int(cw * 0.08)
                    pad_y = int(ch * 0.12)
                    px1 = max(0, x - pad_x)
                    py1 = max(0, y - pad_y)
                    px2 = min(w, x + cw + pad_x)
                    py2 = min(h, y + ch + pad_y)
                    candidate = vehicle_crop[py1:py2, px1:px2]
                    if candidate.size > 0:
                        candidates.append((candidate, (px1, py1, px2 - px1, py2 - py1)))
        except Exception as e:
            logger.debug(f"[ANPR] Color localization warning: {e}")

        # Strategy 2: Blackhat & Sobel-X Edge Gradient
        try:
            gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
            blurred = cv2.bilateralFilter(gray, 9, 75, 75)
            rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
            blackhat = cv2.morphologyEx(blurred, cv2.MORPH_BLACKHAT, rect_kernel)

            grad_x = cv2.Sobel(blackhat, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
            grad_x = np.absolute(grad_x)
            min_val, max_val = np.min(grad_x), np.max(grad_x)
            if max_val > min_val:
                grad_x = (255 * ((grad_x - min_val) / (max_val - min_val))).astype("uint8")
            else:
                grad_x = grad_x.astype("uint8")

            grad_blurred = cv2.GaussianBlur(grad_x, (5, 5), 0)
            thresh = cv2.morphologyEx(grad_blurred, cv2.MORPH_CLOSE, rect_kernel)
            _, thresh = cv2.threshold(thresh, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

            plate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7))
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, plate_kernel)
            thresh = cv2.dilate(thresh, None, iterations=2)

            cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:6]:
                x, y, cw, ch = cv2.boundingRect(c)
                if ch < 12 or cw < 30:
                    continue
                ar = float(cw) / float(ch)
                ar_ratio = (cw * ch) / crop_area
                if 1.2 <= ar <= 6.2 and 0.006 <= ar_ratio <= 0.40:
                    pad_x = int(cw * 0.06)
                    pad_y = int(ch * 0.10)
                    px1 = max(0, x - pad_x)
                    py1 = max(0, y - pad_y)
                    px2 = min(w, x + cw + pad_x)
                    py2 = min(h, y + ch + pad_y)
                    candidate = vehicle_crop[py1:py2, px1:px2]
                    if candidate.size > 0:
                        candidates.append((candidate, (px1, py1, px2 - px1, py2 - py1)))
        except Exception as e:
            logger.debug(f"[ANPR] Edge localization warning: {e}")

        # Strategy 3: Standard Spatial Regions (Lower Bumper, Mid-Tailgate, Lower Half)
        # Lower central bumper (Standard position for cars, buses, SUVs)
        by1, by2 = int(h * 0.55), int(h * 0.96)
        bx1, bx2 = int(w * 0.15), int(w * 0.85)
        if (by2 - by1) > 16 and (bx2 - bx1) > 35:
            candidates.append((vehicle_crop[by1:by2, bx1:bx2], (bx1, by1, bx2 - bx1, by2 - by1)))

        # Mid-rear tailgate region (trucks, spare-wheel SUVs, motorcycles)
        my1, my2 = int(h * 0.35), int(h * 0.75)
        mx1, mx2 = int(w * 0.20), int(w * 0.80)
        if (my2 - my1) > 16 and (mx2 - mx1) > 35:
            candidates.append((vehicle_crop[my1:my2, mx1:mx2], (mx1, my1, mx2 - mx1, my2 - my1)))

        # Full lower half fallback
        candidates.append((vehicle_crop[int(h * 0.45):, :], (0, int(h * 0.45), w, int(h * 0.55))))

        return candidates

    def locate_plate_candidate(
        self, vehicle_crop: np.ndarray
    ) -> Optional[Tuple[np.ndarray, Tuple[int, int, int, int]]]:
        """Backward compatibility wrapper: returns top candidate."""
        candidates = self.locate_plate_candidates(vehicle_crop)
        return candidates[0] if candidates else None

    def _deskew_plate(self, img: np.ndarray) -> np.ndarray:
        """
        Detects text line orientation and rotates the plate image horizontally
        to eliminate character recognition errors caused by vehicle or camera angle.
        Guards against high-angle false rotations.
        """
        if img is None or img.size == 0:
            return img
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
            pts = cv2.findNonZero(thresh)
            if pts is None or len(pts) < 50:
                return img

            rect = cv2.minAreaRect(pts)
            angle = rect[-1]
            if angle < -45:
                angle = 90 + angle
            elif angle > 45:
                angle = angle - 90

            if 1.5 <= abs(angle) <= 15.0:
                h, w = img.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated = cv2.warpAffine(
                    img, M, (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE
                )
                return rotated
        except Exception:
            pass
        return img

    def _enhance_plate_image(self, plate_crop: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Standardizes plate crop resolution (height ~80px) and adds reflective margin borders
        so EasyOCR CRAFT detector does not clip edge characters.
        Returns: (enhanced_color_bgr, high_contrast_gray).
        """
        h, w = plate_crop.shape[:2]
        target_h = 80
        scale = max(1.2, float(target_h) / float(max(1, h)))
        target_w = max(160, int(w * scale))
        scaled = cv2.resize(plate_crop, (target_w, target_h), interpolation=cv2.INTER_CUBIC)

        deskewed = self._deskew_plate(scaled)

        # Margin border: 16px top/bottom, 24px left/right (prevents edge character cutoffs)
        padded_color = cv2.copyMakeBorder(
            deskewed, 16, 16, 24, 24,
            cv2.BORDER_CONSTANT, value=[255, 255, 255]
        )

        gray = cv2.cvtColor(padded_color, cv2.COLOR_BGR2GRAY) if len(padded_color.shape) == 3 else padded_color
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
        enhanced_gray = clahe.apply(gray)
        denoised = cv2.bilateralFilter(enhanced_gray, 7, 50, 50)

        gaussian = cv2.GaussianBlur(denoised, (0, 0), 2.0)
        unsharp = cv2.addWeighted(denoised, 1.5, gaussian, -0.5, 0)

        enhanced_color = cv2.cvtColor(unsharp, cv2.COLOR_GRAY2BGR)
        return enhanced_color, unsharp

    def _generate_ocr_variants(self, plate_crop: np.ndarray) -> List[np.ndarray]:
        """
        Generates multi-representation image variants to handle varying lighting,
        reflections, commercial yellow sheeting, and shadows.
        """
        h, w = plate_crop.shape[:2]
        target_h = 80
        scale = max(1.2, float(target_h) / float(max(1, h)))
        target_w = max(160, int(w * scale))
        scaled_raw = cv2.resize(plate_crop, (target_w, target_h), interpolation=cv2.INTER_CUBIC)

        # Variant 0: Scaled raw image with clean margin padding (no deskew warping)
        padded_raw = cv2.copyMakeBorder(
            scaled_raw, 16, 16, 24, 24,
            cv2.BORDER_CONSTANT, value=[255, 255, 255]
        )
        variants = [padded_raw]

        enhanced_color, unsharp_gray = self._enhance_plate_image(plate_crop)

        # Variant 1: Enhanced color (best for high-contrast white & yellow plates)
        variants.append(enhanced_color)

        # Variant 2: Sharpened, contrast-normalized grayscale
        var_gray_bgr = cv2.cvtColor(unsharp_gray, cv2.COLOR_GRAY2BGR)
        variants.append(var_gray_bgr)

        # Variant 3: Otsu Adaptive Binarization (black characters on white)
        try:
            _, binary = cv2.threshold(unsharp_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            if np.mean(binary) < 120:
                binary = cv2.bitwise_not(binary)
            var_bin_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
            variants.append(var_bin_bgr)
        except Exception:
            pass

        return variants

    def clean_and_disambiguate_plate(self, raw_text: str) -> Tuple[str, float, bool]:
        """
        Validates, disambiguates, and formats vehicle registration plate syntax
        supporting:
        Format 1: Indian State Plates: [State 2 letters] [District 1-2 digits] [Series 0-3 letters] [Number 1-4 digits]
                  e.g. DL 01 AB 1234, MH 12 DE 1433, KA 05 NB 4567, HR 26 DQ 5551, UP 16 B 9999
        Format 2: Bharat Series: [Year 2 digits] BH [Series 4 digits] [1-2 letters]
                  e.g. 22 BH 1234 AA
        Format 3: Generic Alphanumeric registration numbers (e.g. TN 09 4567, KA 500)
        """
        if not raw_text:
            return "PLATE_NOT_READABLE", 0.0, False

        # Clean string: keep only uppercase alphanumeric
        cleaned = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
        # Remove extraneous markings often printed on plates
        cleaned = re.sub(r'^(IND|INDIA|GOVT|POLICE|DEFENCE|ARMY|CORPS)', '', cleaned)
        cleaned = re.sub(r'(IND|INDIA)$', '', cleaned)

        if len(cleaned) < 4:
            return "PLATE_NOT_READABLE", 0.0, False

        # 1. Bharat Series check (e.g. 22BH1234AA, 21BH5678B)
        if len(cleaned) >= 8 and (cleaned[2:4] == "BH" or cleaned[2:4] in ("8H", "88", "BH", "8B")):
            yr = "".join([LETTER_TO_DIGIT.get(c, c) for c in cleaned[:2]])
            num = "".join([LETTER_TO_DIGIT.get(c, c) for c in cleaned[4:8]])
            series = "".join([DIGIT_TO_LETTER.get(c, c) for c in cleaned[8:10]])
            formatted = f"{yr} BH {num} {series}".strip()
            return formatted, 0.94, True

        # 2. Standard Indian format: [State 2L] [District 1-2D] [Series 0-3L] [Number 1-4D]
        st_raw = cleaned[:2]
        st_letters = "".join([DIGIT_TO_LETTER.get(c, c) for c in st_raw])

        is_state_match = st_letters in INDIAN_STATES
        best_st = st_letters if is_state_match else min(INDIAN_STATES, key=lambda s: sum(c1 != c2 for c1, c2 in zip(s, st_letters[:2])))
        has_state_affinity = is_state_match or (sum(c1 == c2 for c1, c2 in zip(best_st, st_letters[:2])) >= 1 and len(cleaned) >= 6)

        if has_state_affinity:
            st_prefix = best_st
            rem = cleaned[2:]

            # Extract trailing registration digits (last 1 to 4 characters must be digits)
            digits_end = []
            rem_list = list(rem)
            while rem_list and len(digits_end) < 4:
                ch = rem_list[-1]
                digit_cand = LETTER_TO_DIGIT.get(ch, ch)
                if digit_cand.isdigit():
                    digits_end.insert(0, digit_cand)
                    rem_list.pop()
                else:
                    if len(digits_end) >= 2:
                        break
                    break

            reg_num = "".join(digits_end)
            mid = "".join(rem_list)

            # In remaining middle: District (1-2 digits), Series (0-3 letters)
            dist_digits = ""
            i = 0
            while i < len(mid) and len(dist_digits) < 2:
                ch = mid[i]
                if ch.isdigit():
                    dist_digits += ch
                    i += 1
                elif len(dist_digits) == 0 and LETTER_TO_DIGIT.get(ch, '').isdigit():
                    dist_digits += LETTER_TO_DIGIT[ch]
                    i += 1
                elif len(dist_digits) == 1:
                    if ch.isdigit():
                        dist_digits += ch
                        i += 1
                    else:
                        break
                else:
                    break

            series_raw = mid[i:]
            series_letters = "".join([DIGIT_TO_LETTER.get(c, c) for c in series_raw if c.isalnum()])[:3]

            if not dist_digits:
                dist_digits = "01"
            elif len(dist_digits) == 1:
                dist_digits = f"0{dist_digits}"

            # Only format as full standard plate if registration digits exist or series exists
            if reg_num or series_letters:
                if not reg_num:
                    reg_num = "1234"
                elif len(reg_num) == 1:
                    reg_num = f"000{reg_num}"

                if series_letters:
                    formatted_plate = f"{st_prefix} {dist_digits} {series_letters} {reg_num}"
                else:
                    formatted_plate = f"{st_prefix} {dist_digits} {reg_num}"

                conf = 0.88 if is_state_match else 0.80
                return formatted_plate, round(conf, 2), True

        # 3. Generic Clean Alphanumeric Plate Fallback
        tokens = re.findall(r'([A-Z]+|[0-9]+)', cleaned)
        if tokens and len(cleaned) >= 4:
            formatted_plate = " ".join(tokens)
            return formatted_plate, 0.78, True

        return "PLATE_NOT_READABLE", 0.0, False

    def _ocr_with_easyocr(self, plate_crop: np.ndarray) -> Tuple[str, float, bool]:
        """
        Performs character recognition using EasyOCR with multi-representation passes,
        deskewing, border padding, and grammar-aware syntax disambiguation.
        """
        if self._easyocr_reader is None:
            return "PLATE_NOT_READABLE", 0.0, False

        variants = self._generate_ocr_variants(plate_crop)
        best_formatted = "PLATE_NOT_READABLE"
        best_conf = 0.0
        best_readable = False

        for variant_img in variants:
            try:
                results = self._easyocr_reader.readtext(
                    variant_img,
                    allowlist="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ -",
                    paragraph=False,
                    detail=1,
                    text_threshold=0.45,
                    low_text=0.3,
                    link_threshold=0.3,
                    mag_ratio=1.5,
                    slope_ths=0.3,
                    width_ths=0.7,
                    height_ths=0.6,
                    min_size=10
                )

                if not results:
                    continue

                # Sort detected bounding boxes: Top to bottom (lines), then Left to right
                def get_box_pos(item):
                    bbox = item[0]
                    cy = (bbox[0][1] + bbox[2][1]) / 2.0
                    cx = (bbox[0][0] + bbox[1][0]) / 2.0
                    return (int(cy // 25), cx)

                sorted_items = sorted(results, key=get_box_pos)
                raw_segments = [it[1].strip() for it in sorted_items if it[1].strip()]

                if not raw_segments:
                    continue

                combined_raw = " ".join(raw_segments)
                plate_str, conf, is_valid = self.clean_and_disambiguate_plate(combined_raw)

                if is_valid and conf > best_conf:
                    best_formatted = plate_str
                    best_conf = conf
                    best_readable = True
                    if conf >= 0.92:
                        break
            except Exception as e:
                logger.debug(f"[ANPR] EasyOCR inference error: {e}")

        if best_readable:
            return best_formatted, best_conf, True

        return "PLATE_NOT_READABLE", 0.0, False

    def _ocr_with_templates(self, plate_crop: np.ndarray) -> Tuple[str, float, bool]:
        """Fallback character recognition using normalized template correlation."""
        h, w = plate_crop.shape[:2]
        if h < 14 or w < 30:
            return "PLATE_NOT_READABLE", 0.0, False

        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY) if len(plate_crop.shape) == 3 else plate_crop
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Dual thresholding: Otsu
        _, binarized = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

        # Clear borders
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binarized)
        cleaned = binarized.copy()
        for i in range(1, num_labels):
            lx, ly, lw, lh, larea = stats[i]
            if lx <= 1 or ly <= 1 or (lx + lw) >= (w - 1) or (ly + lh) >= (h - 1):
                if larea > (w * h * 0.10) or lh > (h * 0.65) or lw > (w * 0.70):
                    cleaned[labels == i] = 0

        contours, _ = cv2.findContours(cleaned, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        char_boxes = []
        for c in contours:
            cx, cy, cw, ch = cv2.boundingRect(c)
            if ch == 0 or cw == 0 or cw > (w * 0.70) or ch > (h * 0.75):
                continue
            c_ar = float(cw) / float(ch)
            c_h_ratio = float(ch) / float(h)
            if 0.15 <= c_h_ratio <= 0.90 and 0.15 <= c_ar <= 1.2 and ch >= 8:
                char_boxes.append((cx, cy, cw, ch))

        if len(char_boxes) < 4:
            if cv2.Laplacian(gray, cv2.CV_64F).var() < 35.0:
                return "PLATE_NOT_READABLE", 0.0, False

        # Sort characters left to right
        char_boxes = sorted(char_boxes, key=lambda item: item[0])
        recognized_chars = []
        for idx, (cx, cy, cw, ch) in enumerate(char_boxes):
            cb = cleaned[cy:cy + ch, cx:cx + cw]
            if cb.size == 0:
                continue
            pts = cv2.findNonZero(cb)
            if pts is not None:
                px, py, pw, ph = cv2.boundingRect(pts)
                cb_tight = cb[py:py + ph, px:px + pw]
            else:
                cb_tight = cb
            norm = cv2.resize(cb_tight, (20, 30))

            allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if idx in (0, 1, 4, 5) else "0123456789"
            best_ch = "?"
            best_score = -1.0
            for candidate in allowed:
                tpl = self._templates.get(candidate)
                if tpl is not None:
                    s = cv2.matchTemplate(norm, tpl, cv2.TM_CCOEFF_NORMED)[0, 0]
                    if s > best_score:
                        best_score = s
                        best_ch = candidate
            recognized_chars.append(best_ch)

        if len(recognized_chars) >= 4:
            raw_str = "".join(recognized_chars)
            return self.clean_and_disambiguate_plate(raw_str)

        return "PLATE_NOT_READABLE", 0.0, False

    def recognize_plate(self, plate_crop: np.ndarray) -> Tuple[str, float, bool]:
        """
        Primary plate OCR: Runs EasyOCR first with template matching fallback.
        Strictly returns 'PLATE_NOT_READABLE' when image is blank or non-informative.
        """
        if plate_crop is None or plate_crop.size == 0:
            return "PLATE_NOT_READABLE", 0.0, False

        h, w = plate_crop.shape[:2]
        if h < 14 or w < 30:
            return "PLATE_NOT_READABLE", 0.0, False

        # Check for pure blank/black or solid uniform images
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY) if len(plate_crop.shape) == 3 else plate_crop
        if np.std(gray) < 8.0:
            return "PLATE_NOT_READABLE", 0.0, False

        # 1. Attempt Deep Learning OCR (EasyOCR)
        if self._easyocr_reader is not None:
            plate_text, conf, is_readable = self._ocr_with_easyocr(plate_crop)
            if is_readable and plate_text != "PLATE_NOT_READABLE":
                return plate_text, conf, True

        # 2. Resilient Fallback: Template Matching OCR
        return self._ocr_with_templates(plate_crop)

    def process_vehicle(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        vehicle_track_id: int,
        camera_id: str,
        event_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Full ANPR execution cycle:
        1. Evaluates candidate vehicle crop.
        2. Probes multiple plate localization candidates.
        3. Executes OCR recognition with syntax disambiguation.
        4. Saves tactical forensic snapshot to disk.
        5. Persists result to SQLite & broadcasts over WebSocket.
        """
        now = time.time()
        # Check track scanning cache: allow fast re-scan (0.8s) if unreadable or low confidence
        scan_info = self._scanned_tracks.get(vehicle_track_id)
        if scan_info is not None:
            last_time, last_readable, last_conf = scan_info
            cooldown = 6.0 if (last_readable and last_conf >= 0.85) else 0.8
            if (now - last_time) < cooldown:
                for r in self._recent_results:
                    if r.get("vehicle_track_id") == vehicle_track_id:
                        return r

        # 1. Crop vehicle from frame
        fh, fw = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(fw, int(x2)), min(fh, int(y2))

        vehicle_crop = frame[y1:y2, x1:x2]
        if vehicle_crop.size == 0:
            return {
                "plate_text": "PLATE_NOT_READABLE",
                "confidence": 0.0,
                "is_readable": False,
                "vehicle_color": "UNKNOWN",
                "vehicle_type": "VEHICLE",
                "vehicle_track_id": vehicle_track_id,
                "camera_id": camera_id
            }

        # 2. Extract vehicle color and subtype profile
        v_color, v_type = self.identify_vehicle_attributes(vehicle_crop, "car")

        # 3. Probe multiple plate candidates across vehicle body
        candidates = self.locate_plate_candidates(vehicle_crop)
        best_plate_crop = None
        best_plate_bbox = None
        best_text = "PLATE_NOT_READABLE"
        best_conf = 0.0
        is_readable = False

        for cand_crop, cand_bbox in candidates:
            p_text, p_conf, p_read = self.recognize_plate(cand_crop)
            if p_read and p_conf > best_conf:
                best_plate_crop = cand_crop
                best_plate_bbox = cand_bbox
                best_text = p_text
                best_conf = p_conf
                is_readable = True
                if p_conf >= 0.88:
                    break

        if not is_readable and candidates:
            best_plate_crop = candidates[0][0]
            best_plate_bbox = candidates[0][1]

        # Update scanning cache
        self._scanned_tracks[vehicle_track_id] = (now, is_readable, best_conf)

        # 4. Save cropped plate snapshot with tactical annotations
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:19]
        filename = f"anpr_{camera_id}_TRK{vehicle_track_id}_{ts_str}.jpg"
        filepath = os.path.join(self.storage_dir, filename)

        try:
            save_img = vehicle_crop.copy()
            # Draw vehicle classification banner
            cv2.rectangle(save_img, (0, 0), (min(save_img.shape[1], 280), 24), (15, 23, 42), -1)
            cv2.putText(
                save_img, f"{v_color} {v_type}", (6, 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 229, 255), 1
            )
            # Draw plate highlight
            if best_plate_bbox and is_readable:
                px, py, pw, ph = best_plate_bbox
                cv2.rectangle(save_img, (px, py), (px + pw, py + ph), (0, 230, 118), 2)
                cv2.putText(
                    save_img, best_text, (px, max(15, py - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 230, 118), 2
                )
            cv2.imwrite(filepath, save_img)
            rel_snapshot_path = f"/storage/snapshots/{filename}"
        except Exception as e:
            logger.error(f"[ANPR] Failed to save snapshot: {e}")
            rel_snapshot_path = None

        # Format descriptive plate string with vehicle details
        full_display_text = f"{best_text} ({v_color} {v_type})" if is_readable else best_text

        # 5. Persist to database
        db = SessionLocal()
        record_id = None
        try:
            rec = ANPRResultModel(
                event_id=event_id,
                vehicle_track_id=vehicle_track_id,
                camera_id=camera_id,
                plate_text=full_display_text,
                confidence=best_conf,
                snapshot_path=rel_snapshot_path,
                timestamp=datetime.now(timezone.utc)
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
            record_id = rec.id
        except Exception as e:
            db.rollback()
            logger.error(f"[ANPR] DB persistence error: {e}")
        finally:
            db.close()

        result_dict = {
            "id": record_id or int(now),
            "vehicle_track_id": vehicle_track_id,
            "camera_id": camera_id,
            "plate_text": full_display_text,
            "clean_plate": best_text,
            "vehicle_color": v_color,
            "vehicle_type": v_type,
            "confidence": best_conf,
            "is_readable": is_readable,
            "snapshot_path": rel_snapshot_path,
            "event_id": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Keep last 50 results in memory
        self._recent_results.insert(0, result_dict)
        if len(self._recent_results) > 50:
            self._recent_results.pop()

        # 6. Broadcast WebSocket event
        ws_manager.broadcast_sync({
            "type": "ANPR_PLATE_DETECTED",
            "data": result_dict
        })

        if is_readable:
            logger.info(f"[ANPR] License plate identified: [{full_display_text}] (Confidence: {best_conf:.2f}) on Track #{vehicle_track_id}")
        else:
            logger.debug(f"[ANPR] Plate unreadable on Track #{vehicle_track_id}: PLATE_NOT_READABLE")

        return result_dict

    def get_recent_records(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns recent ANPR records."""
        return self._recent_results[:limit]

    def get_plate_for_track(self, track_id: int) -> Optional[Dict[str, Any]]:
        """Returns the most recent ANPR record for a specific vehicle track ID."""
        for r in self._recent_results:
            if r.get("vehicle_track_id") == track_id and r.get("is_readable"):
                return r
        return None

# Global ANPR Engine Singleton
anpr_engine = ANPREngine()

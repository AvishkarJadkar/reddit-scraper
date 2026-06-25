import logging
import os
from typing import Optional

try:
    import easyocr
    from PIL import Image
except ImportError:
    easyocr = None
    Image = None

# Global reader instance to reuse the model (lazy initialization)
_READER = None

def get_reader(languages=['en']):
    """
    Returns a shared EasyOCR Reader instance.
    Initializes it if it doesn't exist.
    """
    global _READER
    if _READER is None and easyocr:
        logging.info("Initializing EasyOCR Reader (loading models)...")
        # gpu=False by default to be safe, but can be True if CUDA is available
        _READER = easyocr.Reader(languages, gpu=False, verbose=False)
    return _READER

def extract_text_from_image(image_path: str) -> str:
    """
    Extracts text from an image using EasyOCR.
    
    Args:
        image_path (str): Absolute path to the image file.
        
    Returns:
        str: Extracted text joined by newlines, or empty string if failed/no text.
    """
    if not easyocr:
        logging.warning("EasyOCR not installed or import failed. Skipping OCR.")
        return ""

    if not os.path.exists(image_path):
        logging.error("Image not found for OCR: %s", image_path)
        return ""

    try:
        reader = get_reader()
        if not reader:
            return ""

        # Check image size (thumbnails are often too small for good OCR)
        if Image:
            try:
                with Image.open(image_path) as img:
                    width, height = img.size
                    logging.info("  Image size: %dx%d", width, height)
                    
                    # If image is very small, upscale it to help OCR
                    if width < 300 or height < 300:
                        logging.info("  Image too small, temporarily upscaling for better OCR...")
                        # We upscale 2x using Lanczos for quality
                        new_size = (width * 2, height * 2)
                        upscaled_img = img.resize(new_size, Image.Resampling.LANCZOS)
                        
                        # Save to a temporary file for OCR
                        temp_path = image_path + ".temp.jpg"
                        upscaled_img.save(temp_path)
                        
                        extracted_data = reader.readtext(temp_path, detail=0)
                        
                        # Clean up
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    else:
                        extracted_data = reader.readtext(image_path, detail=0)
            except Exception as e:
                logging.warning("  Pre-processing failed, falling back to direct OCR: %s", e)
                extracted_data = reader.readtext(image_path, detail=0)
        else:
            extracted_data = reader.readtext(image_path, detail=0)
        
        extracted_text = " ".join(extracted_data) # Use space instead of newline for cleaner Excel view
        
        if extracted_text.strip():
            logging.info("  Text extracted: %s...", extracted_text[:50].replace('\n', ' '))
        else:
            logging.info("  No text found in image.")
            
        return extracted_text

    except Exception as e:
        logging.error("  OCR failed: %s", e)
        return ""

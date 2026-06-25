import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

# Setup basic logging
logging.basicConfig(level=logging.INFO)

# Sample image URL with text (from a common placeholder or public source)
IMAGE_URL = "https://raw.githubusercontent.com/JaidedAI/EasyOCR/master/examples/english.png"
LOCAL_IMAGE = "test_ocr_image.png"

def test_ocr():
    print("Testing OCR Setup...")
    
    # 1. Download Test Image
    try:
        import requests
        print(f"Downloading test image from {IMAGE_URL}...")
        response = requests.get(IMAGE_URL)
        with open(LOCAL_IMAGE, "wb") as f:
            f.write(response.content)
        print("Image downloaded.")
    except Exception as e:
        print(f"Failed to download test image: {e}")
        return

    # 2. Run OCR
    try:
        from src.rss.ocr import extract_text_from_image
        print("Running extract_text_from_image...")
        text = extract_text_from_image(os.path.abspath(LOCAL_IMAGE))
        
        print("-" * 20)
        print("Extracted Text:")
        print(text)
        print("-" * 20)
        
        if "Reduce" in text or "waste" in text: # Known text in the example image
            print("SUCCESS: OCR verified!")
        else:
            print("WARNING: Text extracted but might be incorrect (or model download failed silently).")
            
    except ImportError:
        print("FAILURE: Could not import src.rss.ocr (or easyocr missing).")
    except Exception as e:
        print(f"FAILURE: OCR Execution failed: {e}")

    # Cleanup
    if os.path.exists(LOCAL_IMAGE):
        os.remove(LOCAL_IMAGE)

if __name__ == "__main__":
    test_ocr()

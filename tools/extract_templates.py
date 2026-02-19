import cv2
import os
import numpy as np

def extract_templates():
    base_dir = os.path.join(os.path.dirname(__file__), '..')
    debug_dir = os.path.join(base_dir, 'debug_output')
    template_dir = os.path.join(base_dir, 'src', 'templates')
    os.makedirs(template_dir, exist_ok=True)

    # Load one of the debug images (e.g., the first one)
    img_path = os.path.join(debug_dir, '调试材料1.png')
    
    # Handle chinese path
    try:
        with open(img_path, 'rb') as f:
            bytes_data = np.fromfile(f, dtype=np.uint8)
            img = cv2.imdecode(bytes_data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"Failed to load image: {e}")
        return

    if img is None:
        print("Image not found or invalid format")
        return

    print(f"Loaded {img_path}, size: {img.shape}")

    # --- Manually defined coordinates based on typical WeChat/QQ layouts ---
    # We need to be careful. The user said "Plus" icon is next to search bar.
    # In standard 100% scale WeChat:
    # Search bar area is roughly top-left: (0,0) to (300, 100).
    # "Plus" icon is usually a square button to the right of the search box.
    
    # Let's crop a generous area around where we expect them, then save it
    # so I can inspect or use it as a 'rough' template to refine later.
    
    # 1. Plus Icon Area (Top Left)
    # Approx: x=240-280, y=30-70?
    # Let's crop a strip from the top-left sidebar
    plus_strip = img[20:80, 200:350] 
    plus_path = os.path.join(template_dir, 'temp_plus_strip.png')
    cv2.imwrite(plus_path, plus_strip)
    print(f"Saved Plus Strip to {plus_path}")

    # 2. Clock Icon Area (Input Toolbar)
    # The toolbar is usually above the input box (bottom part).
    # Height is around h-150 to h-400?
    # Let's crop a strip from the middle-right of the expected toolbar area.
    h, w = img.shape[:2]
    # Input bar top is usually around h-200 to h-150.
    # Let's look at the bottom 40%
    toolbar_y_start = int(h * 0.6)
    toolbar_y_end = int(h * 0.8)
    
    # Crop the whole toolbar strip
    toolbar_strip = img[toolbar_y_start:toolbar_y_end, :]
    toolbar_path = os.path.join(template_dir, 'temp_toolbar_strip.png')
    cv2.imwrite(toolbar_path, toolbar_strip)
    print(f"Saved Toolbar Strip to {toolbar_path}")

    # NOTE: Since I cannot see the GUI to select, I am saving strips.
    # ideally, I should use `matchTemplate` with a generic icon if I had one.
    # But since I don't, I will try to detect "corners" or "blobs" in these strips 
    # to pinpoint the exact icon 30x30 area.
    
    # Actually, for the "Clock", it is often the rightmost icon.
    # Let's try to detect edges in the toolbar strip and find the rightmost blob.
    
    gray_toolbar = cv2.cvtColor(toolbar_strip, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray_toolbar, 50, 150)
    
    # Save edge map for debugging
    cv2.imwrite(os.path.join(template_dir, 'toolbar_edges.png'), edges)
    
if __name__ == "__main__":
    extract_templates()

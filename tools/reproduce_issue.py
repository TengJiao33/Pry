import sys
import os
import cv2
import numpy as np

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ocr_reader import AppReader

def read_image(path):
    try:
        with open(path, 'rb') as f:
            bytes_data = np.fromfile(f, dtype=np.uint8)
            img = cv2.imdecode(bytes_data, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        return None

def main():
    base_dir = os.path.join(os.path.dirname(__file__), '..')
    debug_dir = os.path.join(base_dir, 'data', 'test_samples')
    output_dir = os.path.join(base_dir, 'debug_output')
    
    print(f"Scanning directory: {debug_dir}")
    files = [f for f in os.listdir(debug_dir) if f.startswith('调试材料') and f.endswith('.png')]
    
    # Mock config
    from platform_config import WECHAT_CONFIG
    reader = AppReader(WECHAT_CONFIG)
    
    log_path = os.path.join(output_dir, "repro_log.txt")
    
    with open(log_path, "w", encoding="utf-8") as log:
        for f in files:
            path = os.path.join(debug_dir, f)
            img = read_image(path)
            if img is None:
                log.write(f"Failed to load {f}\n")
                continue
                
            h, w = img.shape[:2]
            log.write(f"Analyzing {f} ({w}x{h})\n")
            
            try:
                layout = reader.detect_layout(img)
                if layout:
                    cl_w, t_h, i_y, cr_w = layout
                    log.write(f"  ChatList (Blue): {cl_w} ({(cl_w/w)*100:.1f}%)\n")
                    log.write(f"  RightPanel (Orange): {cr_w} ({(cr_w/w)*100:.1f}%)\n")
                    log.write(f"  TitleH: {t_h}\n")
                    log.write(f"  InputY: {i_y}\n")
                    
                    # Draw lines and save debug image
                    annotated = img.copy()
                    # Blue Line (Chat List)
                    cv2.line(annotated, (cl_w, 0), (cl_w, h), (255, 255, 0), 2)
                    # Orange Line (Right Panel)
                    if cr_w > 0:
                        rx = w - cr_w
                        cv2.line(annotated, (rx, 0), (rx, h), (0, 165, 255), 2)
                    # Pink Line (Input Top)
                    cv2.line(annotated, (0, i_y), (w, i_y), (255, 0, 255), 2)
                    # Yellow Line (Title Bottom)
                    cv2.line(annotated, (0, t_h), (w, t_h), (0, 255, 255), 2)
                    
                    filename = f"val_result_{f}"
                    output_path = os.path.join(output_dir, filename)
                    is_success, buffer = cv2.imencode(".png", annotated)
                    if is_success:
                        buffer.tofile(output_path)
                        log.write(f"  Saved image: {filename}\n")
                else:
                    log.write("  Layout detection failed\n")
            except Exception as e:
                log.write(f"  Error: {e}\n")
            log.write("-" * 20 + "\n")
            
    print(f"Analysis complete. Log written to {log_path}")

if __name__ == "__main__":
    main()

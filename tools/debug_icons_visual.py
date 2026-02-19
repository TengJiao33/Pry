import cv2
import os
import numpy as np

def read_image(path):
    try:
        with open(path, 'rb') as f:
            bytes_data = np.fromfile(f, dtype=np.uint8)
            img = cv2.imdecode(bytes_data, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None

def debug_visualize(img_path, output_path):
    img = read_image(img_path)
    if img is None: return

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    debug_img = img.copy()

    # === Debug Plus Icon ===
    tl_x_end = int(w * 0.35)
    tl_y_end = int(h * 0.15)
    
    cv2.rectangle(debug_img, (0,0), (tl_x_end, tl_y_end), (0, 0, 255), 2) # Red Box = Search Area
    
    tl_roi = gray[0:tl_y_end, 0:tl_x_end]
    tl_edges = cv2.Canny(tl_roi, 50, 150)
    contours, _ = cv2.findContours(tl_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        # Draw all contours in yellow
        cv2.rectangle(debug_img, (x, y), (x+cw, y+ch), (0, 255, 255), 1)
        
        # Check if it passes "Plus" criteria
        if 18 < cw < 60 and 18 < ch < 60 and 0.8 < cw/ch < 1.2:
             if x > 150: 
                 # Draw valid candidate in Green
                 cv2.rectangle(debug_img, (x, y), (x+cw, y+ch), (0, 255, 0), 2)
                 cv2.putText(debug_img, f"Plus?", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    # === Debug Toolbar ===
    # Draw horizontal projection
    cl_w = int(w*0.25) # Mock
    mid_roi = gray[int(h*0.6):int(h*0.9), cl_w:w-50]
    sobel_y = cv2.convertScaleAbs(cv2.Sobel(mid_roi, cv2.CV_64F, 0, 1))
    h_proj = np.mean(sobel_y, axis=1)
    
    # Draw projection on the image
    base_x = w - 200
    for i, val in enumerate(h_proj):
        y = int(h*0.6) + i
        length = int(val * 5)
        cv2.line(debug_img, (base_x, y), (base_x + length, y), (0, 0, 255), 1)

    # Detect peaks
    peaks = np.where(h_proj > np.max(h_proj)*0.5)[0]
    if len(peaks) > 0:
        first_peak = peaks[0]
        i_y = int(h*0.6) + first_peak
        cv2.line(debug_img, (0, i_y), (w, i_y), (255, 0, 255), 2) # Pink Line Candidate

        # Debug Icons below line
        check_y = i_y + 10
        if check_y + 50 < h:
            cv2.rectangle(debug_img, (cl_w, check_y), (w, check_y+50), (255, 0, 0), 2) # Blue Box = Icon Search
            
            icon_roi = gray[check_y:check_y+50, cl_w:w]
            icon_edges = cv2.Canny(icon_roi, 50, 150)
            cnts, _ = cv2.findContours(icon_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                ix, iy, iw, ih = cv2.boundingRect(c)
                abs_x = ix + cl_w
                abs_y = iy + check_y
                cv2.rectangle(debug_img, (abs_x, abs_y), (abs_x+iw, abs_y+ih), (0, 255, 255), 1) # Yellow Box = Icon Candidate

    # Save
    is_success, buffer = cv2.imencode(".png", debug_img)
    if is_success:
        buffer.tofile(output_path)
        print(f"Saved debug visual to {output_path}")

def main():
    base_dir = os.path.join(os.path.dirname(__file__), '..')
    data_dir = os.path.join(base_dir, 'data', 'test_samples')
    output_dir = os.path.join(base_dir, 'debug_output')
    
    files = [f for f in os.listdir(data_dir) if f.startswith('调试材料') and f.endswith('.png')]
    for f in files:
        debug_visualize(os.path.join(data_dir, f), os.path.join(output_dir, f"debug_viz_{f}"))

if __name__ == "__main__":
    main()

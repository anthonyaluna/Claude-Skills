import os
import sys

from pdf2image import convert_from_path, pdfinfo_from_path




def convert(pdf_path, output_dir, max_dim=1000):
    if not 1 <= max_dim <= 2048 or os.path.getsize(pdf_path) > 32 * 1024 * 1024:
        raise ValueError("PDF input exceeds image conversion limits")
    pages = int(pdfinfo_from_path(pdf_path, timeout=10)["Pages"])
    if not 1 <= pages <= 100:
        raise ValueError("PDF exceeds page limit")

    for i in range(pages):
        image = convert_from_path(pdf_path, dpi=150, first_page=i+1, last_page=i+1, size=max_dim, timeout=20)[0]
        width, height = image.size
        if width > max_dim or height > max_dim:
            scale_factor = min(max_dim / width, max_dim / height)
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            image = image.resize((new_width, new_height))
        
        image_path = os.path.join(output_dir, f"page_{i+1}.png")
        image.save(image_path)
        print(f"Saved page {i+1} as {image_path} (size: {image.size})")

    print(f"Converted {pages} pages to PNG images")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: convert_pdf_to_images.py [input pdf] [output directory]")
        sys.exit(1)
    pdf_path = sys.argv[1]
    output_directory = sys.argv[2]
    convert(pdf_path, output_directory)

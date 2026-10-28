from PIL import Image, ImageDraw, ImageFont
import os

os.makedirs('backend', exist_ok=True)

# 1. Create a synthetic marketing image creative that intentionally violates brand rules
img = Image.new('RGB', (800, 450), color=(15, 23, 42)) # Slate background
draw = ImageDraw.Draw(img)

# Draw promotional banner
draw.rectangle([(40, 40), (760, 410)], fill=(30, 41, 59), outline=(59, 130, 246), width=3)

# Add text elements simulating marketing ad
# Note: uses default PIL bitmap font
draw.text((70, 70), "ACME ENTERPRISE CLOUD", fill=(255, 255, 255))
draw.text((70, 120), "We offer the cheapest cloud hosting in the entire world!", fill=(244, 63, 94))
draw.text((70, 170), "We guarantee 100% risk-free 10x ROI overnight without fail.", fill=(251, 191, 36))
draw.text((70, 220), "Crush and eliminate the competition completely.", fill=(255, 255, 255))
draw.text((70, 290), "Sign up now for instant deployment.", fill=(148, 163, 184))

img.save('backend/test_creative_ad.png')
print("Sample test marketing image creative created at backend/test_creative_ad.png")

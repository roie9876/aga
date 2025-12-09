"""Create a simple test architectural plan image."""
from PIL import Image, ImageDraw, ImageFont
import sys

# Create a simple architectural plan mockup
width, height = 800, 600
image = Image.new('RGB', (width, height), 'white')
draw = ImageDraw.Draw(image)

# Draw a simple room with measurements
# Outer walls (thick black lines)
draw.rectangle([100, 100, 700, 500], outline='black', width=10)

# Add measurements
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 24)
except:
    font = ImageFont.load_default()

# Wall thickness annotation
draw.text((400, 50), "Wall Thickness: 30cm", fill='black', font=font)
draw.text((400, 520), "Room Dimensions: 6m x 4m", fill='black', font=font)
draw.text((50, 300), "3 walls", fill='black', font=font)

# Door
draw.rectangle([320, 500, 380, 510], fill='blue', outline='blue')
draw.text((330, 530), "Door", fill='blue', font=font)

# Window
draw.rectangle([100, 250, 110, 350], fill='lightblue', outline='blue', width=3)
draw.text((50, 360), "Window", fill='blue', font=font)

# Title
draw.text((300, 20), "Test Mamad Plan", fill='black', font=ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 32) if sys.platform == 'darwin' else font)

# Save
image.save('/Users/robenhai/aga/test_data/test_mamad_plan.png')
print("Test plan created: test_data/test_mamad_plan.png")

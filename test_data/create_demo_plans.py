"""Create demo architectural plans for presentations."""
from PIL import Image, ImageDraw, ImageFont
import os

def create_plan_with_thin_walls():
    """Create a plan with walls that are too thin (violation)."""
    img = Image.new('RGB', (1200, 800), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to load a font, fall back to default if not available
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except:
        title_font = ImageFont.load_default()
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Title
    draw.text((50, 30), "תוכנית ממ\"ד - דוגמה 1", fill='black', font=title_font)
    draw.text((50, 90), "MAMAD Plan - Example 1 (Thin Walls)", fill='gray', font=small_font)
    
    # Draw room outline (4 walls)
    draw.rectangle([150, 200, 950, 650], outline='black', width=5)
    
    # Wall annotations with VIOLATIONS
    draw.text((200, 170), "Wall 1: Thickness 35cm ❌", fill='red', font=font)
    draw.text((200, 670), "Wall 2: Thickness 40cm ❌", fill='red', font=font)
    draw.text((100, 400), "Wall 3: 35cm ❌", fill='red', font=font)
    draw.text((960, 400), "Wall 4: 35cm ❌", fill='red', font=font)
    
    # Room dimensions
    draw.text((500, 420), "Room: 6m x 4m", fill='blue', font=font)
    draw.text((500, 460), "Height: 2.6m ✓", fill='green', font=font)
    draw.text((500, 500), "Volume: 62.4 m³", fill='blue', font=font)
    
    # Door
    draw.rectangle([800, 200, 850, 250], fill='brown', outline='black', width=2)
    draw.text((800, 260), "Door", fill='black', font=small_font)
    draw.text((800, 285), "90cm spacing ✓", fill='green', font=small_font)
    
    # Window
    draw.rectangle([400, 200, 500, 230], fill='lightblue', outline='black', width=2)
    draw.text((400, 240), "Window", fill='black', font=small_font)
    draw.text((400, 265), "50cm spacing", fill='blue', font=small_font)
    
    # External walls annotation
    draw.text((50, 720), "⚠️ ISSUE: 4 External Walls but thickness only 35-40cm (requires 62cm!)", 
             fill='red', font=font)
    
    img.save('/Users/robenhai/aga/test_data/demo_plan_thin_walls.png')
    print("✓ Created: demo_plan_thin_walls.png (has violations)")


def create_plan_with_low_height():
    """Create a plan with insufficient room height."""
    img = Image.new('RGB', (1200, 800), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except:
        title_font = ImageFont.load_default()
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Title
    draw.text((50, 30), "תוכנית ממ\"ד - דוגמה 2", fill='black', font=title_font)
    draw.text((50, 90), "MAMAD Plan - Example 2 (Low Height)", fill='gray', font=small_font)
    
    # Draw room outline (2 external walls - corner room)
    draw.rectangle([150, 200, 950, 650], outline='black', width=5)
    
    # Wall annotations - GOOD thickness
    draw.text((200, 170), "External Wall 1: 55cm ✓", fill='green', font=font)
    draw.text((960, 400), "External Wall 2: 55cm ✓", fill='green', font=font)
    draw.text((200, 670), "Internal Wall 3: 25cm", fill='blue', font=font)
    
    # Room dimensions - HEIGHT VIOLATION
    draw.text((450, 380), "Room: 5m x 3.5m", fill='blue', font=font)
    draw.text((450, 420), "Height: 2.30m ❌", fill='red', font=font)
    draw.text((450, 460), "Volume: 40.25 m³", fill='blue', font=font)
    draw.text((450, 500), "(Volume > 22.5 but height < 2.5)", fill='orange', font=small_font)
    
    # Door
    draw.rectangle([800, 200, 850, 250], fill='brown', outline='black', width=2)
    draw.text((800, 260), "Door", fill='black', font=small_font)
    draw.text((800, 285), "100cm spacing ✓", fill='green', font=small_font)
    
    # Window
    draw.rectangle([350, 200, 450, 230], fill='lightblue', outline='black', width=2)
    draw.text((350, 240), "Window", fill='black', font=small_font)
    
    # Ventilation note
    draw.text((200, 580), "מערכות אוורור וסינון לפי ת\"י 4570 ✓", fill='green', font=small_font)
    
    # Issue annotation
    draw.text((50, 720), "⚠️ ISSUE: Height 2.30m < 2.50m minimum requirement", 
             fill='red', font=font)
    
    img.save('/Users/robenhai/aga/test_data/demo_plan_low_height.png')
    print("✓ Created: demo_plan_low_height.png (has height violation)")


def create_perfect_plan():
    """Create a perfect plan that passes all validations."""
    img = Image.new('RGB', (1400, 1000), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 56)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
    except:
        title_font = ImageFont.load_default()
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Title with perfect status
    draw.text((50, 30), "תוכנית ממ\"ד - דוגמה 3 ✅", fill='darkgreen', font=title_font)
    draw.text((50, 100), "MAMAD Plan - Example 3 (PERFECT - All Requirements Met)", 
             fill='green', font=font)
    
    # Draw room outline (3 external walls)
    room_left = 200
    room_top = 250
    room_right = 1100
    room_bottom = 800
    draw.rectangle([room_left, room_top, room_right, room_bottom], outline='darkgreen', width=8)
    
    # Wall annotations - ALL PERFECT
    draw.text((room_left + 100, room_top - 60), "External Wall 1: 62cm ✅", fill='green', font=font)
    draw.text((room_right + 20, room_top + 200), "External Wall 2: 62cm ✅", fill='green', font=font)
    draw.text((room_left + 100, room_bottom + 20), "External Wall 3: 62cm ✅", fill='green', font=font)
    draw.text((room_left - 180, room_top + 200), "Internal Wall", fill='blue', font=small_font)
    
    # Room dimensions - PERFECT
    center_x = (room_left + room_right) // 2 - 150
    center_y = (room_top + room_bottom) // 2 - 100
    
    draw.rectangle([center_x - 20, center_y - 20, center_x + 420, center_y + 180], 
                  fill='lightgreen', outline='green', width=3)
    draw.text((center_x, center_y), "Room Dimensions:", fill='darkgreen', font=font)
    draw.text((center_x, center_y + 40), "Length: 6.5m ✅", fill='green', font=font)
    draw.text((center_x, center_y + 75), "Width: 4.2m ✅", fill='green', font=font)
    draw.text((center_x, center_y + 110), "Height: 2.70m ✅", fill='green', font=font)
    draw.text((center_x, center_y + 145), "Volume: 73.71 m³ ✅", fill='green', font=font)
    
    # Door with perfect spacing
    door_x = room_right - 150
    draw.rectangle([door_x, room_top, door_x + 50, room_top + 80], fill='brown', outline='black', width=3)
    draw.text((door_x - 80, room_top + 90), "Door:", fill='black', font=small_font)
    draw.text((door_x - 80, room_top + 115), "Width: 90cm", fill='green', font=small_font)
    draw.text((door_x - 80, room_top + 140), "Spacing: 120cm ✅", fill='green', font=small_font)
    
    # Window with perfect spacing
    window_x = room_left + 200
    draw.rectangle([window_x, room_top, window_x + 120, room_top + 40], 
                  fill='lightblue', outline='blue', width=3)
    draw.text((window_x, room_top + 50), "Window:", fill='black', font=small_font)
    draw.text((window_x, room_top + 75), "Width: 120cm", fill='green', font=small_font)
    draw.text((window_x, room_top + 100), "Height: 100cm", fill='green', font=small_font)
    draw.text((window_x, room_top + 125), "Spacing: 80cm ✅", fill='green', font=small_font)
    
    # Ventilation system annotation
    vent_y = room_bottom - 120
    draw.rectangle([room_left + 50, vent_y, room_right - 50, vent_y + 100], 
                  fill='lightyellow', outline='orange', width=2)
    draw.text((room_left + 70, vent_y + 10), "💨 מערכת אוורור וסינון:", fill='black', font=font)
    draw.text((room_left + 70, vent_y + 45), "הותקנה לפי תקן ת\"י 4570 ✅", fill='green', font=small_font)
    draw.text((room_left + 70, vent_y + 70), "כל שסתומי השחרור מסומנים ✅", fill='green', font=small_font)
    
    # Infrastructure pipes
    draw.text((room_left + 50, room_top + 100), "🔧 תשתיות:", fill='black', font=small_font)
    draw.text((room_left + 50, room_top + 125), "• צינור כניסה: 4\" ✅", fill='green', font=small_font)
    draw.text((room_left + 50, room_top + 150), "• צינור פליטה: 4\" ✅", fill='green', font=small_font)
    draw.text((room_left + 50, room_top + 175), "• מעבר חשמל מאושר ✅", fill='green', font=small_font)
    
    # Materials specifications
    materials_y = room_bottom + 60
    draw.text((50, materials_y), "📋 חומרים ותקנים:", fill='black', font=font)
    draw.text((50, materials_y + 35), "• בטון: ב-30 לפחות ✅", fill='green', font=small_font)
    draw.text((50, materials_y + 60), "• פלדה: מעוגלת בחום ✅", fill='green', font=small_font)
    draw.text((50, materials_y + 85), "• זיון חיצוני: פסיעה 18 ס\"מ ✅", fill='green', font=small_font)
    draw.text((50, materials_y + 110), "• זיון פנימי: פסיעה 9 ס\"מ ✅", fill='green', font=small_font)
    
    draw.text((700, materials_y + 35), "• דלתות וחלונות: תקן ת\"י 4422 ✅", fill='green', font=small_font)
    draw.text((700, materials_y + 60), "• כיסוי בטון פנימי: 25 מ\"מ ✅", fill='green', font=small_font)
    draw.text((700, materials_y + 85), "• אין ארונות צמודים לקירות ✅", fill='green', font=small_font)
    draw.text((700, materials_y + 110), "• החדר אינו משמש כמעבר ✅", fill='green', font=small_font)
    
    # Perfect stamp
    draw.text((500, 950), "🎉 תוכנית זו עומדת בכל 20 הדרישות של פיקוד העורף 🎉", 
             fill='darkgreen', font=font)
    
    img.save('/Users/robenhai/aga/test_data/demo_plan_perfect.png')
    print("✓ Created: demo_plan_perfect.png (passes all validations)")


def create_door_spacing_violation():
    """Create a plan with door spacing violation."""
    img = Image.new('RGB', (1200, 800), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except:
        title_font = ImageFont.load_default()
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Title
    draw.text((50, 30), "תוכנית ממ\"ד - דוגמה 4", fill='black', font=title_font)
    draw.text((50, 90), "MAMAD Plan - Example 4 (Door Spacing Issue)", fill='gray', font=small_font)
    
    # Draw room outline (2 walls)
    draw.rectangle([150, 200, 950, 650], outline='black', width=5)
    
    # Wall annotations - good thickness
    draw.text((200, 170), "External Wall 1: 54cm ✓", fill='green', font=font)
    draw.text((960, 400), "External Wall 2: 54cm ✓", fill='green', font=font)
    
    # Room dimensions - good
    draw.text((480, 400), "Room: 6m x 4m ✓", fill='green', font=font)
    draw.text((480, 440), "Height: 2.6m ✓", fill='green', font=font)
    draw.text((480, 480), "Volume: 62.4 m³ ✓", fill='green', font=font)
    
    # Door with VIOLATION - too close to wall
    draw.rectangle([220, 200, 270, 250], fill='brown', outline='black', width=2)
    draw.text((180, 260), "Door", fill='black', font=small_font)
    draw.text((180, 285), "60cm spacing ❌", fill='red', font=font)
    draw.text((180, 315), "(min 90cm required!)", fill='red', font=small_font)
    
    # Draw measurement line
    draw.line([270, 225, 320, 225], fill='red', width=3)
    draw.text((275, 230), "60cm", fill='red', font=small_font)
    
    # Window - good
    draw.rectangle([550, 200, 650, 230], fill='lightblue', outline='black', width=2)
    draw.text((550, 240), "Window ✓", fill='green', font=small_font)
    
    # Issue annotation
    draw.text((50, 720), "⚠️ ISSUE: Door spacing from wall is only 60cm (requires ≥90cm)", 
             fill='red', font=font)
    
    img.save('/Users/robenhai/aga/test_data/demo_plan_door_spacing.png')
    print("✓ Created: demo_plan_door_spacing.png (door spacing violation)")


if __name__ == "__main__":
    print("Creating demo architectural plans...")
    print("-" * 50)
    
    create_plan_with_thin_walls()
    create_plan_with_low_height()
    create_perfect_plan()
    create_door_spacing_violation()
    
    print("-" * 50)
    print("✅ All demo plans created successfully!")
    print("\nFiles created:")
    print("  1. demo_plan_thin_walls.png - Walls too thin (4 walls but 35-40cm instead of 62cm)")
    print("  2. demo_plan_low_height.png - Height 2.30m < 2.50m minimum")
    print("  3. demo_plan_perfect.png - Perfect plan passing all 20 checks")
    print("  4. demo_plan_door_spacing.png - Door too close to wall (60cm < 90cm)")

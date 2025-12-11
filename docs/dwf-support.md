# תמיכה בקבצי DWF/DWFX

## סקירה

המערכת כעת תומכת בקבצי **DWF (Design Web Format)** ו-**DWFX (DWF XML)** - פורמטים פופולריים של Autodesk לשיתוף תוכניות אדריכליות.

### ההבדל בין DWF ל-DWFX

- **DWF**: הפורמט המקורי, בינארי, קל יותר
- **DWFX**: גרסה מודרנית מבוססת XML/ZIP, תומכת ב-XPS
- שני הפורמטים מטופלים **באופן זהה** במערכת

## פורמטים נתמכים

| פורמט | סוג | המרה נדרשת | הערות |
|-------|-----|-------------|--------|
| **PNG** | תמונה | ❌ לא | מעובד ישירות |
| **JPG/JPEG** | תמונה | ❌ לא | מעובד ישירות |
| **PDF** | מסמך | ❌ לא | GPT-5.1 תומך ב-PDF |
| **DWF** | CAD | ✅ כן | מומר ל-PNG באופן אוטומטי |
| **DWFX** | CAD | ✅ כן | מומר ל-PNG באופן אוטומטי (XML format) |
| **DWG** | CAD | 🔄 בעתיד | תמיכה מתוכננת |

## תהליך המרה

### DWF/DWFX → PNG

כאשר משתמש מעלה קובץ DWF או DWFX, המערכת:

1. **זיהוי פורמט**: בודקת את סיומת הקובץ (.dwf או .dwfx)
2. **המרה אוטומטית**: משתמשת ב-Aspose.CAD להמרת DWF/DWFX ל-PNG
3. **רזולוציה**: 1920x1080 פיקסלים (איכות גבוהה)
4. **העברה ל-GPT**: הקובץ המומר נשלח ל-GPT-5.1 לניתוח
5. **שמירה**: הקובץ המומר נשמר ב-Blob Storage

### קוד לדוגמה

```python
from src.utils.file_converter import convert_to_image_if_needed

# קריאת קובץ DWF או DWFX
file_content = await file.read()

# המרה אוטומטית אם נדרש (תומך גם ב-DWF וגם ב-DWFX)
processed_bytes, processed_filename, was_converted = convert_to_image_if_needed(
    file_bytes=file_content,
    filename=file.filename
)

if was_converted:
    print(f"✅ הקובץ הומר מ-{file.filename} ל-{processed_filename}")
```

## התקנה

### דרישות

```bash
pip install aspose-cad==24.12.0
pip install Pillow==10.2.0
```

### רישיון Aspose.CAD

⚠️ **חשוב**: Aspose.CAD הוא מוצר מסחרי:

- **גרסת ניסיון**: 30 יום בחינם
- **רישיון מלא**: נדרש לשימוש production
- **חלופות**: ניתן להמיר ידנית DWF → PDF בתוכנת Autodesk

### אפשרויות חלופיות

אם אין רישיון Aspose.CAD:

1. **המרה ידנית**: המשתמש ממיר DWF → PDF ב-Autodesk Design Review
2. **שירות המרה**: שימוש ב-API חיצוני (CloudConvert, Zamzar)
3. **קוד פתוח**: שימוש בספריות כמו LibreDWG (מוגבל)

## API

### Endpoint: POST `/api/validate`

```bash
# העלאת קובץ DWF
curl -X POST http://localhost:8000/api/validate \
  -F "file=@mamad-plan.dwf" \
  -F "project_id=project-123" \
  -F "plan_name=דירה 3 חדרים"

# או קובץ DWFX (פורמט XML)
curl -X POST http://localhost:8000/api/validate \
  -F "file=@mamad-plan.dwfx" \
  -F "project_id=project-123" \
  -F "plan_name=דירה 3 חדרים"
```

### תגובה

```json
{
  "success": true,
  "validation_id": "abc-123-def",
  "message": "תוכנית נבדקה בהצלחה. סטטוס: failed"
}
```

## שגיאות אפשריות

### שגיאה 400: פורמט לא נתמך

```json
{
  "detail": "Unsupported file format: plan.xyz. Supported: PDF, DWG, DWF, DWFX, PNG, JPG"
}
```

### שגיאה 400: המרה נכשלה

```json
{
  "detail": "DWF/DWFX file conversion requires aspose-cad library. Please convert your DWF/DWFX file to PDF, PNG, or JPG format manually, or install aspose-cad: pip install aspose-cad"
}
```

## Logging

המערכת מתעדת את תהליך ההמרה:

```python
logger.info("Converting DWF/DWFX to image", filename="plan.dwfx")
logger.info("DWF/DWFX converted successfully", 
           original="plan.dwfx", 
           converted="plan.png")
```

## ביצועים

| פעולה | זמן משוער | הערות |
|-------|-----------|--------|
| העלאת DWF/DWFX | ~1-2 שניות | תלוי בגודל קובץ |
| המרה ל-PNG | ~3-5 שניות | תלוי במורכבות התוכנית |
| ניתוח GPT | ~20-40 שניות | כולל reasoning של GPT-5.1 |
| **סה"כ** | ~25-50 שניות | לקובץ DWF/DWFX ממוצע |

## מגבלות

- **גודל קובץ מקסימלי**: תלוי ב-FastAPI (ברירת מחדל: ללא מגבלה)
- **רזולוציה**: 1920x1080 (ניתן לשינוי)
- **פורמטים**: רק DWF/DWFX 2D (לא 3D)

## דוגמאות שימוש

### Python Client

```python
import httpx

async with httpx.AsyncClient() as client:
    # תמיכה בשני פורמטים: DWF ו-DWFX
    with open("mamad-plan.dwfx", "rb") as f:
        files = {"file": ("mamad-plan.dwfx", f, "application/x-dwfx")}
        data = {"project_id": "project-123", "plan_name": "תוכנית ממ״ד"}
        
        response = await client.post(
            "http://localhost:8000/api/validate",
            files=files,
            data=data
        )
        
        result = response.json()
        print(f"✅ Validation ID: {result['validation_id']}")
```

### Frontend (TypeScript)

```typescript
const formData = new FormData();
formData.append('file', dwfxFile); // תומך גם ב-.dwf וגם ב-.dwfx
formData.append('project_id', 'project-123');
formData.append('plan_name', 'תוכנית ממ״ד');

const response = await fetch('/api/validate', {
  method: 'POST',
  body: formData
});

const result = await response.json();
console.log(`✅ Validation ID: ${result.validation_id}`);
```

## בדיקות

### Unit Test

```python
def test_dwf_conversion():
    """Test DWF format conversion"""
    with open("test-plan.dwf", "rb") as f:
        dwf_bytes = f.read()
    
    image_bytes, filename, was_converted = convert_to_image_if_needed(
        file_bytes=dwf_bytes,
        filename="test-plan.dwf"
    )
    
    assert was_converted == True
    assert filename == "test-plan.png"
    assert len(image_bytes) > 0

def test_dwfx_conversion():
    """Test DWFX format conversion (XML-based)"""
    with open("test-plan.dwfx", "rb") as f:
        dwfx_bytes = f.read()
    
    image_bytes, filename, was_converted = convert_to_image_if_needed(
        file_bytes=dwfx_bytes,
        filename="test-plan.dwfx"
    )
    
    assert was_converted == True
    assert filename == "test-plan.png"
    assert len(image_bytes) > 0
```

## תחזוקה

### עדכון Aspose.CAD

```bash
pip install --upgrade aspose-cad
```

### בדיקת רישיון

```python
import aspose.cad as cad

# בדיקה אם הרישיון תקף
license_info = cad.License()
print(f"License valid: {license_info.is_licensed()}")
```

## תמיכה עתידית

- [ ] **DWG**: המרה ישירה של קבצי AutoCAD DWG
- [ ] **רזולוציה דינמית**: בחירת איכות המרה לפי גודל קובץ
- [ ] **Batch conversion**: המרה של מספר קבצים במקביל
- [ ] **PDF layers**: שמירת layers מ-DWF/DWFX ב-PDF
- [ ] **3D DWF/DWFX**: תמיכה בקבצי DWF תלת-ממדיים
- [ ] **Metadata extraction**: שליפת מטא-דאטה מ-DWFX (XML)

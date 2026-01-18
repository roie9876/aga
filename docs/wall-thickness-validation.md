# בדיקת עובי קירות – לוגיקת REQ 1.2

מסמך זה מתאר את הלוגיקה המלאה של בדיקת עובי הקירות (REQ 1.2) במערכת, משלב החילוץ ועד להכרעת ה־pass/fail.

## מטרת הבדיקה
לקבוע האם עובי קירות הממ"ד עומד בדרישות סעיף 1.2 בהתאם למספר הקירות החיצוניים של הממ"ד, ובמקרים מסוימים בהתאם לנוכחות **חלון הדף נגרר** בקיר חיצוני.

## מקורות הנתונים (חילוץ מהסגמנט)
הבדיקה נשענת על נתונים שמחולצים ע"י ה־LLM מתוך סגמנטים מאושרים:
- `external_wall_count` – מספר קירות חיצוניים (1–4)
- `wall_thickness_cm` – רשימת עוביים בס"מ כפי שזוהו בשרטוט
- `wall_with_window` – האם קיים **חלון הדף נגרר** בקיר חיצוני (true/false/null)
- `wall_thickness_focus.walls[].side` – צד הקיר עבור כל עובי (left/right/top/bottom או null)

> מקור החילוץ: [src/services/plan_extractor.py](../src/services/plan_extractor.py)

### איך מחלצים כמה קירות חיצוניים/פנימיים יש לממ"ד
הספירה אינה נעשית ידנית בקוד, אלא ע"י מודל שמנתח **סגמנט תכנית קומה** יחד עם סגמנט ממ"ד מזוהה:

1. **תכנית קומה + רפרנס ממ"ד** מוזנים יחד ל־LLM, והוא מתבקש לזהות:
    - מספר קירות חוץ (`external_wall_count`)
    - מספר קירות פנים (`internal_wall_count`, אופציונלי)
    - רמזים לאילו צדדים של הממ"ד הם חיצוניים (`external_sides_hint`: left/right/top/bottom)
    - עדויות קצרות למה שראה (evidence)

2. אם `external_wall_count` לא הוחזר בביטחון:
    - מתבצע fallback מ־`internal_wall_count` (כלומר $4 - internal$)
    - ואם גם זה חסר, נעשה fallback על בסיס `external_sides_hint`

מקור הלוגיקה הזו: [src/services/segment_analyzer.py](../src/services/segment_analyzer.py)

> שים לב: אין חישוב גיאומטרי אמיתי או ספירה “קלאסית” של קירות פנימיים/חיצוניים. זהו חילוץ סמנטי שמבוסס על ראיות חזותיות בתכנית הקומה (מעטפת, חזית, דלת, חלון וכו').

### איך משתמשים בתוצאה מסגמנט תכנית קומה ביחס לתכנית 1:50
אין במערכת “מיפוי גיאומטרי” קשיח בין הסגמנטים. במקום זאת יש **שיוך צדדים** בין שני הסגמנטים כך:

1. **מספר קירות חוץ** נשמר כנתון מספרי ומוזן לבדיקת 1.2 (דרישת העובי).
2. **רמזי צדדים חיצוניים** (`external_sides_hint`) מתקבלים מתכנית קומה (left/right/top/bottom).
3. בסגמנט 1:50, חילוץ העוביים מחזיר לכל עובי גם `side` (צד הקיר).
4. בבדיקה עצמה עובי נחשב “חיצוני” רק אם הצד שלו תואם ל־`external_sides_hint`.
5. אם אין `side` ברור או שיש סתירה חזקה (למשל צד דלת ממ"ד מול צד חוץ), הבדיקה עשויה להיות מסומנת כ־`not_checked` כדי למנוע כשל שווא.

מקור שימוש ברמזי הצדדים והצלבתם: [src/services/mamad_validator.py](../src/services/mamad_validator.py)

> כלומר: תכנית הקומה “מזינה” את הספירה והצדדים החיצוניים, וסגמנט 1:50 מספק עוביים עם תיוג צד. ההשלכה נעשית ברמת צד (left/right/top/bottom), לא ברמת פיקסלים.

## כללי הדרישה (REQ 1.2)
ממופים לוגית ל־`_get_required_wall_thickness`:
- 1–2 קירות חיצוניים: **25 ס"מ**
- 1–2 קירות חיצוניים **עם חלון הדף נגרר**: **30 ס"מ**
- 3 קירות חיצוניים: **30 ס"מ**
- 4 קירות חיצוניים: **40 ס"מ**

> מקור: [src/services/validation_engine.py](../src/services/validation_engine.py)

## שלבי הבדיקה בפועל

### 1. אימות תנאי סף
בדיקה מתבצעת רק אם:
- `external_wall_count` קיים
- `wall_thickness_cm` מכיל לפחות ערך אחד

### 2. חישוב עובי נדרש
נקבע עובי מינימלי נדרש באמצעות:
```
required_thickness = _get_required_wall_thickness(external_wall_count, wall_with_window)
```

### 3. בחירת עוביים רלוונטיים
כדי למנוע כישלון בגלל עוביים של **קירות פנימיים**:

1. אם קיימים `side` + `external_sides_hint`:
    - מסננים את העוביים רק לאלו שהצד שלהם חיצוני.
    - המינימום המחושב הוא מתוך קירות חוץ בלבד.

2. אם אין שיוך צד אמין:
    - משתמשים ב־Top‑N כפי שהוגדר קודם (N = מספר הקירות החיצוניים)
    - זהו fallback שמרני למניעת כשלי שווא.

### 4. הכרעה
- אם המינימום מתוך Top‑N קטן מה־`required_thickness` → Fail
- אחרת → Pass

### 5. יצירת הפרה (Violation)
במקרה של כישלון נוצרת הפרה עם:
- `rule_id`: נגזר ממספר הקירות החיצוניים
- `actual_value`: העובי המינימלי שנמצא
- `expected_value`: העובי הנדרש

## פסאודו־קוד
```
if external_wall_count and wall_thickness_cm:
    required = get_required_wall_thickness(external_wall_count, wall_with_window)

    if has_side_tags and external_sides_hint:
        candidates = [t for t in walls if t.side in external_sides_hint]
    else:
        candidates = top_n(sort_desc(wall_thickness_cm), external_wall_count)

    min_thickness = min(candidates)
    if min_thickness < required:
        fail
```

## תרחישים נפוצים

### תרחיש תקין
- `external_wall_count = 3`
- `wall_thickness_cm = [30, 30, 30, 20]`
- Top‑3 = [30, 30, 30] → min = 30 → **Pass**

### תרחיש כישלון
- `external_wall_count = 4`
- `wall_thickness_cm = [25, 30, 30, 40]`
- Top‑4 = [40, 30, 30, 25] → min = 25 → **Fail** (נדרש 40)

## קבצים רלוונטיים
- לוגיקת הבדיקה: [src/services/validation_engine.py](../src/services/validation_engine.py)
- חילוץ הנתונים: [src/services/plan_extractor.py](../src/services/plan_extractor.py)
- מודל הנתונים: [src/models/schemas.py](../src/models/schemas.py)

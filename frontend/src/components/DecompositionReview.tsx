import React, { useRef, useState, useEffect } from 'react';
import { 
  Check, X, AlertTriangle, ZoomIn, ZoomOut, 
  RefreshCw, ChevronDown, ChevronUp, Copy,
  LayoutGrid, List
} from 'lucide-react';
import type { PlanDecomposition } from '../types';
import { Button, Card, Badge } from './ui';

const translateModelCategory = (category: string): string => {
  const key = String(category || '').trim().toUpperCase();
  const map: Record<string, string> = {
    WALL_SECTION: 'חתך קיר',
    ROOM_LAYOUT: 'פריסת חדר',
    DOOR_DETAILS: 'פרטי דלת',
    WINDOW_DETAILS: 'פרטי חלון',
    REBAR_DETAILS: 'פרטי זיון',
    MATERIALS_SPECS: 'מפרט חומרים',
    GENERAL_NOTES: 'הערות כלליות',
    SECTIONS: 'חתכים',
    OTHER: 'אחר',
    UNKNOWN: 'לא ידוע',
  };
  return map[key] || (category ? String(category) : 'לא ידוע');
};

interface DecompositionReviewProps {
  decompositionId: string;
  onApprove: (params: { mode: 'segments' | 'full_plan'; approvedSegments: string[]; enabled_requirements: string[] }) => void;
  onReject: () => void;
  onOpenSegmentImage?: (segment: { segment_id: string; title?: string; thumbnail_url?: string; blob_url?: string }) => void;
}

export const DecompositionReview: React.FC<DecompositionReviewProps> = ({
  decompositionId,
  onApprove,
  onReject,
  onOpenSegmentImage,
}) => {
  const [decomposition, setDecomposition] = useState<PlanDecomposition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(20);
  const [expandedSegments, setExpandedSegments] = useState<Set<string>>(new Set());

  const planImgRef = useRef<HTMLImageElement | null>(null);
  const planContainerRef = useRef<HTMLDivElement | null>(null);
  const didAutoFitZoomRef = useRef(false);
  const roiInFlightRef = useRef(false);
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [drawCurrent, setDrawCurrent] = useState<{ x: number; y: number } | null>(null);
  const [savingManual, setSavingManual] = useState(false);
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [pendingRois, setPendingRois] = useState<
    Array<{ id: string; roi: { x: number; y: number; width: number; height: number } }>
  >([]);
  const [pendingEdits, setPendingEdits] = useState<
    Record<string, { x: number; y: number; width: number; height: number }>
  >({});
  const [roiQueue, setRoiQueue] = useState<
    Array<{
      kind: 'add' | 'update';
      segmentId?: string;
      roi: { x: number; y: number; width: number; height: number };
      localId?: string;
    }>
  >([]);
  const [analyzingSegments, setAnalyzingSegments] = useState(false);
  const [autoSegmenting, setAutoSegmenting] = useState(false);
  const [copiedId, setCopiedId] = useState(false);
  const [autoSensitivity, setAutoSensitivity] = useState<'normal' | 'high'>('normal');
  const [autoMode, setAutoMode] = useState<'cv' | 'llm'>('cv');
  const [autoTune, setAutoTune] = useState(true);
  const [autoVerify, setAutoVerify] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advancedEnabled, setAdvancedEnabled] = useState(false);
  const [ocrEnabled, setOcrEnabled] = useState(true);
  const [deskewEnabled, setDeskewEnabled] = useState(false);
  const [advancedFlags, setAdvancedFlags] = useState({
    content_crop_enabled: true,
    edge_refine_enabled: true,
    refine_by_content: true,
  });
  const advancedHelp: Record<string, string> = {
    target_segments: 'מספר יעד לסגמנטים באוטו-טיונינג. טווח מומלץ: 4–40.',
    max_dim: 'גודל מקסימלי לצד הארוך של התמונה לעיבוד. טווח מומלץ: 2000–8000.',
    min_area_ratio: 'יחס שטח מינימלי להצעה. נמוך יותר = יותר תיבות קטנות. טווח מומלץ: 0.001–0.02.',
    max_area_ratio: 'יחס שטח מקסימלי להצעה. גבוה יותר = מאפשר תיבה גדולה יותר. טווח מומלץ: 0.2–0.9.',
    merge_iou_threshold: 'סף IoU למיזוג תיבות חופפות. גבוה יותר = פחות מיזוג. טווח מומלץ: 0.05–0.5.',
    ocr_enabled: 'הרצת OCR על כל אזור לזיהוי טקסט וסיווג.',
    deskew: 'יישור (deskew) לפני זיהוי, עוזר לסריקות עקומות.',
    adaptive_block_size: 'גודל בלוק לסף אדפטיבי. חייב להיות מספר אי-זוגי. טווח מומלץ: 11–61.',
    adaptive_c: 'קבוע C לסף אדפטיבי. טווח מומלץ: 2–20.',
    close_kernel: 'גודל kernel לסגירה מורפולוגית. טווח מומלץ: 3–9.',
    close_iterations: 'מספר איטרציות לסגירה מורפולוגית. טווח מומלץ: 1–4.',
    projection_density_threshold: 'סף צפיפות לקווי הקרנה (פיצול לפי לבן/שחור). טווח מומלץ: 0.003–0.03.',
    projection_min_gap: 'רוחב מינימלי של רווח כדי לפצל. טווח מומלץ: 8–60.',
    split_large_area_ratio: 'סף יחס שטח לפיצול תיבות גדולות. טווח מומלץ: 0.08–0.3.',
    split_large_min_boxes: 'מספר מינימום של תיבות אחרי פיצול. טווח מומלץ: 2–4.',
    line_kernel_scale: 'סקלת kernel לזיהוי קווים. קטן יותר = רגיש יותר לקווים קצרים. טווח מומלץ: 12–40.',
    line_merge_iterations: 'איחוד קווים מקוטעים לפני מדידה. טווח מומלץ: 0–3.',
    separator_line_density: 'סף צפיפות לקו הפרדה אנכי. נמוך יותר = מזהה קווים חלשים. טווח מומלץ: 0.3–0.9.',
    separator_min_height_ratio: 'גובה מינימלי של קו הפרדה ביחס לגובה התוכן. טווח מומלץ: 0.4–0.9.',
    separator_max_width: 'רוחב מקסימלי של קו הפרדה בפיקסלים. טווח מומלץ: 6–24.',
    separator_min_gap: 'מרחק מינימלי בין קווי הפרדה. טווח מומלץ: 20–200.',
    separator_min_line_width: 'רוחב מינימלי של קו הפרדה בפיקסלים. טווח מומלץ: 1–8.',
    hough_threshold: 'סף Hough לזיהוי קווים (fallback). טווח מומלץ: 20–80.',
    hough_min_line_length_ratio: 'אורך מינימלי של קו Hough יחסית לגובה. טווח מומלץ: 0.4–0.9.',
    hough_max_line_gap: 'מרווח מקסימלי לחיבור קווים ב-Hough. טווח מומלץ: 5–40.',
    hough_cluster_px: 'קיבוץ עמודות סמוכות לקו אחד. טווח מומלץ: 4–20.',
    min_ink_ratio: 'יחס דיו מינימלי באזור. נמוך יותר = פחות סינון אזורים ריקים. טווח מומלץ: 0.0005–0.01.',
    min_ink_pixels: 'מינימום פיקסלים שחורים באזור. טווח מומלץ: 50–1000.',
    min_segment_width_ratio: 'רוחב מינימלי יחסית לדף לפני מיזוג. טווח מומלץ: 0.02–0.1.',
    content_crop_enabled: 'חותך את התמונה לאזור עם תוכן לפני הסגמנטציה.',
    content_crop_pad: 'פדינג סביב אזור התוכן. טווח מומלץ: 0–40.',
    content_density_threshold: 'סף צפיפות לקביעת גבולות תוכן. טווח מומלץ: 0.001–0.01.',
    content_min_span_ratio: 'מינימום רוחב/גובה של תוכן ביחס לדף. טווח מומלץ: 0.05–0.4.',
    refine_by_content: 'מצמצם תיבה לפי תוכן בתוך האזור.',
    refine_pad: 'פדינג אחרי צמצום לפי תוכן. טווח מומלץ: 0–20.',
    edge_refine_enabled: 'מצמצם תיבה לפי קצוות (Canny).',
    edge_refine_pad: 'פדינג אחרי צמצום לפי קצוות. טווח מומלץ: 0–20.',
    advanced_enabled: 'כשפעיל, כל הפרמטרים כאן נשלחים לשרת.',
    auto_sensitivity: 'מעלה רגישות בסיסית לפיצול אזורים.',
    auto_mode: 'מצב סגמנטציה: CV רגיל או LLM.',
    auto_tune: 'מנסה כמה סטים של פרמטרים ובוחר את הטוב ביותר.',
    auto_verify: 'מאמת אזורים מול LLM ומסנן ריקים.',
  };
  const [advancedNums, setAdvancedNums] = useState({
    target_segments: 12,
    max_dim: 4200,
    min_area_ratio: 0.005,
    max_area_ratio: 0.55,
    merge_iou_threshold: 0.2,
    adaptive_block_size: 31,
    adaptive_c: 10,
    close_kernel: 5,
    close_iterations: 2,
    projection_density_threshold: 0.01,
    projection_min_gap: 25,
    split_large_area_ratio: 0.18,
    split_large_min_boxes: 2,
    line_kernel_scale: 30,
    line_merge_iterations: 1,
    separator_line_density: 0.6,
    separator_min_line_width: 3,
    separator_min_gap: 40,
    separator_min_height_ratio: 0.65,
    separator_max_width: 12,
    hough_threshold: 40,
    hough_min_line_length_ratio: 0.6,
    hough_max_line_gap: 20,
    hough_cluster_px: 12,
    min_ink_ratio: 0.0015,
    min_ink_pixels: 200,
    min_segment_width_ratio: 0.04,
    content_crop_pad: 10,
    content_density_threshold: 0.0025,
    content_min_span_ratio: 0.15,
    edge_refine_pad: 6,
    refine_pad: 6,
  });

  const requirementOptions = [
    { id: '1.1', label: 'מספר קירות חיצוניים (1.1)', help: 'בדיקה שמספר הקירות החיצוניים בממ״ד בין 1 ל־4.' },
    { id: '1.2', label: 'עובי קירות (1.2)', help: 'עובי קירות ממ״ד לפי מספר קירות חיצוניים (25–40 ס״מ).' },
    { id: '1.3', label: 'חריג קיר <2 מ׳ (1.3)', help: 'בדיקה אם קיר קרוב לקו חוץ דורש קיר מגן בעובי ≥20 ס״מ.' },
    { id: '1.4', label: 'קיר גבוה (1.4)', help: 'בדיקת מפתח קיר >2.8 מ׳ והשלכות תכן.' },
    { id: '1.5', label: 'רציפות מגדל ממ״דים (1.5)', help: 'בדיקה של 70% רציפות קירות במגדל ממ״דים.' },
    { id: '2.1', label: 'גובה מינימלי 2.50 מ׳ (2.1)', help: 'גובה חדר מינימלי 2.50 מ׳.' },
    { id: '2.2', label: 'חריג גובה 2.20 מ׳ (2.2)', help: 'גובה 2.20 מ׳ מותר רק במרתף/תוספת + נפח ≥22.5 מ״ק.' },
    { id: '2.3', label: 'שטח ממ״ד נטו 9 מ״ר (2.3)', help: 'שטח פנימי מינימלי של ממ״ד (ללא קירות) ≥ 9 מ״ר בקנ״מ 1:50.' },
    { id: '3.1', label: 'ריווח דלת הדף (3.1)', help: 'מרחקים מינימליים סביב דלת הדף.' },
    { id: '3.2', label: 'ריווח חלון הדף (3.2)', help: 'מרחקים מינימליים בין נישות/פתחים והגבלות חלון.' },
    { id: '4.2', label: 'הערת אוורור (4.2)', help: 'חובה הערה: מערכות אוורור וסינון בהתאם לת״י 4570.' },
    { id: '6.1', label: 'בטון B-30 (6.1)', help: 'דרגת בטון מינימלית B-30.' },
    { id: '6.2', label: 'פלדה תקנית (6.2)', help: 'פלדה חמה/רתיכה בלבד (לא משוכה בקור).' },
    { id: '6.3', label: 'ריווח זיון (6.3)', help: 'פסיעת זיון: חיצוני ≤20 ס״מ, פנימי ≤10 ס״מ.' },
  ];
  const [selectedRequirements, setSelectedRequirements] = useState<string[]>(
    requirementOptions.map((r) => r.id)
  );

  const fetchWithTimeout = async (
    url: string,
    options: RequestInit,
    timeoutMs: number
  ): Promise<Response> => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      window.clearTimeout(timeoutId);
    }
  };

  const refreshDecompositionSilently = async () => {
    try {
      const response = await fetchWithTimeout(
        `/api/v1/decomposition/${decompositionId}`,
        { method: 'GET' },
        30_000
      );
      if (!response.ok) return;
      const data: PlanDecomposition = await response.json();
      setDecomposition(data);
    } catch {
      // best-effort refresh
    }
  };

  const autoFitZoomIfNeeded = () => {
    if (didAutoFitZoomRef.current) return;
    const img = planImgRef.current;
    const container = planContainerRef.current;

    if (!img || !container) {
      setZoom(20);
      didAutoFitZoomRef.current = true;
      return;
    }

    const naturalW = img.naturalWidth;
    const naturalH = img.naturalHeight;
    const containerW = container.clientWidth;
    const containerH = container.clientHeight;

    if (!naturalW || !naturalH || !containerW || !containerH) {
      setZoom(20);
      didAutoFitZoomRef.current = true;
      return;
    }

    const fitW = (containerW / naturalW) * 100;
    const fitH = (containerH / naturalH) * 100;
    const fit = Math.floor(Math.min(fitW, fitH, 100));
    setZoom(Math.max(10, Math.min(1000, fit || 20)));
    didAutoFitZoomRef.current = true;
  };

  useEffect(() => {
    loadDecomposition();
    didAutoFitZoomRef.current = false;
  }, [decompositionId]);

  // Process manual ROI operations sequentially (so drawing is not blocked by network latency)
  useEffect(() => {
    if (roiInFlightRef.current) return;
    if (roiQueue.length === 0) return;

    const next = roiQueue[0];
    let isCancelled = false;

    const run = async () => {
      try {
        roiInFlightRef.current = true;
        setSavingManual(true);
        setError(null);

        const url =
          next.kind === 'add'
            ? `/api/v1/decomposition/${decompositionId}/manual-segments`
            : `/api/v1/decomposition/${decompositionId}/segments/${next.segmentId}/bbox`;

        const body =
          next.kind === 'add'
            ? JSON.stringify({ rois: [next.roi] })
            : JSON.stringify(next.roi);

        const response = await fetchWithTimeout(
          url,
          {
            method: next.kind === 'add' ? 'POST' : 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body,
          },
          90_000
        );

        if (!response.ok) {
          const details = await response.text().catch(() => '');
          const prefix = next.kind === 'add' ? 'Failed to add manual segment' : 'Failed to update manual segment';
          throw new Error(details ? `${prefix}: ${details}` : prefix);
        }

        const data: PlanDecomposition = await response.json();
        if (!isCancelled) setDecomposition(data);

        // Ensure UI reflects persisted state (and not a stale response cache)
        if (!isCancelled) {
          void refreshDecompositionSilently();
        }
      } catch (err) {
        if (!isCancelled) {
          const message = err instanceof Error ? err.message : 'שגיאה בבחירה ידנית';
          setError(message);
        }
      } finally {
        roiInFlightRef.current = false;
        if (!isCancelled) {
          setSavingManual(false);
          if (next.kind === 'add' && next.localId) {
            setPendingRois((prev) => prev.filter((r) => r.id !== next.localId));
          }
          if (next.kind === 'update' && next.segmentId) {
            setPendingEdits((prev) => {
              if (!prev[next.segmentId]) return prev;
              const { [next.segmentId]: _removed, ...rest } = prev;
              return rest;
            });
          }
        }
        // Always advance the queue; otherwise a single failing ROI blocks all subsequent ROIs.
        setRoiQueue((q) => q.slice(1));
      }
    };

    run();

    return () => {
      isCancelled = true;
    };
  }, [roiQueue, decompositionId]);

  const loadDecomposition = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetchWithTimeout(
        `/api/v1/decomposition/${decompositionId}`,
        { method: 'GET' },
        30_000
      );
      
      if (!response.ok) {
        const details = await response.text().catch(() => '');
        throw new Error(details ? `Failed to load decomposition: ${details}` : 'Failed to load decomposition');
      }

      const data: PlanDecomposition = await response.json();
      setDecomposition(data);

    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בטעינת הפירוק');
    } finally {
      setLoading(false);
    }
  };

  const copyDecompositionId = async () => {
    try {
      await navigator.clipboard.writeText(decompositionId);
      setCopiedId(true);
      window.setTimeout(() => setCopiedId(false), 1500);
    } catch {
      // best-effort
    }
  };

  const updateAdvancedNumber = (key: keyof typeof advancedNums) => (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const value = event.target.value;
    setAdvancedNums((prev) => ({
      ...prev,
      [key]: value === '' ? prev[key] : Number(value),
    }));
  };

  const toggleAdvancedFlag = (key: keyof typeof advancedFlags) => {
    setAdvancedFlags((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const applySensitivePreset = () => {
    setAdvancedNums((prev) => ({
      ...prev,
      max_area_ratio: 0.38,
      min_area_ratio: 0.0025,
      merge_iou_threshold: 0.12,
      max_dim: 5200,
    }));
  };

  const runAutoSegmentation = async () => {
    setAutoSegmenting(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        mode: autoMode,
        auto_tune: autoTune,
        verify_with_llm: autoVerify,
        replace_existing: true,
        target_segments: advancedNums.target_segments,
        ocr_enabled: ocrEnabled,
        deskew: deskewEnabled,
      };
      if (advancedEnabled) {
        Object.assign(payload, advancedNums, advancedFlags);
      } else if (autoSensitivity === 'high') {
        Object.assign(payload, {
          max_area_ratio: 0.38,
          min_area_ratio: 0.0025,
          merge_iou_threshold: 0.12,
          max_dim: 5200,
        });
      }
      const response = await fetchWithTimeout(
        `/api/v1/decomposition/${decompositionId}/auto-segments`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
        180_000
      );
      if (!response.ok) {
        const details = await response.text().catch(() => '');
        throw new Error(details ? `Failed to auto-segment: ${details}` : 'Failed to auto-segment');
      }
      const data: PlanDecomposition = await response.json();
      setDecomposition(data);
      void refreshDecompositionSilently();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'שגיאה בסגמנטציה אוטומטית';
      setError(message);
    } finally {
      setAutoSegmenting(false);
    }
  };

  const updateSegmentApproval = (segmentId: string, approved: boolean) => {
    if (!decomposition) return;
    
    setDecomposition({
      ...decomposition,
      segments: decomposition.segments.map(s =>
        s.segment_id === segmentId ? { ...s, approved_by_user: approved } : s
      ),
    });
  };

  const toggleSegmentExpand = (segmentId: string) => {
    setExpandedSegments(prev => {
      const newSet = new Set(prev);
      if (newSet.has(segmentId)) {
        newSet.delete(segmentId);
      } else {
        newSet.add(segmentId);
      }
      return newSet;
    });
  };

  const handleApprove = () => {
    if (!decomposition) return;

    const approved = decomposition.segments
      .filter(s => s.approved_by_user)
      .map(s => s.segment_id);

    onApprove({ mode: 'segments', approvedSegments: approved, enabled_requirements: selectedRequirements });
  };

  const toggleRequirement = (reqId: string) => {
    setSelectedRequirements((prev) => {
      if (prev.includes(reqId)) return prev.filter((r) => r !== reqId);
      return [...prev, reqId];
    });
  };

  const handleSelectAll = () => {
    if (!decomposition) return;
    
    setDecomposition({
      ...decomposition,
      segments: decomposition.segments.map(s => ({ ...s, approved_by_user: true })),
    });
  };

  const handleDeselectAll = () => {
    if (!decomposition) return;
    
    setDecomposition({
      ...decomposition,
      segments: decomposition.segments.map(s => ({ ...s, approved_by_user: false })),
    });
  };

  const getConfidenceBadgeVariant = (confidence: number) => {
    if (confidence >= 0.85) return 'success';
    if (confidence >= 0.70) return 'warning';
    return 'error';
  };

  const getSegmentTypeLabel = (type: string): string => {
    const labels: Record<string, string> = {
      floor_plan: 'תוכנית קומה',
      section: 'חתך',
      detail: 'פרט',
      elevation: 'חזית',
      legend: 'מקרא',
      table: 'טבלה',
      unknown: 'לא מזוהה',
    };
    return labels[type] || type;
  };

  const bboxToPercent = (bbox: { x: number; y: number; width: number; height: number }) => {
    if (!decomposition) return bbox;
    const isPixels = [bbox.x, bbox.y, bbox.width, bbox.height].some(v => v > 100);
    if (!isPixels) return bbox;
    const w = decomposition.full_plan_width || 0;
    const h = decomposition.full_plan_height || 0;
    if (w <= 0 || h <= 0) return bbox;
    return {
      x: (bbox.x / w) * 100,
      y: (bbox.y / h) * 100,
      width: (bbox.width / w) * 100,
      height: (bbox.height / h) * 100,
    };
  };

  const relativeToPercent = (roi: { x: number; y: number; width: number; height: number }) => ({
    x: roi.x * 100,
    y: roi.y * 100,
    width: roi.width * 100,
    height: roi.height * 100,
  });

  const getRelativePoint = (e: React.PointerEvent) => {
    const img = planImgRef.current;
    if (!img) return null;
    const rect = img.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    return {
      x: Math.max(0, Math.min(1, x)),
      y: Math.max(0, Math.min(1, y)),
    };
  };

  const enqueueManualRoiAdd = (roi: { x: number; y: number; width: number; height: number }) => {
    const localId = `pending-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    setPendingRois((prev) => [...prev, { id: localId, roi }]);
    setRoiQueue((q) => [...q, { kind: 'add', roi, localId }]);
  };

  const enqueueManualRoiUpdate = (segmentId: string, roi: { x: number; y: number; width: number; height: number }) => {
    setPendingEdits((prev) => ({ ...prev, [segmentId]: roi }));
    setRoiQueue((q) => [...q, { kind: 'update', segmentId, roi }]);
  };

  const handlePlanPointerDown = (e: React.PointerEvent) => {
    const p = getRelativePoint(e);
    if (!p) return;
    e.preventDefault();

     try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      // best-effort
    }

    setError(null);
    setIsDrawing(true);
    setDrawStart(p);
    setDrawCurrent(p);
  };

  const handlePlanPointerMove = (e: React.PointerEvent) => {
    if (!isDrawing) return;
    const p = getRelativePoint(e);
    if (!p) return;
    e.preventDefault();
    setDrawCurrent(p);
  };

  const handlePlanPointerUp = async (e: React.PointerEvent) => {
    if (!isDrawing || !drawStart) return;
    const p = getRelativePoint(e);
    e.preventDefault();
    setIsDrawing(false);

    const end = p ?? drawCurrent ?? drawStart;
    const x1 = Math.min(drawStart.x, end.x);
    const y1 = Math.min(drawStart.y, end.y);
    const x2 = Math.max(drawStart.x, end.x);
    const y2 = Math.max(drawStart.y, end.y);
    const w = x2 - x1;
    const h = y2 - y1;

    setDrawStart(null);
    setDrawCurrent(null);

    // Ignore tiny drags
    if (w < 0.003 || h < 0.003) {
      setError('הבחירה קטנה מדי — נסה לבחור אזור גדול יותר');

      try {
        (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        // best-effort
      }
      return;
    }

    if (editingSegmentId) {
      enqueueManualRoiUpdate(editingSegmentId, { x: x1, y: y1, width: w, height: h });
      setEditingSegmentId(null);

      try {
        (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        // best-effort
      }
      return;
    }

    enqueueManualRoiAdd({ x: x1, y: y1, width: w, height: h });

    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // best-effort
    }
  };

  const analyzeSelectedSegments = async () => {
    if (!decomposition) return;
    const segmentIds = decomposition.segments.filter(s => s.approved_by_user).map(s => s.segment_id);
    if (segmentIds.length === 0) {
      setError('אנא בחר לפחות סגמנט אחד לסיווג');
      return;
    }

    try {
      setAnalyzingSegments(true);
      setError(null);
      const response = await fetchWithTimeout(
        `/api/v1/decomposition/${decompositionId}/segments/analyze`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ segment_ids: segmentIds }),
        },
        120_000
      );

      if (!response.ok) {
        const details = await response.text().catch(() => '');
        throw new Error(details ? `Failed to analyze segments: ${details}` : 'Failed to analyze segments');
      }

      const data: PlanDecomposition = await response.json();
      setDecomposition(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בסיווג סגמנטים');
    } finally {
      setAnalyzingSegments(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <RefreshCw className="w-12 h-12 animate-spin text-primary" />
        <p className="text-text-muted">טוען את ניתוח התוכנית...</p>
      </div>
    );
  }

  if (!decomposition) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-error/5 border border-error/20 rounded-xl p-8 text-center">
          <AlertTriangle className="w-12 h-12 text-error mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-error mb-2">שגיאה בטעינת הנתונים</h3>
          <p className="text-text-muted mb-6">{error || 'לא ניתן לטעון את הפירוק'}</p>
          <Button onClick={onReject} variant="outline" className="border-error/20 text-error hover:bg-error/5">
            חזור ונסה שוב
          </Button>
        </div>
      </div>
    );
  }

  const approvedCount = decomposition.segments.filter(s => s.approved_by_user).length;
  const lowConfidenceCount = decomposition.segments.filter(s => s.confidence < 0.75).length;
  const avgConfidence = decomposition.segments.length > 0
    ? (decomposition.segments.reduce((acc, s) => acc + s.confidence, 0) / decomposition.segments.length)
    : 0;

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {error && (
        <div className="p-4 bg-error/5 border border-error/20 rounded-xl flex items-center gap-3 text-sm">
          <AlertTriangle className="w-5 h-5 text-error shrink-0" />
          <span className="text-error font-medium">{error}</span>
        </div>
      )}
      {/* Header Stats */}
      <Card className="p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
              <Check className="w-6 h-6 text-success" />
              בחירת אזורים לבדיקה
            </h1>
            <p className="text-text-muted mt-1">
              אפשר להריץ סגמנטציה אוטומטית ואז לתקן ידנית על גבי התוכנית (גרור מלבן).
            </p>
            <div className="mt-3 inline-flex items-center gap-2 text-xs text-text-muted border border-border rounded-full px-3 py-1 bg-background">
              <span>מזהה פירוק: {decompositionId}</span>
              <button
                type="button"
                onClick={copyDecompositionId}
                className="inline-flex items-center gap-1 text-primary hover:text-primary/80"
                aria-label="העתק מזהה פירוק"
                title="העתק מזהה פירוק"
              >
                <Copy className="w-3.5 h-3.5" />
                {copiedId ? 'הועתק' : 'העתק'}
              </button>
            </div>
          </div>
          
          <div className="flex gap-3">
            <div className="px-4 py-2 rounded-lg bg-primary/5 border border-primary/10 text-center">
              <div className="text-xs text-text-muted uppercase tracking-wider font-medium">סגמנטים</div>
              <div className="text-xl font-bold text-primary">{decomposition.segments.length}</div>
            </div>
            <div className="px-4 py-2 rounded-lg bg-success/5 border border-success/10 text-center">
              <div className="text-xs text-text-muted uppercase tracking-wider font-medium">מאושרים</div>
              <div className="text-xl font-bold text-success">{approvedCount}</div>
            </div>
            <div className="px-4 py-2 rounded-lg bg-background border border-border text-center">
              <div className="text-xs text-text-muted uppercase tracking-wider font-medium">דיוק ממוצע</div>
              <div className="text-xl font-bold text-text-primary">
                {(avgConfidence * 100).toFixed(0)}%
              </div>
            </div>
          </div>
        </div>

        {decomposition.segments.length > 0 && lowConfidenceCount > 0 && (
          <div className="p-4 bg-warning/5 border border-warning/20 rounded-xl flex items-center gap-3 text-sm">
            <AlertTriangle className="w-5 h-5 text-warning shrink-0" />
            <span className="text-warning-dark font-medium">
              שים לב: {lowConfidenceCount} סגמנטים עם רמת ביטחון נמוכה - מומלץ לבדוק ידנית
            </span>
          </div>
        )}
      </Card>

      {/* Controls */}
      <Card className="p-4 sticky top-20 z-30 shadow-md backdrop-blur-xl bg-card/95">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={handleSelectAll}>
                סמן הכל
              </Button>
              <Button size="sm" variant="ghost" onClick={handleDeselectAll}>
                בטל הכל
              </Button>
            </div>

            <Button
              size="sm"
              variant="outline"
              onClick={runAutoSegmentation}
              disabled={autoSegmenting}
              title="מריץ סגמנטציה אוטומטית על התוכנית"
            >
              {autoSegmenting ? 'מפלח…' : 'סגמנטציה אוטומטית'}
            </Button>

            <Button
              size="sm"
              variant="ghost"
              onClick={() => setAdvancedOpen(!advancedOpen)}
              title="פתיחת פרמטרים מתקדמים"
            >
              פרמטרים מתקדמים {advancedOpen ? <ChevronUp className="inline w-4 h-4" /> : <ChevronDown className="inline w-4 h-4" />}
            </Button>

            <Button
              size="sm"
              variant="outline"
              onClick={analyzeSelectedSegments}
              disabled={analyzingSegments}
              title="מריץ סיווג וחילוץ מידע לכל הסגמנטים המסומנים (ללא ולידציה)"
            >
              {analyzingSegments ? 'מסווג…' : 'סווג סגמנטים'}
            </Button>

            <div className="h-6 w-px bg-border mx-2" />

            <div className="flex items-center gap-2 bg-background rounded-lg border border-border p-1">
              <button onClick={() => setZoom(Math.max(10, zoom - 10))} className="p-1.5 hover:bg-muted rounded-md text-text-muted hover:text-text-primary">
                <ZoomOut className="w-4 h-4" />
              </button>
              <span className="text-sm font-mono w-12 text-center text-text-primary">{zoom}%</span>
              <button onClick={() => setZoom(Math.min(1000, zoom + 10))} className="p-1.5 hover:bg-muted rounded-md text-text-muted hover:text-text-primary">
                <ZoomIn className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {advancedOpen && (
          <div className="mt-4 border-t border-border pt-4 text-sm">
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <label className="inline-flex items-center gap-2" title={advancedHelp.advanced_enabled}>
                <input
                  type="checkbox"
                  checked={advancedEnabled}
                  onChange={(event) => setAdvancedEnabled(event.target.checked)}
                />
                <span>הפעל פרמטרים מתקדמים</span>
              </label>
              <div className="inline-flex items-center gap-2 text-xs text-text-muted border border-border rounded-full px-3 py-1 bg-background">
                <span>מצב רגיש</span>
                <button
                  type="button"
                  onClick={() => {
                    const next = autoSensitivity === 'high' ? 'normal' : 'high';
                    setAutoSensitivity(next);
                    if (next === 'high') {
                      applySensitivePreset();
                    }
                  }}
                  className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs ${
                    autoSensitivity === 'high'
                      ? 'border-primary text-primary bg-primary/10'
                      : 'border-border text-text-muted'
                  }`}
                  title={advancedHelp.auto_sensitivity}
                >
                  {autoSensitivity === 'high' ? 'פעיל' : 'כבוי'}
                </button>
              </div>
              <div className="inline-flex items-center gap-2 text-xs text-text-muted border border-border rounded-full px-3 py-1 bg-background">
                <span>מצב LLM</span>
                <button
                  type="button"
                  onClick={() => setAutoMode(autoMode === 'llm' ? 'cv' : 'llm')}
                  className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs ${
                    autoMode === 'llm'
                      ? 'border-primary text-primary bg-primary/10'
                      : 'border-border text-text-muted'
                  }`}
                  title={advancedHelp.auto_mode}
                >
                  {autoMode === 'llm' ? 'פעיל' : 'כבוי'}
                </button>
              </div>
              <div className="inline-flex items-center gap-2 text-xs text-text-muted border border-border rounded-full px-3 py-1 bg-background">
                <span>Auto-Tune</span>
                <button
                  type="button"
                  onClick={() => setAutoTune(!autoTune)}
                  className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs ${
                    autoTune ? 'border-primary text-primary bg-primary/10' : 'border-border text-text-muted'
                  }`}
                  title={advancedHelp.auto_tune}
                >
                  {autoTune ? 'פעיל' : 'כבוי'}
                </button>
              </div>
              <div className="inline-flex items-center gap-2 text-xs text-text-muted border border-border rounded-full px-3 py-1 bg-background">
                <span>LLM Verify</span>
                <button
                  type="button"
                  onClick={() => setAutoVerify(!autoVerify)}
                  className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs ${
                    autoVerify ? 'border-primary text-primary bg-primary/10' : 'border-border text-text-muted'
                  }`}
                  title={advancedHelp.auto_verify}
                >
                  {autoVerify ? 'פעיל' : 'כבוי'}
                </button>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-3">
                <div className="text-xs uppercase tracking-wide text-text-muted">כללי</div>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.target_segments}>
                  <span>Target Segments</span>
                  <input
                    type="number"
                    value={advancedNums.target_segments}
                    onChange={updateAdvancedNumber('target_segments')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.max_dim}>
                  <span>Max Dim</span>
                  <input
                    type="number"
                    value={advancedNums.max_dim}
                    onChange={updateAdvancedNumber('max_dim')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.min_area_ratio}>
                  <span>Min Area Ratio</span>
                  <input
                    type="number"
                    step="0.001"
                    value={advancedNums.min_area_ratio}
                    onChange={updateAdvancedNumber('min_area_ratio')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.max_area_ratio}>
                  <span>Max Area Ratio</span>
                  <input
                    type="number"
                    step="0.01"
                    value={advancedNums.max_area_ratio}
                    onChange={updateAdvancedNumber('max_area_ratio')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.merge_iou_threshold}>
                  <span>Merge IoU</span>
                  <input
                    type="number"
                    step="0.01"
                    value={advancedNums.merge_iou_threshold}
                    onChange={updateAdvancedNumber('merge_iou_threshold')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.ocr_enabled}>
                  <span>OCR</span>
                  <input
                    type="checkbox"
                    checked={ocrEnabled}
                    onChange={() => setOcrEnabled(!ocrEnabled)}
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.deskew}>
                  <span>Deskew</span>
                  <input
                    type="checkbox"
                    checked={deskewEnabled}
                    onChange={() => setDeskewEnabled(!deskewEnabled)}
                  />
                </label>
              </div>

              <div className="space-y-3">
                <div className="text-xs uppercase tracking-wide text-text-muted">קווים והפרדות</div>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.line_kernel_scale}>
                  <span>Line Kernel Scale</span>
                  <input
                    type="number"
                    value={advancedNums.line_kernel_scale}
                    onChange={updateAdvancedNumber('line_kernel_scale')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.line_merge_iterations}>
                  <span>Line Merge Iter</span>
                  <input
                    type="number"
                    value={advancedNums.line_merge_iterations}
                    onChange={updateAdvancedNumber('line_merge_iterations')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.separator_line_density}>
                  <span>Separator Density</span>
                  <input
                    type="number"
                    step="0.01"
                    value={advancedNums.separator_line_density}
                    onChange={updateAdvancedNumber('separator_line_density')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.separator_min_height_ratio}>
                  <span>Separator Min Height</span>
                  <input
                    type="number"
                    step="0.01"
                    value={advancedNums.separator_min_height_ratio}
                    onChange={updateAdvancedNumber('separator_min_height_ratio')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.separator_max_width}>
                  <span>Separator Max Width</span>
                  <input
                    type="number"
                    value={advancedNums.separator_max_width}
                    onChange={updateAdvancedNumber('separator_max_width')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.separator_min_gap}>
                  <span>Separator Min Gap</span>
                  <input
                    type="number"
                    value={advancedNums.separator_min_gap}
                    onChange={updateAdvancedNumber('separator_min_gap')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.separator_min_line_width}>
                  <span>Separator Min Width</span>
                  <input
                    type="number"
                    value={advancedNums.separator_min_line_width}
                    onChange={updateAdvancedNumber('separator_min_line_width')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.hough_threshold}>
                  <span>Hough Threshold</span>
                  <input
                    type="number"
                    value={advancedNums.hough_threshold}
                    onChange={updateAdvancedNumber('hough_threshold')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.hough_min_line_length_ratio}>
                  <span>Hough Min Len</span>
                  <input
                    type="number"
                    step="0.01"
                    value={advancedNums.hough_min_line_length_ratio}
                    onChange={updateAdvancedNumber('hough_min_line_length_ratio')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.hough_max_line_gap}>
                  <span>Hough Max Gap</span>
                  <input
                    type="number"
                    value={advancedNums.hough_max_line_gap}
                    onChange={updateAdvancedNumber('hough_max_line_gap')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.hough_cluster_px}>
                  <span>Hough Cluster Px</span>
                  <input
                    type="number"
                    value={advancedNums.hough_cluster_px}
                    onChange={updateAdvancedNumber('hough_cluster_px')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
              </div>

              <div className="space-y-3">
                <div className="text-xs uppercase tracking-wide text-text-muted">עיבוד ותוכן</div>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.adaptive_block_size}>
                  <span>Adaptive Block</span>
                  <input
                    type="number"
                    value={advancedNums.adaptive_block_size}
                    onChange={updateAdvancedNumber('adaptive_block_size')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.adaptive_c}>
                  <span>Adaptive C</span>
                  <input
                    type="number"
                    value={advancedNums.adaptive_c}
                    onChange={updateAdvancedNumber('adaptive_c')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.close_kernel}>
                  <span>Close Kernel</span>
                  <input
                    type="number"
                    value={advancedNums.close_kernel}
                    onChange={updateAdvancedNumber('close_kernel')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.close_iterations}>
                  <span>Close Iter</span>
                  <input
                    type="number"
                    value={advancedNums.close_iterations}
                    onChange={updateAdvancedNumber('close_iterations')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.projection_density_threshold}>
                  <span>Projection Density</span>
                  <input
                    type="number"
                    step="0.001"
                    value={advancedNums.projection_density_threshold}
                    onChange={updateAdvancedNumber('projection_density_threshold')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.projection_min_gap}>
                  <span>Projection Gap</span>
                  <input
                    type="number"
                    value={advancedNums.projection_min_gap}
                    onChange={updateAdvancedNumber('projection_min_gap')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.split_large_area_ratio}>
                  <span>Split Large Ratio</span>
                  <input
                    type="number"
                    step="0.01"
                    value={advancedNums.split_large_area_ratio}
                    onChange={updateAdvancedNumber('split_large_area_ratio')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.split_large_min_boxes}>
                  <span>Split Large Min</span>
                  <input
                    type="number"
                    value={advancedNums.split_large_min_boxes}
                    onChange={updateAdvancedNumber('split_large_min_boxes')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.min_ink_ratio}>
                  <span>Min Ink Ratio</span>
                  <input
                    type="number"
                    step="0.0001"
                    value={advancedNums.min_ink_ratio}
                    onChange={updateAdvancedNumber('min_ink_ratio')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.min_ink_pixels}>
                  <span>Min Ink Pixels</span>
                  <input
                    type="number"
                    value={advancedNums.min_ink_pixels}
                    onChange={updateAdvancedNumber('min_ink_pixels')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.min_segment_width_ratio}>
                  <span>Min Segment Width</span>
                  <input
                    type="number"
                    step="0.01"
                    value={advancedNums.min_segment_width_ratio}
                    onChange={updateAdvancedNumber('min_segment_width_ratio')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.content_crop_enabled}>
                  <span>Content Crop</span>
                  <input
                    type="checkbox"
                    checked={advancedFlags.content_crop_enabled}
                    onChange={() => toggleAdvancedFlag('content_crop_enabled')}
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.content_crop_pad}>
                  <span>Content Crop Pad</span>
                  <input
                    type="number"
                    value={advancedNums.content_crop_pad}
                    onChange={updateAdvancedNumber('content_crop_pad')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.content_density_threshold}>
                  <span>Content Density</span>
                  <input
                    type="number"
                    step="0.001"
                    value={advancedNums.content_density_threshold}
                    onChange={updateAdvancedNumber('content_density_threshold')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.content_min_span_ratio}>
                  <span>Content Min Span</span>
                  <input
                    type="number"
                    step="0.01"
                    value={advancedNums.content_min_span_ratio}
                    onChange={updateAdvancedNumber('content_min_span_ratio')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.refine_by_content}>
                  <span>Refine By Content</span>
                  <input
                    type="checkbox"
                    checked={advancedFlags.refine_by_content}
                    onChange={() => toggleAdvancedFlag('refine_by_content')}
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.refine_pad}>
                  <span>Refine Pad</span>
                  <input
                    type="number"
                    value={advancedNums.refine_pad}
                    onChange={updateAdvancedNumber('refine_pad')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.edge_refine_enabled}>
                  <span>Edge Refine</span>
                  <input
                    type="checkbox"
                    checked={advancedFlags.edge_refine_enabled}
                    onChange={() => toggleAdvancedFlag('edge_refine_enabled')}
                  />
                </label>
                <label className="flex items-center justify-between gap-3" title={advancedHelp.edge_refine_pad}>
                  <span>Edge Refine Pad</span>
                  <input
                    type="number"
                    value={advancedNums.edge_refine_pad}
                    onChange={updateAdvancedNumber('edge_refine_pad')}
                    className="w-24 border border-border rounded-md px-2 py-1"
                  />
                </label>
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* Full Plan View */}
      {decomposition.full_plan_url && (
        <Card className="p-6 overflow-hidden">
          <div className="mb-4 p-3 bg-primary/5 border border-primary/10 rounded-xl text-sm text-text-primary flex items-center justify-between gap-3">
            <div>
              <strong className="font-semibold">בחירה ידנית:</strong>{' '}
              {editingSegmentId
                ? 'עריכת אזור: גרור מחדש על התוכנית כדי להגדיר את האזור.'
                : 'גרור על התוכנית כדי לסמן אזור לבדיקה (אפשר כמה פעמים). האזור יתווסף כסגמנט חדש.'}
              {' '}אפשר גם להריץ סגמנטציה אוטומטית מהכפתור למעלה ואז לתקן ידנית.
            </div>
            <div className="text-text-muted whitespace-nowrap flex items-center gap-2">
              {roiQueue.length > 0 && <span>תור: {roiQueue.length}</span>}
              {savingManual && <span>שומר…</span>}
            </div>
          </div>
          <div 
            className="border border-border rounded-xl overflow-auto bg-background/50 relative min-h-[500px]"
            style={{ maxHeight: '70vh' }}
            ref={planContainerRef}
          >
            <div
              className="relative inline-block origin-top-right transition-transform duration-200"
              style={{ transform: `scale(${zoom / 100})` }}
            >
              <img
                src={decomposition.full_plan_url}
                alt="תוכנית מלאה"
                className="max-w-none"
                style={{ direction: 'ltr' }}
                ref={planImgRef}
                onLoad={autoFitZoomIfNeeded}
              />

              {/* Drawing overlay (manual ROI selection) */}
              <div
                className="absolute inset-0 cursor-crosshair z-30"
                style={{ touchAction: 'none' }}
                onPointerDown={handlePlanPointerDown}
                onPointerMove={handlePlanPointerMove}
                onPointerUp={handlePlanPointerUp}
                onPointerCancel={(e) => {
                  setIsDrawing(false);
                  setDrawStart(null);
                  setDrawCurrent(null);

                  try {
                    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
                  } catch {
                    // best-effort
                  }
                }}
              />

              {decomposition.segments.map((segment) => (
                (() => {
                  const pending = pendingEdits[segment.segment_id];
                  const b = pending ? relativeToPercent(pending) : bboxToPercent(segment.bounding_box);
                  return (
                <div
                  key={segment.segment_id}
                  className={`absolute border-2 transition-all cursor-pointer group ${
                    segment.approved_by_user 
                      ? 'border-success bg-success/10 hover:bg-success/20' 
                      : 'border-error bg-error/10 hover:bg-error/20'
                  }`}
                  style={{
                    left: `${b.x}%`,
                    top: `${b.y}%`,
                    width: `${b.width}%`,
                    height: `${b.height}%`,
                    pointerEvents: editingSegmentId ? 'none' : 'auto',
                  }}
                  onClick={() => {
                    if (editingSegmentId) return;
                    updateSegmentApproval(segment.segment_id, !segment.approved_by_user);
                  }}
                >
                  {pending && (
                    <div className="absolute -top-7 right-0 text-[10px] text-primary bg-white/90 border border-primary/20 rounded px-2 py-0.5 shadow">
                      שומר…
                    </div>
                  )}
                  <div className="absolute -top-8 right-0 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                    <div className="bg-popover text-popover-foreground text-xs px-2 py-1 rounded shadow-lg border border-border whitespace-nowrap font-medium">
                      {segment.title} ({(segment.confidence * 100).toFixed(0)}%)
                    </div>
                  </div>
                </div>
                  );
                })()
              ))}
              {pendingRois.map((pending) => {
                const b = relativeToPercent(pending.roi);
                return (
                  <div
                    key={pending.id}
                    className="absolute border-2 border-success/70 bg-success/10 border-dashed z-20"
                    style={{
                      left: `${b.x}%`,
                      top: `${b.y}%`,
                      width: `${b.width}%`,
                      height: `${b.height}%`,
                      pointerEvents: 'none',
                    }}
                  >
                    <div className="absolute -top-7 right-0 text-[10px] text-success bg-white/90 border border-success/20 rounded px-2 py-0.5 shadow">
                      שומר…
                    </div>
                  </div>
                );
              })}

              {/* Current drawn rectangle */}
              {isDrawing && drawStart && drawCurrent && (
                (() => {
                  const x1 = Math.min(drawStart.x, drawCurrent.x) * 100;
                  const y1 = Math.min(drawStart.y, drawCurrent.y) * 100;
                  const x2 = Math.max(drawStart.x, drawCurrent.x) * 100;
                  const y2 = Math.max(drawStart.y, drawCurrent.y) * 100;
                  return (
                    <div
                      className="absolute border-2 border-primary bg-primary/10 z-40"
                      style={{ left: `${x1}%`, top: `${y1}%`, width: `${x2 - x1}%`, height: `${y2 - y1}%` }}
                    />
                  );
                })()
              )}
            </div>
          </div>
        </Card>
      )}

      {/* Segments List */}
      <div className="grid gap-4">
        {decomposition.segments.map((segment) => (
          <Card
            key={segment.segment_id}
            className={`transition-all duration-200 ${
              segment.approved_by_user 
                ? 'border-success/30 bg-success/5 shadow-sm' 
                : 'border-border bg-card hover:border-primary/30'
            }`}
          >
            <div className="p-4 flex items-start gap-4">
              {/* Thumbnail */}
              <button
                type="button"
                className="shrink-0 w-32 h-24 rounded-lg border border-border bg-muted overflow-hidden relative group focus:outline-none focus:ring-2 focus:ring-primary/40"
                onClick={() => onOpenSegmentImage?.(segment)}
                aria-label={`פתח תמונה של ${segment.title || segment.segment_id}`}
              >
                {segment.thumbnail_url ? (
                  <img
                    src={segment.thumbnail_url}
                    alt={segment.title}
                    className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-text-muted">
                    <LayoutGrid className="w-8 h-8 opacity-20" />
                  </div>
                )}
              </button>

              {/* Content */}
              <div className="grow min-w-0">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-3">
                      <h3 className="text-base font-semibold text-text-primary truncate">
                        {segment.title}
                      </h3>
                      <Badge variant={getConfidenceBadgeVariant(segment.confidence) as any}>
                        {Math.round(segment.confidence * 100)}%
                      </Badge>
                      <Badge variant="neutral" className="hidden sm:inline-flex">
                        {getSegmentTypeLabel(segment.type)}
                      </Badge>
                    </div>
                    <p className="text-sm text-text-muted mt-1 line-clamp-2">
                      {segment.description}
                    </p>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <label className="flex items-center gap-2 cursor-pointer select-none">
                      <span className="text-sm text-text-primary">
                        {segment.approved_by_user ? 'מאושר' : 'לא מאושר'}
                      </span>
                      <div className={`w-6 h-6 rounded border flex items-center justify-center transition-all ${
                        segment.approved_by_user 
                          ? 'bg-success border-success text-white' 
                          : 'bg-background border-border text-transparent hover:border-primary'
                      }`}>
                        <Check className="w-4 h-4" />
                      </div>
                      <input
                        type="checkbox"
                        className="hidden"
                        checked={segment.approved_by_user}
                        onChange={(e) => updateSegmentApproval(segment.segment_id, e.target.checked)}
                      />
                    </label>

                    {segment.llm_reasoning === 'MANUAL_ROI' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setEditingSegmentId(segment.segment_id);
                        }}
                      >
                        ערוך אזור
                      </Button>
                    )}
                  </div>
                </div>

                <button
                  onClick={() => toggleSegmentExpand(segment.segment_id)}
                  className="mt-2 text-sm text-primary hover:text-primary-dark flex items-center gap-1 font-medium transition-colors"
                >
                  {expandedSegments.has(segment.segment_id) ? (
                    <>הסתר פרטים <ChevronUp className="w-4 h-4" /></>
                  ) : (
                    <>פרטים טכניים <ChevronDown className="w-4 h-4" /></>
                  )}
                </button>

                {/* Expanded details */}
                {expandedSegments.has(segment.segment_id) && (
                  <div className="mt-3 p-3 bg-background/50 rounded-lg border border-border text-sm animate-in slide-in-from-top-2 duration-200">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <strong className="text-text-primary block mb-1">מיקום בתוכנית (Bounding Box):</strong>
                        <div className="text-xs text-text-muted font-mono bg-background p-2 rounded border border-border">
                          {(() => {
                            const b = bboxToPercent(segment.bounding_box);
                            return (
                              <>
                                x: {b.x.toFixed(1)}%, y: {b.y.toFixed(1)}%<br />
                                w: {b.width.toFixed(1)}%, h: {b.height.toFixed(1)}%
                              </>
                            );
                          })()}
                        </div>
                      </div>
                      {segment.llm_reasoning && (
                        <div>
                          <strong className="text-text-primary block mb-1">ניתוח AI:</strong>
                          <div className="text-xs text-text-muted leading-relaxed bg-background p-2 rounded border border-border">
                            {segment.llm_reasoning === 'MANUAL_ROI' ? 'אזור שסומן ידנית' : ''}
                          </div>
                        </div>
                      )}

                      {segment.analysis_data?.classification && (
                        <div className="md:col-span-2">
                          <strong className="text-text-primary block mb-1">סיווג וחילוץ (שקיפות):</strong>
                          <div className="text-xs text-text-muted leading-relaxed bg-background p-2 rounded border border-border space-y-2">
                            <div>
                              <span className="font-semibold">ראשי:</span>{' '}
                              {segment.analysis_data.classification.primary_category
                                ? translateModelCategory(String(segment.analysis_data.classification.primary_category))
                                : '—'}
                              {Array.isArray(segment.analysis_data.classification.secondary_categories) && segment.analysis_data.classification.secondary_categories.length > 0 ? (
                                <>
                                  {' '}<span className="font-semibold">משני:</span>{' '}
                                  {segment.analysis_data.classification.secondary_categories
                                    .map((c: any) => translateModelCategory(String(c)))
                                    .join(', ')}
                                </>
                              ) : null}
                              {typeof segment.analysis_data.classification.confidence === 'number' ? (
                                <>
                                  {' '}<span className="font-semibold">ביטחון:</span>{' '}
                                  {(segment.analysis_data.classification.confidence * 100).toFixed(0)}%
                                </>
                              ) : null}
                            </div>

                            {segment.analysis_data.classification.explanation_he && (
                              <div>
                                <span className="font-semibold">הסבר:</span>{' '}
                                {segment.analysis_data.classification.explanation_he}
                              </div>
                            )}

                            {Array.isArray(segment.analysis_data.classification.evidence) && segment.analysis_data.classification.evidence.length > 0 && (
                              <div>
                                <span className="font-semibold">ראיות:</span>{' '}
                                {segment.analysis_data.classification.evidence.join(' • ')}
                              </div>
                            )}

                            {Array.isArray(segment.analysis_data.classification.missing_information) && segment.analysis_data.classification.missing_information.length > 0 && (
                              <div>
                                <span className="font-semibold">חסר:</span>{' '}
                                {segment.analysis_data.classification.missing_information.join(' • ')}
                              </div>
                            )}

                            <div>
                              <span className="font-semibold">כמות פריטים שחולצו:</span>{' '}
                              טקסט: {Array.isArray(segment.analysis_data.text_items) ? segment.analysis_data.text_items.length : 0},{' '}
                              מידות: {Array.isArray(segment.analysis_data.dimensions) ? segment.analysis_data.dimensions.length : 0},{' '}
                              אלמנטים: {Array.isArray(segment.analysis_data.structural_elements) ? segment.analysis_data.structural_elements.length : 0}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Metadata Section */}
      {decomposition.metadata.project_name && (
        <Card className="p-6">
          <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
            <List className="w-5 h-5 text-primary" />
            פרטי הפרויקט (זוהו אוטומטית)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {decomposition.metadata.project_name && (
              <div>
                <div className="text-xs text-text-muted uppercase tracking-wider font-medium mb-1">פרויקט</div>
                <div className="font-medium text-text-primary">{decomposition.metadata.project_name}</div>
              </div>
            )}
            {decomposition.metadata.architect && (
              <div>
                <div className="text-xs text-text-muted uppercase tracking-wider font-medium mb-1">אדריכל</div>
                <div className="font-medium text-text-primary">{decomposition.metadata.architect}</div>
              </div>
            )}
            {decomposition.metadata.date && (
              <div>
                <div className="text-xs text-text-muted uppercase tracking-wider font-medium mb-1">תאריך</div>
                <div className="font-medium text-text-primary">{decomposition.metadata.date}</div>
              </div>
            )}
            {decomposition.metadata.plan_number && (
              <div>
                <div className="text-xs text-text-muted uppercase tracking-wider font-medium mb-1">מס' תוכנית</div>
                <div className="font-medium text-text-primary">{decomposition.metadata.plan_number}</div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Action Buttons */}
      <div className="sticky bottom-6 z-30">
        <Card className="p-4 shadow-xl border-primary/10 bg-card/95 backdrop-blur-xl">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-4">
              <div className="text-sm font-medium text-text-primary">בחר בדיקות להרצה:</div>
              <div className="flex flex-wrap gap-3">
                {requirementOptions.map((req) => (
                  <label key={req.id} className="flex items-center gap-2 text-sm text-text-primary" title={req.help}>
                    <input
                      type="checkbox"
                      checked={selectedRequirements.includes(req.id)}
                      onChange={() => toggleRequirement(req.id)}
                    />
                    {req.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between gap-4">
              <Button
                variant="ghost"
                onClick={onReject}
                className="text-text-muted hover:text-error hover:bg-error/5"
              >
                <X className="w-4 h-4 ml-2" />
                ביטול וחזרה
              </Button>

              <div className="flex gap-3">
                <Button
                  variant="outline"
                  onClick={loadDecomposition}
                  className="hidden sm:flex"
                >
                  <RefreshCw className="w-4 h-4 ml-2" />
                  רענן נתונים
                </Button>

                <Button
                  onClick={handleApprove}
                  disabled={approvedCount === 0 || selectedRequirements.length === 0}
                  className="min-w-[200px] shadow-lg shadow-primary/20"
                >
                  <Check className="w-4 h-4 ml-2" />
                  {`אשר ${approvedCount} סגמנטים והמשך`}
                </Button>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default DecompositionReview;

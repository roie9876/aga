import React, { useRef, useState, useEffect } from 'react';
import { 
  Check, X, AlertTriangle, ZoomIn, ZoomOut, 
  RefreshCw, ChevronDown, ChevronUp,
  LayoutGrid, List
} from 'lucide-react';
import type { PlanDecomposition } from '../types';
import { Button, Card, Badge } from './ui';

interface DecompositionReviewProps {
  decompositionId: string;
  onApprove: (params: { mode: 'segments' | 'full_plan'; approvedSegments: string[]; check_groups: string[] }) => void;
  onReject: () => void;
}

export const DecompositionReview: React.FC<DecompositionReviewProps> = ({
  decompositionId,
  onApprove,
  onReject,
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
  const [roiQueue, setRoiQueue] = useState<
    Array<{
      kind: 'add' | 'update';
      segmentId?: string;
      roi: { x: number; y: number; width: number; height: number };
    }>
  >([]);
  const [analyzingSegments, setAnalyzingSegments] = useState(false);

  const [selectedCheckGroups, setSelectedCheckGroups] = useState<string[]>([
    'walls',
    'heights',
    'doors',
    'windows',
  ]);

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
    setZoom(Math.max(10, Math.min(200, fit || 20)));
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
        if (!isCancelled) setSavingManual(false);
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

    onApprove({ mode: 'segments', approvedSegments: approved, check_groups: selectedCheckGroups });
  };

  const toggleCheckGroup = (group: string) => {
    setSelectedCheckGroups((prev) => {
      if (prev.includes(group)) return prev.filter((g) => g !== group);
      return [...prev, group];
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
    setRoiQueue((q) => [...q, { kind: 'add', roi }]);
  };

  const enqueueManualRoiUpdate = (segmentId: string, roi: { x: number; y: number; width: number; height: number }) => {
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
              בחר אזורים ידנית על גבי התוכנית (גרור מלבן) כדי ליצור סגמנטים לבדיקה.
            </p>
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
              <button onClick={() => setZoom(Math.min(200, zoom + 10))} className="p-1.5 hover:bg-muted rounded-md text-text-muted hover:text-text-primary">
                <ZoomIn className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
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
              {' '}כדי להתקדם לשלב הבא לחץ למטה על “אשר והמשך”.
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
                  const b = bboxToPercent(segment.bounding_box);
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
                  <div className="absolute -top-8 right-0 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                    <div className="bg-popover text-popover-foreground text-xs px-2 py-1 rounded shadow-lg border border-border whitespace-nowrap font-medium">
                      {segment.title} ({(segment.confidence * 100).toFixed(0)}%)
                    </div>
                  </div>
                </div>
                  );
                })()
              ))}

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
              <div className="shrink-0 w-32 h-24 rounded-lg border border-border bg-muted overflow-hidden relative group">
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
              </div>

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
                            {segment.llm_reasoning}
                          </div>
                        </div>
                      )}

                      {segment.analysis_data?.classification && (
                        <div className="md:col-span-2">
                          <strong className="text-text-primary block mb-1">סיווג וחילוץ (שקיפות):</strong>
                          <div className="text-xs text-text-muted leading-relaxed bg-background p-2 rounded border border-border space-y-2">
                            <div>
                              <span className="font-semibold">Primary:</span>{' '}
                              {String(segment.analysis_data.classification.primary_category || '—')}
                              {Array.isArray(segment.analysis_data.classification.secondary_categories) && segment.analysis_data.classification.secondary_categories.length > 0 ? (
                                <>
                                  {' '}<span className="font-semibold">Secondary:</span>{' '}
                                  {segment.analysis_data.classification.secondary_categories.join(', ')}
                                </>
                              ) : null}
                              {typeof segment.analysis_data.classification.confidence === 'number' ? (
                                <>
                                  {' '}<span className="font-semibold">Confidence:</span>{' '}
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
              <div className="text-sm font-medium text-text-primary">בחר סט בדיקות להרצה:</div>
              <label className="flex items-center gap-2 text-sm text-text-primary">
                <input
                  type="checkbox"
                  checked={selectedCheckGroups.includes('walls')}
                  onChange={() => toggleCheckGroup('walls')}
                />
                קירות
              </label>
              <label className="flex items-center gap-2 text-sm text-text-primary">
                <input
                  type="checkbox"
                  checked={selectedCheckGroups.includes('heights')}
                  onChange={() => toggleCheckGroup('heights')}
                />
                גובה/נפח
              </label>
              <label className="flex items-center gap-2 text-sm text-text-primary">
                <input
                  type="checkbox"
                  checked={selectedCheckGroups.includes('doors')}
                  onChange={() => toggleCheckGroup('doors')}
                />
                דלתות
              </label>
              <label className="flex items-center gap-2 text-sm text-text-primary">
                <input
                  type="checkbox"
                  checked={selectedCheckGroups.includes('windows')}
                  onChange={() => toggleCheckGroup('windows')}
                />
                חלונות
              </label>
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
                  disabled={approvedCount === 0 || selectedCheckGroups.length === 0}
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

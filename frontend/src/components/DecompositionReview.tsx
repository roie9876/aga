import React, { useState, useEffect } from 'react';
import { 
  Check, X, AlertTriangle, ZoomIn, ZoomOut, 
  Edit, Trash2, Upload, Save, RefreshCw, ChevronDown, ChevronUp,
  Maximize2, LayoutGrid, List
} from 'lucide-react';
import type { PlanDecomposition, PlanSegment } from '../types';
import { Button, Card, Badge } from './ui';

interface DecompositionReviewProps {
  decompositionId: string;
  onApprove: (approvedSegments: string[]) => void;
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
  const [viewMode, setViewMode] = useState<'full' | 'segments'>('full');
  const [zoom, setZoom] = useState(100);
  const [expandedSegments, setExpandedSegments] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadDecomposition();
  }, [decompositionId]);

  const loadDecomposition = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/v1/decomposition/${decompositionId}`);
      
      if (!response.ok) {
        throw new Error('Failed to load decomposition');
      }

      const data: PlanDecomposition = await response.json();
      setDecomposition(data);
      
      // Auto-approve segments with high confidence
      const highConfidenceSegments = data.segments.filter(s => s.confidence >= 0.85);
      highConfidenceSegments.forEach(s => {
        updateSegmentApproval(s.segment_id, true);
      });
      
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
    
    onApprove(approved);
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

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.85) return 'text-success';
    if (confidence >= 0.70) return 'text-warning';
    return 'text-error';
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

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <RefreshCw className="w-12 h-12 animate-spin text-primary" />
        <p className="text-text-muted">טוען את ניתוח התוכנית...</p>
      </div>
    );
  }

  if (error || !decomposition) {
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

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header Stats */}
      <Card className="p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
              <Check className="w-6 h-6 text-success" />
              אישור סגמנטים
            </h1>
            <p className="text-text-muted mt-1">אנא וודא שהסגמנטים זוהו כראוי לפני המעבר לשלב הבדיקה</p>
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
                {(decomposition.segments.reduce((acc, s) => acc + s.confidence, 0) / decomposition.segments.length * 100).toFixed(0)}%
              </div>
            </div>
          </div>
        </div>

        {lowConfidenceCount > 0 && (
          <div className="p-4 bg-warning/5 border border-warning/20 rounded-xl flex items-center gap-3 text-sm">
            <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0" />
            <span className="text-warning-dark font-medium">
              שים לב: {lowConfidenceCount} סגמנטים עם רמת ביטחון נמוכה - מומלץ לבדוק ידנית
            </span>
          </div>
        )}
      </Card>

      {/* Controls */}
      <Card className="p-4 sticky top-20 z-30 shadow-md backdrop-blur-xl bg-card/95">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex gap-2 bg-background p-1 rounded-lg border border-border">
            <button
              onClick={() => setViewMode('full')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${
                viewMode === 'full' 
                  ? 'bg-white shadow-sm text-primary' 
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              <Maximize2 className="w-4 h-4" />
              תוכנית מלאה
            </button>
            <button
              onClick={() => setViewMode('segments')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${
                viewMode === 'segments' 
                  ? 'bg-white shadow-sm text-primary' 
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              <LayoutGrid className="w-4 h-4" />
              רשימת סגמנטים
            </button>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={handleSelectAll}>
                סמן הכל
              </Button>
              <Button size="sm" variant="ghost" onClick={handleDeselectAll}>
                בטל הכל
              </Button>
            </div>

            <div className="h-6 w-px bg-border mx-2" />

            <div className="flex items-center gap-2 bg-background rounded-lg border border-border p-1">
              <button onClick={() => setZoom(Math.max(50, zoom - 10))} className="p-1.5 hover:bg-muted rounded-md text-text-muted hover:text-text-primary">
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
      {viewMode === 'full' && decomposition.full_plan_url && (
        <Card className="p-6 overflow-hidden">
          <div 
            className="border border-border rounded-xl overflow-auto bg-background/50 relative min-h-[500px]"
            style={{ maxHeight: '70vh' }}
          >
            <div className="relative inline-block origin-top-right transition-transform duration-200" style={{ transform: `scale(${zoom / 100})` }}>
              <img
                src={decomposition.full_plan_url}
                alt="תוכנית מלאה"
                className="max-w-none"
                style={{ direction: 'ltr' }}
              />
              {decomposition.segments.map((segment) => (
                <div
                  key={segment.segment_id}
                  className={`absolute border-2 transition-all cursor-pointer group ${
                    segment.approved_by_user 
                      ? 'border-success bg-success/10 hover:bg-success/20' 
                      : 'border-error bg-error/10 hover:bg-error/20'
                  }`}
                  style={{
                    left: `${segment.bounding_box.x}%`,
                    top: `${segment.bounding_box.y}%`,
                    width: `${segment.bounding_box.width}%`,
                    height: `${segment.bounding_box.height}%`,
                  }}
                  onClick={() => updateSegmentApproval(segment.segment_id, !segment.approved_by_user)}
                >
                  <div className="absolute -top-8 right-0 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                    <div className="bg-popover text-popover-foreground text-xs px-2 py-1 rounded shadow-lg border border-border whitespace-nowrap font-medium">
                      {segment.title} ({(segment.confidence * 100).toFixed(0)}%)
                    </div>
                  </div>
                </div>
              ))}
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
              <div className="flex-shrink-0 w-32 h-24 rounded-lg border border-border bg-muted overflow-hidden relative group">
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
              <div className="flex-grow min-w-0">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h4 className="font-semibold text-text-primary text-lg mb-1 truncate">
                      {segment.title}
                    </h4>
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <Badge variant="secondary" className="text-xs">
                        {getSegmentTypeLabel(segment.type)}
                      </Badge>
                      <Badge 
                        variant={getConfidenceBadgeVariant(segment.confidence) as any}
                        className="text-xs"
                      >
                        {(segment.confidence * 100).toFixed(0)}% דיוק
                      </Badge>
                    </div>
                    <p className="text-sm text-text-muted line-clamp-2">{segment.description}</p>
                  </div>

                  <div className="flex flex-col items-end gap-2">
                    <label className="flex items-center gap-2 cursor-pointer select-none group">
                      <span className={`text-sm font-medium transition-colors ${segment.approved_by_user ? 'text-success' : 'text-text-muted group-hover:text-text-primary'}`}>
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
                          x: {segment.bounding_box.x.toFixed(1)}%, y: {segment.bounding_box.y.toFixed(1)}%<br />
                          w: {segment.bounding_box.width.toFixed(1)}%, h: {segment.bounding_box.height.toFixed(1)}%
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
                disabled={approvedCount === 0}
                className="min-w-[200px] shadow-lg shadow-primary/20"
              >
                <Check className="w-4 h-4 ml-2" />
                אשר {approvedCount} סגמנטים והמשך
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default DecompositionReview;

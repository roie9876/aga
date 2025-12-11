import React, { useState, useEffect } from 'react';
import { 
  Check, X, AlertTriangle, ZoomIn, ZoomOut, 
  Edit, Trash2, Upload, Save, RefreshCw, ChevronDown, ChevronUp 
} from 'lucide-react';
import type { PlanDecomposition, PlanSegment } from '../types';

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
  const [editingSegment, setEditingSegment] = useState<string | null>(null);

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
    if (confidence >= 0.85) return 'text-green-600';
    if (confidence >= 0.70) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getConfidenceIcon = (confidence: number) => {
    if (confidence >= 0.85) return '🟢';
    if (confidence >= 0.70) return '🟡';
    return '🔴';
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
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 animate-spin text-blue-500 mx-auto mb-4" />
          <p className="text-gray-600">טוען פירוק...</p>
        </div>
      </div>
    );
  }

  if (error || !decomposition) {
    return (
      <div className="max-w-2xl mx-auto p-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-red-800 mb-2">שגיאה</h3>
          <p className="text-red-600">{error || 'לא ניתן לטעון את הפירוק'}</p>
          <button
            onClick={onReject}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
          >
            חזור
          </button>
        </div>
      </div>
    );
  }

  const approvedCount = decomposition.segments.filter(s => s.approved_by_user).length;
  const lowConfidenceCount = decomposition.segments.filter(s => s.confidence < 0.75).length;

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
          <h1 className="text-3xl font-bold text-gray-800 mb-2">
            ✅ פירוק התוכנית הושלם - אנא בדוק ואשר
          </h1>
          
          {/* Stats */}
          <div className="flex gap-6 mt-4 text-sm text-gray-600">
            <div>⏱️ זמן עיבוד: <strong>{decomposition.processing_stats.processing_time_seconds.toFixed(1)}s</strong></div>
            <div>📊 סגמנטים: <strong>{decomposition.segments.length}</strong></div>
            <div>✅ מאושרים: <strong>{approvedCount}/{decomposition.segments.length}</strong></div>
            <div>📈 Confidence ממוצע: <strong>{(decomposition.segments.reduce((acc, s) => acc + s.confidence, 0) / decomposition.segments.length * 100).toFixed(0)}%</strong></div>
          </div>

          {/* Warning for low confidence */}
          {lowConfidenceCount > 0 && (
            <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-yellow-600" />
              <span className="text-sm text-yellow-800">
                ⚠️ שים לב: {lowConfidenceCount} סגמנטים עם ביטחון נמוך - מומלץ לבדוק
              </span>
            </div>
          )}
        </div>

        {/* View Controls */}
        <div className="bg-white rounded-lg shadow p-4 mb-6">
          <div className="flex items-center justify-between">
            <div className="flex gap-4">
              <button
                onClick={() => setViewMode('full')}
                className={`px-4 py-2 rounded ${
                  viewMode === 'full' ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-700'
                }`}
              >
                ● תוכנית מלאה
              </button>
              <button
                onClick={() => setViewMode('segments')}
                className={`px-4 py-2 rounded ${
                  viewMode === 'segments' ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-700'
                }`}
              >
                ○ סגמנטים בלבד
              </button>
            </div>

            <div className="flex items-center gap-4">
              {/* Select All / Deselect All buttons */}
              <div className="flex gap-2 border-l pl-4">
                <button
                  onClick={handleSelectAll}
                  className="px-3 py-1 bg-green-500 text-white text-sm rounded hover:bg-green-600 transition-colors"
                  title="סמן את כל הסגמנטים"
                >
                  ✓ סמן הכל
                </button>
                <button
                  onClick={handleDeselectAll}
                  className="px-3 py-1 bg-gray-500 text-white text-sm rounded hover:bg-gray-600 transition-colors"
                  title="בטל סימון של כל הסגמנטים"
                >
                  ✗ בטל הכל
                </button>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600">🔍 Zoom:</span>
                <button onClick={() => setZoom(Math.max(50, zoom - 10))} className="p-1 hover:bg-gray-100 rounded">
                  <ZoomOut className="w-4 h-4" />
                </button>
                <span className="text-sm font-mono w-12 text-center">{zoom}%</span>
                <button onClick={() => setZoom(Math.min(200, zoom + 10))} className="p-1 hover:bg-gray-100 rounded">
                  <ZoomIn className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Full Plan View */}
        {viewMode === 'full' && decomposition.full_plan_url && (
          <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
            <h3 className="text-lg font-semibold mb-4">🖼️ תוכנית מלאה</h3>
            <div 
              className="border-2 border-gray-200 rounded-lg overflow-auto bg-gray-50"
              style={{ maxHeight: '600px' }}
            >
              <div className="relative inline-block" style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top right' }}>
                <img
                  src={decomposition.full_plan_url}
                  alt="תוכנית מלאה"
                  className="w-full h-auto"
                  style={{ direction: 'ltr' }}
                />
                {/* Bounding boxes overlay */}
                {decomposition.segments.map((segment) => (
                  <div
                    key={segment.segment_id}
                    className={`absolute border-2 ${
                      segment.approved_by_user ? 'border-green-500' : 'border-red-500'
                    } bg-opacity-10 hover:bg-opacity-30 transition-all cursor-pointer`}
                    style={{
                      left: `${segment.bounding_box.x}%`,
                      top: `${segment.bounding_box.y}%`,
                      width: `${segment.bounding_box.width}%`,
                      height: `${segment.bounding_box.height}%`,
                    }}
                    title={`${segment.title} (${(segment.confidence * 100).toFixed(0)}%)`}
                  >
                    <div className="absolute -top-6 right-0 bg-white px-2 py-1 rounded shadow text-xs font-semibold border">
                      {segment.title} {(segment.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Segments List */}
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h3 className="text-lg font-semibold mb-4">📑 סגמנטים שזוהו ({decomposition.segments.length})</h3>
          
          <div className="space-y-4">
            {decomposition.segments.map((segment) => (
              <div
                key={segment.segment_id}
                className={`border rounded-lg p-4 transition-all ${
                  segment.approved_by_user ? 'border-green-300 bg-green-50' : 'border-gray-300'
                }`}
              >
                <div className="flex items-start gap-4">
                  {/* Thumbnail */}
                  {segment.thumbnail_url ? (
                    <img
                      src={segment.thumbnail_url}
                      alt={segment.title}
                      className="flex-shrink-0 w-32 h-24 object-cover rounded border border-gray-300 bg-gray-100"
                    />
                  ) : (
                    <div className="flex-shrink-0 w-32 h-24 bg-gray-200 rounded border border-gray-300 flex items-center justify-center">
                      <span className="text-xs text-gray-500">#{segment.segment_id.slice(-4)}</span>
                    </div>
                  )}

                  {/* Content */}
                  <div className="flex-grow">
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-semibold text-gray-800 mb-1">
                          {segment.title}
                        </h4>
                        <div className="flex items-center gap-3 text-sm text-gray-600 mb-2">
                          <span className="px-2 py-1 bg-gray-100 rounded text-xs">
                            🏷️ {getSegmentTypeLabel(segment.type)}
                          </span>
                          <span className={getConfidenceColor(segment.confidence)}>
                            {getConfidenceIcon(segment.confidence)} {(segment.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="text-sm text-gray-600">{segment.description}</p>
                      </div>

                      {/* Approval checkbox */}
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={segment.approved_by_user}
                          onChange={(e) => updateSegmentApproval(segment.segment_id, e.target.checked)}
                          className="w-5 h-5 text-blue-600 rounded"
                        />
                        <label className="text-sm text-gray-700">אשר</label>
                      </div>
                    </div>

                    {/* Expand button */}
                    <button
                      onClick={() => toggleSegmentExpand(segment.segment_id)}
                      className="mt-2 text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
                    >
                      {expandedSegments.has(segment.segment_id) ? (
                        <>פרטים מלאים <ChevronUp className="w-4 h-4" /></>
                      ) : (
                        <>הצג פרטים <ChevronDown className="w-4 h-4" /></>
                      )}
                    </button>

                    {/* Expanded details */}
                    {expandedSegments.has(segment.segment_id) && (
                      <div className="mt-4 p-4 bg-gray-50 rounded border border-gray-200 text-sm">
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <strong>Bounding Box:</strong>
                            <div className="text-xs text-gray-600 mt-1">
                              x: {segment.bounding_box.x.toFixed(1)}%, y: {segment.bounding_box.y.toFixed(1)}%<br />
                              w: {segment.bounding_box.width.toFixed(1)}%, h: {segment.bounding_box.height.toFixed(1)}%
                            </div>
                          </div>
                          {segment.llm_reasoning && (
                            <div>
                              <strong>הסבר GPT:</strong>
                              <div className="text-xs text-gray-600 mt-1">{segment.llm_reasoning}</div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Metadata Section */}
        {decomposition.metadata.project_name && (
          <div className="bg-white rounded-lg shadow-lg p-6 mt-6">
            <h3 className="text-lg font-semibold mb-4">📋 מטא-דאטה (מהמקרא)</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              {decomposition.metadata.project_name && (
                <div>
                  <strong className="text-gray-600">פרויקט:</strong>
                  <div>{decomposition.metadata.project_name}</div>
                </div>
              )}
              {decomposition.metadata.architect && (
                <div>
                  <strong className="text-gray-600">אדריכל:</strong>
                  <div>{decomposition.metadata.architect}</div>
                </div>
              )}
              {decomposition.metadata.date && (
                <div>
                  <strong className="text-gray-600">תאריך:</strong>
                  <div>{decomposition.metadata.date}</div>
                </div>
              )}
              {decomposition.metadata.plan_number && (
                <div>
                  <strong className="text-gray-600">מס' תוכנית:</strong>
                  <div>{decomposition.metadata.plan_number}</div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="bg-white rounded-lg shadow-lg p-6 mt-6">
          <div className="flex items-center justify-between">
            <button
              onClick={onReject}
              className="px-6 py-3 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 flex items-center gap-2"
            >
              <X className="w-5 h-5" />
              דחה והעלה מחדש
            </button>

            <div className="flex gap-4">
              <button
                onClick={loadDecomposition}
                className="px-6 py-3 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 flex items-center gap-2"
              >
                <RefreshCw className="w-5 h-5" />
                רענן
              </button>

              <button
                onClick={handleApprove}
                disabled={approvedCount === 0}
                className={`px-6 py-3 rounded-lg flex items-center gap-2 ${
                  approvedCount === 0
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-green-600 text-white hover:bg-green-700'
                }`}
              >
                <Check className="w-5 h-5" />
                אשר והמשך לבדיקות ({approvedCount} סגמנטים)
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DecompositionReview;

import { useState } from 'react';
import { Upload, CheckCircle, Sparkles, ArrowRight, Loader2, Zap, History } from 'lucide-react';
import type { PlanDecomposition } from './types';
import { DecompositionUpload } from './components/DecompositionUpload';
import { DecompositionReview } from './components/DecompositionReview';

// Workflow stages
type WorkflowStage = 'upload' | 'decomposition_review' | 'validation' | 'results' | 'history';

function App() {
  const [stage, setStage] = useState<WorkflowStage>('upload');
  const [decompositionId, setDecompositionId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string>('demo-project-001');
  const [validationProgress, setValidationProgress] = useState<{
    total: number;
    current: number;
    currentSegment: string;
  } | null>(null);
  const [validationResult, setValidationResult] = useState<any>(null);
  const [validationHistory, setValidationHistory] = useState<any[]>([]);
  
  console.log('🎨 App rendering, stage:', stage);
  
  // Handle decomposition complete
  const handleDecompositionComplete = (decompId: string) => {
    setDecompositionId(decompId);
    setStage('decomposition_review');
  };
  
  // Handle decomposition approved
  const handleApprovalComplete = async (approvedSegmentIds: string[]) => {
    setStage('validation');
    setValidationProgress({
      total: approvedSegmentIds.length,
      current: 0,
      currentSegment: 'מתחיל בדיקה...'
    });
    
    try {
      // Call new segment validation API
      const response = await fetch('/api/v1/segments/validate-segments', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          decomposition_id: decompositionId,
          approved_segment_ids: approvedSegmentIds,
        }),
      });
      
      if (!response.ok) {
        throw new Error('Validation failed');
      }
      
      const result = await response.json();
      console.log('Validation result:', result);
      console.log('Analyzed segments:', result.analyzed_segments);
      console.log('Analyzed segments count:', result.analyzed_segments?.length);
      
      // Fetch decomposition to get segment images
      const decompResponse = await fetch(`/api/v1/decomposition/${decompositionId}`);
      if (!decompResponse.ok) {
        throw new Error('Failed to fetch decomposition data');
      }
      const decompData = await decompResponse.json();
      console.log('Decomposition data:', decompData);
      console.log('Decomposition segments:', decompData.segments);
      
      // Merge analysis results with segment data (images, descriptions)
      const enrichedResult = {
        ...result,
        segments: result.analyzed_segments?.map((analysis: any) => {
          const segment = decompData.segments?.find(
            (s: any) => s.segment_id === analysis.segment_id
          );
          return {
            ...analysis,
            blob_url: segment?.blob_url,
            thumbnail_url: segment?.thumbnail_url,
            type: segment?.type,
            description: segment?.description
          };
        }) || []
      };
      
      console.log('Enriched result:', enrichedResult);
      console.log('Enriched segments:', enrichedResult.segments);
      console.log('Enriched segments count:', enrichedResult.segments?.length);
      
      setValidationResult(enrichedResult);
      
      // Show results
      setStage('results');
      
    } catch (error) {
      console.error('Validation error:', error);
      alert('שגיאה בבדיקת הסגמנטים');
      setStage('decomposition_review');
    }
  };
  
  // Handle rejection - go back to upload
  const handleRejection = () => {
    setStage('upload');
    setDecompositionId(null);
  };
  
  // Load validation history
  const loadHistory = async () => {
    try {
      const response = await fetch('/api/v1/segments/validations');
      if (!response.ok) {
        throw new Error('Failed to load history');
      }
      const data = await response.json();
      setValidationHistory(data.validations || []);
      setStage('history');
    } catch (error) {
      console.error('History load error:', error);
      alert('שגיאה בטעינת ההיסטוריה');
    }
  };
  
  // Load specific validation by ID
  const loadValidationById = async (validationId: string) => {
    try {
      const response = await fetch(`/api/v1/segments/validation/${validationId}`);
      if (!response.ok) {
        throw new Error('Failed to load validation');
      }
      const result = await response.json();
      
      // Fetch decomposition to get segment images
      const decompResponse = await fetch(`/api/v1/decomposition/${result.decomposition_id}`);
      if (!decompResponse.ok) {
        throw new Error('Failed to fetch decomposition data');
      }
      const decompData = await decompResponse.json();
      
      // Merge analysis results with segment data
      const enrichedResult = {
        ...result,
        segments: result.analyzed_segments?.map((analysis: any) => {
          const segment = decompData.segments?.find(
            (s: any) => s.segment_id === analysis.segment_id
          );
          return {
            ...analysis,
            blob_url: segment?.blob_url,
            thumbnail_url: segment?.thumbnail_url,
            type: segment?.type,
            description: segment?.description
          };
        }) || []
      };
      
      setValidationResult(enrichedResult);
      setStage('results');
      
    } catch (error) {
      console.error('Validation load error:', error);
      alert('שגיאה בטעינת הבדיקה');
    }
  };
  
  // Render stage indicator
  const renderStageIndicator = () => {
    const stages = [
      { id: 'upload', label: 'העלאה', icon: Upload },
      { id: 'decomposition_review', label: 'סקירת פירוק', icon: Sparkles },
      { id: 'validation', label: 'בדיקה', icon: Zap },
      { id: 'results', label: 'תוצאות', icon: CheckCircle }
    ];
    
    const currentIndex = stages.findIndex(s => s.id === stage);
    
    return (
      <div className="flex items-center justify-center gap-2 mb-8">
        {stages.map((s, index) => {
          const Icon = s.icon;
          const isActive = index === currentIndex;
          const isCompleted = index < currentIndex;
          
          return (
            <div key={s.id} className="flex items-center">
              <div className={`
                flex items-center gap-2 px-4 py-2 rounded-lg transition-all
                ${isActive ? 'bg-blue-500 text-white' : ''}
                ${isCompleted ? 'bg-green-500 text-white' : ''}
                ${!isActive && !isCompleted ? 'bg-gray-200 text-gray-500' : ''}
              `}>
                <Icon className="w-5 h-5" />
                <span className="text-sm font-medium">{s.label}</span>
              </div>
              {index < stages.length - 1 && (
                <ArrowRight className="w-5 h-5 mx-2 text-gray-400" />
              )}
            </div>
          );
        })}
      </div>
    );
  };
  
  // Render based on current stage
  const renderStageContent = () => {
    switch (stage) {
      case 'upload':
        return (
          <DecompositionUpload
            projectId={projectId}
            onProjectIdChange={setProjectId}
            onDecompositionComplete={handleDecompositionComplete}
          />
        );
      
      case 'decomposition_review':
        if (!decompositionId) return null;
        return (
          <DecompositionReview
            decompositionId={decompositionId}
            onApprove={handleApprovalComplete}
            onReject={handleRejection}
          />
        );
      
      case 'validation':
        return (
          <div className="bg-white rounded-xl shadow-lg p-8">
            <div className="text-center mb-8">
              <Loader2 className="w-16 h-16 mx-auto mb-4 text-blue-500 animate-spin" />
              <h2 className="text-2xl font-bold mb-2">מריץ בדיקות GPT-5.1</h2>
              <p className="text-gray-600">מנתח כל סגמנט באמצעות בינה מלאכותית</p>
            </div>
            
            {validationProgress && (
              <div className="max-w-2xl mx-auto">
                {/* Progress bar */}
                <div className="mb-6">
                  <div className="flex justify-between mb-2">
                    <span className="text-sm font-medium text-gray-700">
                      סגמנט {validationProgress.current} מתוך {validationProgress.total}
                    </span>
                    <span className="text-sm font-medium text-blue-600">
                      {Math.round((validationProgress.current / validationProgress.total) * 100)}%
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3">
                    <div 
                      className="bg-gradient-to-r from-blue-500 to-purple-500 h-3 rounded-full transition-all duration-500"
                      style={{ width: `${(validationProgress.current / validationProgress.total) * 100}%` }}
                    />
                  </div>
                </div>
                
                {/* Current status */}
                <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                  <div className="flex items-center gap-3">
                    <Sparkles className="w-5 h-5 text-blue-600 animate-pulse" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-blue-900">
                        {validationProgress.currentSegment}
                      </p>
                      <p className="text-xs text-blue-700 mt-1">
                        מחלץ מידע: טקסט, מידות, אלמנטים קונסטרוקטיביים, פלדת זיון, חומרים
                      </p>
                    </div>
                  </div>
                </div>
                
                {/* Processing steps indicator */}
                <div className="mt-6 grid grid-cols-5 gap-2">
                  {['טקסט', 'מידות', 'קירות', 'זיון', 'חומרים'].map((step, idx) => (
                    <div 
                      key={step}
                      className={`text-center p-2 rounded-lg text-xs font-medium transition-all ${
                        validationProgress.current > 0 
                          ? 'bg-green-100 text-green-700 border border-green-300' 
                          : 'bg-gray-100 text-gray-400'
                      }`}
                    >
                      {step}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      
      case 'history':
        return (
          <div className="bg-white rounded-xl shadow-lg p-8">
            <div className="mb-8">
              <h2 className="text-2xl font-bold mb-2">📋 היסטוריית בדיקות</h2>
              <p className="text-gray-600">כל הבדיקות שבוצעו במערכת</p>
            </div>
            
            {validationHistory.length === 0 ? (
              <div className="text-center py-12">
                <History className="w-16 h-16 mx-auto mb-4 text-gray-400" />
                <p className="text-gray-500">אין בדיקות קודמות</p>
              </div>
            ) : (
              <div className="space-y-4">
                {validationHistory.map((validation: any) => {
                  const date = new Date(validation.created_at).toLocaleDateString('he-IL', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                  });
                  
                  const passRate = validation.total_segments > 0 
                    ? Math.round((validation.passed / validation.total_segments) * 100)
                    : 0;
                  
                  return (
                    <div 
                      key={validation.id}
                      onClick={() => loadValidationById(validation.id)}
                      className="border rounded-lg p-4 hover:bg-blue-50 cursor-pointer transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <h3 className="font-bold">בדיקה מתאריך {date}</h3>
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                              passRate === 100 ? 'bg-green-100 text-green-700' :
                              passRate >= 80 ? 'bg-yellow-100 text-yellow-700' :
                              'bg-red-100 text-red-700'
                            }`}>
                              {passRate}% עבר
                            </span>
                          </div>
                          <div className="flex gap-4 text-sm text-gray-600">
                            <span>סגמנטים: {validation.total_segments}</span>
                            <span className="text-green-600">✓ {validation.passed}</span>
                            <span className="text-red-600">✗ {validation.failed}</span>
                            {validation.warnings > 0 && (
                              <span className="text-yellow-600">⚠ {validation.warnings}</span>
                            )}
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            מזהה: {validation.id}
                          </p>
                        </div>
                        <ArrowRight className="w-5 h-5 text-gray-400" />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            
            <div className="mt-8">
              <button
                onClick={() => setStage('upload')}
                className="w-full px-6 py-3 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
              >
                חזור לבדיקה חדשה
              </button>
            </div>
          </div>
        );
      
      case 'results':
        return (
          <div className="bg-white rounded-xl shadow-lg p-8">
            <div className="text-center mb-8">
              <CheckCircle className="w-16 h-16 mx-auto mb-4 text-green-500" />
              <h2 className="text-2xl font-bold mb-2">הבדיקות הושלמו!</h2>
              <p className="text-gray-600">ניתוח GPT-5.1 הושלם בהצלחה</p>
            </div>
            
            {validationResult && (
              <div className="max-w-4xl mx-auto">
                {/* Summary stats */}
                <div className="grid grid-cols-3 gap-4 mb-8">
                  <div className="bg-blue-50 rounded-lg p-4 border border-blue-200 text-center">
                    <div className="text-3xl font-bold text-blue-600">
                      {validationResult.total_segments}
                    </div>
                    <div className="text-sm text-gray-600 mt-1">סגמנטים נותחו</div>
                  </div>
                  <div className="bg-green-50 rounded-lg p-4 border border-green-200 text-center">
                    <div className="text-3xl font-bold text-green-600">
                      {validationResult.passed || 0}
                    </div>
                    <div className="text-sm text-gray-600 mt-1">הושלמו בהצלחה</div>
                  </div>
                  <div className="bg-yellow-50 rounded-lg p-4 border border-yellow-200 text-center">
                    <div className="text-3xl font-bold text-yellow-600">
                      {validationResult.warnings || 0}
                    </div>
                    <div className="text-sm text-gray-600 mt-1">אזהרות</div>
                  </div>
                </div>
                
                {/* Coverage Report */}
                {validationResult.coverage && (
                  <div className="mb-8">
                    <h3 className="text-xl font-bold mb-4">כיסוי דרישות ממ"ד</h3>
                    
                    {/* Coverage Statistics */}
                    <div className="bg-gradient-to-r from-purple-50 to-blue-50 rounded-lg p-6 border border-purple-200 mb-6">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                        <div className="bg-white rounded-lg p-3 text-center shadow-sm">
                          <div className="text-2xl font-bold text-purple-600">
                            {validationResult.coverage.statistics.coverage_percentage}%
                          </div>
                          <div className="text-xs text-gray-600 mt-1">כיסוי דרישות</div>
                        </div>
                        <div className="bg-white rounded-lg p-3 text-center shadow-sm">
                          <div className="text-2xl font-bold text-green-600">
                            {validationResult.coverage.statistics.passed}
                          </div>
                          <div className="text-xs text-gray-600 mt-1">עברו בדיקה</div>
                        </div>
                        <div className="bg-white rounded-lg p-3 text-center shadow-sm">
                          <div className="text-2xl font-bold text-red-600">
                            {validationResult.coverage.statistics.failed}
                          </div>
                          <div className="text-xs text-gray-600 mt-1">נכשלו</div>
                        </div>
                        <div className="bg-white rounded-lg p-3 text-center shadow-sm">
                          <div className="text-2xl font-bold text-gray-500">
                            {validationResult.coverage.statistics.not_checked}
                          </div>
                          <div className="text-xs text-gray-600 mt-1">לא נבדקו</div>
                        </div>
                      </div>
                      
                      {/* Progress bar */}
                      <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                        <div 
                          className="bg-gradient-to-r from-green-500 to-green-400 h-full transition-all duration-500"
                          style={{ width: `${validationResult.coverage.statistics.coverage_percentage}%` }}
                        />
                      </div>
                      <p className="text-center text-sm text-gray-600 mt-2">
                        {validationResult.coverage.statistics.checked} מתוך {validationResult.coverage.statistics.total_requirements} דרישות נבדקו
                      </p>
                    </div>
                    
                    {/* Requirements by Category */}
                    <div className="space-y-4 mb-6">
                      {Object.entries(validationResult.coverage.by_category || {}).map(([category, requirements]: [string, any]) => (
                        <div key={category} className="border border-gray-200 rounded-lg overflow-hidden">
                          <div className="bg-gray-100 px-4 py-3 border-b border-gray-200">
                            <h4 className="font-bold text-gray-800">{category}</h4>
                          </div>
                          <div className="divide-y divide-gray-200">
                            {requirements.map((req: any) => (
                              <div 
                                key={req.requirement_id}
                                className={`px-4 py-3 ${
                                  req.status === 'passed' ? 'bg-green-50' :
                                  req.status === 'failed' ? 'bg-red-50' :
                                  'bg-gray-50'
                                }`}
                              >
                                <div className="flex items-start gap-3">
                                  <div className="flex-shrink-0 mt-0.5">
                                    {req.status === 'passed' && <span className="text-green-600 text-xl">✅</span>}
                                    {req.status === 'failed' && <span className="text-red-600 text-xl">❌</span>}
                                    {req.status === 'not_checked' && <span className="text-gray-400 text-xl">⚠️</span>}
                                  </div>
                                  <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-1">
                                      <span className="font-mono text-sm font-bold text-gray-700">
                                        {req.requirement_id}
                                      </span>
                                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                                        req.severity === 'critical' ? 'bg-red-100 text-red-700' :
                                        req.severity === 'error' ? 'bg-orange-100 text-orange-700' :
                                        'bg-yellow-100 text-yellow-700'
                                      }`}>
                                        {req.severity}
                                      </span>
                                    </div>
                                    <p className="text-sm text-gray-700 mb-1">{req.description}</p>
                                    {req.segments_checked.length > 0 && (
                                      <p className="text-xs text-gray-500">
                                        נבדק בסגמנטים: {req.segments_checked.join(', ')}
                                      </p>
                                    )}
                                    {req.status === 'failed' && req.violations.length > 0 && (
                                      <div className="mt-2 text-xs text-red-700">
                                        <strong>הפרות:</strong>
                                        <ul className="list-disc list-inside mt-1">
                                          {req.violations.map((v: any, i: number) => (
                                            <li key={i}>{v.description}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                    
                    {/* Missing Segments */}
                    {validationResult.coverage.missing_segments_needed && 
                     validationResult.coverage.missing_segments_needed.length > 0 && (
                      <div className="bg-yellow-50 rounded-lg p-6 border border-yellow-200">
                        <h4 className="font-bold text-yellow-900 mb-3 flex items-center gap-2">
                          <span className="text-xl">📋</span>
                          נדרש להוספה להשלמת הבדיקה
                        </h4>
                        <div className="space-y-2">
                          {validationResult.coverage.missing_segments_needed.map((missing: any, i: number) => (
                            <div 
                              key={i}
                              className="bg-white rounded p-3 border border-yellow-300"
                            >
                              <div className="flex items-start gap-2">
                                <span className="font-mono text-sm font-bold text-yellow-700">
                                  {missing.requirement_id}
                                </span>
                                <div className="flex-1">
                                  <p className="text-sm text-gray-700 font-medium">
                                    {missing.description}
                                  </p>
                                  <p className="text-xs text-gray-600 mt-1">
                                    <strong>דרוש:</strong> {missing.needed_segment_type}
                                  </p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
                
                {/* Validation ID */}
                <div className="bg-gray-50 rounded-lg p-4 mb-6">
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">מזהה בדיקה:</span>
                    <span className="ml-2 font-mono text-xs">{validationResult.validation_id}</span>
                  </p>
                </div>
                
                {/* Info message */}
                <div className="bg-purple-50 rounded-lg p-4 border border-purple-200 mb-6">
                  <div className="flex items-start gap-3">
                    <Sparkles className="w-5 h-5 text-purple-600 mt-0.5" />
                    <div className="flex-1 text-sm text-purple-900">
                      <p className="font-medium mb-1">GPT-5.1 חילץ מידע מכל סגמנט:</p>
                      <ul className="list-disc list-inside space-y-1 text-purple-700">
                        <li>כל הטקסטים (עברית ואנגלית)</li>
                        <li>מידות ומדידות עם יחידות</li>
                        <li>אלמנטים קונסטרוקטיביים (קירות, דלתות, חלונות)</li>
                        <li>פרטי זיון (קוטר, מרווחים, כיוון)</li>
                        <li>חומרים (בטון, פלדה)</li>
                        <li>הערות ואנוטציות</li>
                      </ul>
                      <p className="mt-3 text-xs">
                        <span className="font-medium">שלב הבא:</span> יישום כללי תקן ממ"ד (Part 4) להפקת תוצאות pass/fail
                      </p>
                    </div>
                  </div>
                </div>
                
                {/* Detailed segment analysis */}
                {validationResult.segments && validationResult.segments.length > 0 && (
                  <div className="mb-6">
                    <h3 className="text-lg font-bold mb-4">ניתוח מפורט לפי סגמנט</h3>
                    <div className="space-y-6">
                      {validationResult.segments.map((segment: any, idx: number) => (
                        <div 
                          key={segment.segment_id}
                          className="border border-gray-200 rounded-lg p-4 bg-gray-50"
                        >
                          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            {/* Segment image - smaller column */}
                            <div className="md:col-span-1">
                              <div className="bg-white rounded-lg p-2 border border-gray-300 max-w-[200px]">
                                <img 
                                  src={segment.thumbnail_url || segment.blob_url} 
                                  alt={`סגמנט ${idx + 1}`}
                                  className="w-full h-auto rounded object-contain max-h-48"
                                />
                              </div>
                              <div className="mt-2 text-sm">
                                <p className="font-medium text-gray-700">
                                  {segment.type || 'סגמנט'} {idx + 1}
                                </p>
                                <p className="text-xs text-gray-500">
                                  {segment.description || 'אין תיאור'}
                                </p>
                              </div>
                            </div>
                            
                            {/* Analysis results - larger column */}
                            <div className="md:col-span-3 space-y-3">
                              <div className="flex items-center gap-2 mb-2">
                                <Sparkles className="w-4 h-4 text-blue-500" />
                                <h4 className="font-medium text-gray-900">ניתוח וסיווג הסגמנט</h4>
                              </div>
                              
                              {/* Segment Classification (Part 3) */}
                              {segment.analysis_data?.classification && (
                                <div className="bg-blue-50 rounded-lg p-3 border border-blue-200 mb-3">
                                  <h5 className="text-sm font-semibold text-blue-900 mb-2">🏷️ סיווג</h5>
                                  <div className="text-sm space-y-1">
                                    <p className="text-blue-800">
                                      <strong>קטגוריה:</strong> {segment.analysis_data.classification.primary_category}
                                    </p>
                                    <p className="text-blue-700 text-xs">
                                      {segment.analysis_data.classification.description}
                                    </p>
                                    {segment.analysis_data.classification.relevant_requirements?.length > 0 && (
                                      <p className="text-blue-700 text-xs mt-2">
                                        <strong>דרישות רלוונטיות:</strong>{' '}
                                        {segment.analysis_data.classification.relevant_requirements.join(', ')}
                                      </p>
                                    )}
                                  </div>
                                </div>
                              )}
                              
                              {/* Validation results (Part 4) */}
                              {segment.validation && (
                                <div className="mt-3 pt-3 border-t border-gray-200">
                                  <div className="flex items-center gap-2 mb-2">
                                    {segment.validation.passed ? (
                                      <CheckCircle className="w-4 h-4 text-green-500" />
                                    ) : (
                                      <span className="w-4 h-4 text-red-500">❌</span>
                                    )}
                                    <h5 className="font-medium text-gray-900 text-sm">
                                      תוצאות בדיקה: {segment.validation.passed ? 'תקין ✓' : 'נמצאו ליקויים'}
                                    </h5>
                                  </div>
                                  
                                  {/* Violation counts */}
                                  {segment.validation.total_violations > 0 && (
                                    <div className="grid grid-cols-3 gap-2 mb-2">
                                      {segment.validation.critical_count > 0 && (
                                        <div className="bg-red-50 rounded px-2 py-1 text-center border border-red-200">
                                          <div className="text-lg font-bold text-red-600">{segment.validation.critical_count}</div>
                                          <div className="text-xs text-red-700">קריטי</div>
                                        </div>
                                      )}
                                      {segment.validation.error_count > 0 && (
                                        <div className="bg-orange-50 rounded px-2 py-1 text-center border border-orange-200">
                                          <div className="text-lg font-bold text-orange-600">{segment.validation.error_count}</div>
                                          <div className="text-xs text-orange-700">שגיאות</div>
                                        </div>
                                      )}
                                      {segment.validation.warning_count > 0 && (
                                        <div className="bg-yellow-50 rounded px-2 py-1 text-center border border-yellow-200">
                                          <div className="text-lg font-bold text-yellow-600">{segment.validation.warning_count}</div>
                                          <div className="text-xs text-yellow-700">אזהרות</div>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                  
                                  {/* Violations list */}
                                  {segment.validation.violations && segment.validation.violations.length > 0 && (
                                    <div className="space-y-1 max-h-40 overflow-y-auto">
                                      {segment.validation.violations.map((violation: any, i: number) => (
                                        <div 
                                          key={i}
                                          className={`rounded p-2 text-xs border ${
                                            violation.severity === 'critical' 
                                              ? 'bg-red-50 border-red-300 text-red-900' 
                                              : violation.severity === 'error'
                                              ? 'bg-orange-50 border-orange-300 text-orange-900'
                                              : 'bg-yellow-50 border-yellow-300 text-yellow-900'
                                          }`}
                                        >
                                          <div className="font-medium mb-1">
                                            {violation.severity === 'critical' && '🔴'} 
                                            {violation.severity === 'error' && '⚠️'} 
                                            {violation.severity === 'warning' && '💡'} 
                                            {' '}{violation.description}
                                          </div>
                                          <div className="text-xs opacity-90">
                                            <div><strong>נדרש:</strong> {violation.requirement}</div>
                                            <div><strong>נמצא:</strong> {violation.found}</div>
                                            {violation.location && (
                                              <div><strong>מיקום:</strong> {violation.location}</div>
                                            )}
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                  
                                  {segment.validation.passed && segment.validation.total_violations === 0 && (
                                    <div className="bg-green-50 rounded p-2 border border-green-200 text-xs text-green-800">
                                      ✅ כל הבדיקות עברו בהצלחה - הסגמנט עומד בתקן ממ"ד
                                    </div>
                                  )}
                                </div>
                              )}
                              
                              {segment.status === 'analyzed' && segment.analysis_data && (
                                <div className="space-y-2 text-sm mt-3 pt-3 border-t border-gray-200">
                                  <p className="text-xs font-medium text-gray-700 mb-2">📊 נתונים שחולצו מהתוכנית:</p>
                                  
                                  {/* Text items */}
                                  {segment.analysis_data.text_items && segment.analysis_data.text_items.length > 0 && (
                                    <div className="bg-white rounded p-2 border border-blue-100">
                                      <p className="font-medium text-blue-900 mb-1">📝 טקסטים ({segment.analysis_data.text_items.length})</p>
                                      <div className="text-xs text-gray-600 max-h-20 overflow-y-auto">
                                        {segment.analysis_data.text_items.slice(0, 5).map((item: any, i: number) => (
                                          <div key={i}>• {item.text}</div>
                                        ))}
                                        {segment.analysis_data.text_items.length > 5 && (
                                          <div className="text-gray-400">...ועוד {segment.analysis_data.text_items.length - 5}</div>
                                        )}
                                      </div>
                                    </div>
                                  )}
                                  
                                  {/* Dimensions */}
                                  {segment.analysis_data.dimensions && segment.analysis_data.dimensions.length > 0 && (
                                    <div className="bg-white rounded p-2 border border-green-100">
                                      <p className="font-medium text-green-900 mb-1">📏 מידות ({segment.analysis_data.dimensions.length})</p>
                                      <div className="text-xs text-gray-600 max-h-20 overflow-y-auto">
                                        {segment.analysis_data.dimensions.slice(0, 5).map((dim: any, i: number) => (
                                          <div key={i}>• {dim.value}{dim.unit} - {dim.element}</div>
                                        ))}
                                        {segment.analysis_data.dimensions.length > 5 && (
                                          <div className="text-gray-400">...ועוד {segment.analysis_data.dimensions.length - 5}</div>
                                        )}
                                      </div>
                                    </div>
                                  )}
                                  
                                  {/* Structural elements */}
                                  {segment.analysis_data.structural_elements && segment.analysis_data.structural_elements.length > 0 && (
                                    <div className="bg-white rounded p-2 border border-purple-100">
                                      <p className="font-medium text-purple-900 mb-1">🏗️ אלמנטים ({segment.analysis_data.structural_elements.length})</p>
                                      <div className="text-xs text-gray-600 max-h-20 overflow-y-auto">
                                        {segment.analysis_data.structural_elements.slice(0, 5).map((elem: any, i: number) => (
                                          <div key={i}>• {elem.type} - {elem.thickness || elem.dimensions || 'N/A'}</div>
                                        ))}
                                        {segment.analysis_data.structural_elements.length > 5 && (
                                          <div className="text-gray-400">...ועוד {segment.analysis_data.structural_elements.length - 5}</div>
                                        )}
                                      </div>
                                    </div>
                                  )}
                                  
                                  {/* Rebar details */}
                                  {segment.analysis_data.rebar_details && segment.analysis_data.rebar_details.length > 0 && (
                                    <div className="bg-white rounded p-2 border border-orange-100">
                                      <p className="font-medium text-orange-900 mb-1">🔩 זיון ({segment.analysis_data.rebar_details.length})</p>
                                      <div className="text-xs text-gray-600 max-h-20 overflow-y-auto">
                                        {segment.analysis_data.rebar_details.slice(0, 3).map((rebar: any, i: number) => (
                                          <div key={i}>• Ø{rebar.diameter} @ {rebar.spacing}</div>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                  
                                  {/* Summary */}
                                  {segment.analysis_data.summary && (
                                    <div className="bg-blue-50 rounded p-2 border border-blue-200">
                                      <p className="font-medium text-blue-900 text-xs mb-1">סיכום:</p>
                                      <p className="text-xs text-gray-700">
                                        {segment.analysis_data.summary.primary_function || 'לא זמין'}
                                      </p>
                                    </div>
                                  )}
                                </div>
                              )}
                              
                              {segment.status === 'error' && (
                                <div className="bg-red-50 rounded p-3 border border-red-200">
                                  <p className="text-sm text-red-800">
                                    ❌ שגיאה בניתוח: {segment.error}
                                  </p>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            
            <div className="flex gap-4 justify-center">
              <button
                onClick={loadHistory}
                className="px-6 py-3 bg-purple-100 text-purple-700 rounded-lg hover:bg-purple-200 transition-colors flex items-center gap-2"
              >
                <History className="w-5 h-5" />
                היסטוריה
              </button>
              <button
                onClick={() => {
                  setStage('upload');
                  setDecompositionId(null);
                  setValidationResult(null);
                  setValidationProgress(null);
                }}
                className="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
              >
                בדיקה חדשה
              </button>
            </div>
          </div>
        );
      
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 via-blue-50 to-indigo-100" dir="rtl" style={{ minHeight: '100vh', background: 'linear-gradient(to bottom right, #faf5ff, #eff6ff, #e0e7ff)' }}>
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8 relative">
          {/* History button - top right */}
          {stage !== 'history' && (
            <button
              onClick={loadHistory}
              className="absolute top-0 left-0 flex items-center gap-2 px-4 py-2 bg-purple-100 text-purple-700 rounded-lg hover:bg-purple-200 transition-colors"
            >
              <History className="w-5 h-5" />
              <span className="font-medium">היסטוריה</span>
            </button>
          )}
          
          <div className="flex items-center justify-center gap-3 mb-4">
            <Sparkles className="w-12 h-12 text-purple-600" />
            <h1 className="text-5xl font-black bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent" style={{ color: '#7c3aed' }}>
              בודק ממ"ד GPT-5.1
            </h1>
          </div>
          <p className="text-xl text-gray-600 font-medium">
            מערכת אינטליגנטית לבדיקת תוכניות אדריכליות של ממ"ד
          </p>
        </div>
        
        {/* Stage Indicator */}
        {stage !== 'history' && renderStageIndicator()}
        
        {/* Main Content */}
        <div className="max-w-6xl mx-auto">
          {renderStageContent()}
        </div>
      </div>
    </div>
  );
}

export default App;

import { useState } from 'react';
import { 
  CheckCircle2, 
  Sparkles, 
  Loader2, 
  History, 
  FileText,
  AlertCircle,
  TrendingUp,
  Shield,
  BookOpen,
  Plus
} from 'lucide-react';
import { DecompositionUpload } from './components/DecompositionUpload';
import { DecompositionReview } from './components/DecompositionReview';
import { RequirementItem } from './components/RequirementItem';
import { RequirementsModal } from './components/RequirementsModal';
import { Button, Card, StatCard, Badge, ProgressBar, EmptyState, FloatingActionButton } from './components/ui';
import { StepIndicator } from './components/ValidationComponents';

type WorkflowStage = 'upload' | 'decomposition_review' | 'validation' | 'results' | 'history';

// Helper function to translate English descriptions to Hebrew
const translateDescription = (description: string): string => {
  if (!description) return '';
  
  const translations: Record<string, string> = {
    // Segment types
    'floor plan': 'תוכנית קומה',
    'section': 'חתך',
    'detail': 'פרט',
    'elevation': 'חזית',
    'reinforcement': 'חיזוק',
    'schedule': 'לוח זיון',
    'showing': 'מציג',
    
    // Descriptors
    'narrow': 'צר',
    'tall': 'גבוה',
    'rectangular': 'מלבני',
    'small': 'קטן',
    'lower': 'תחתון',
    'upper': 'עליון',
    
    // Features
    'dimensions': 'מידות',
    'text': 'טקסט',
    'highlight': 'הדגשה',
    'cyan': 'כחול בהיר',
    'internal': 'פנימי',
    'room': 'חדר',
    'layout': 'פריסה',
    
    // Connectors
    'with': 'עם',
    'and': 'ו',
  };
  
  let translated = description.toLowerCase();
  
  // First handle exact phrase matches for better context
  const phrases: Record<string, string> = {
    'small lower detail showing reinforcement schedule': 'פרט קטן תחתון מציג לוח זיון',
    'reinforcement schedule': 'לוח זיון',
    'floor plan with': 'תוכנית קומה עם',
    'rectangular detail': 'פרט מלבני',
  };
  
  Object.entries(phrases).forEach(([eng, heb]) => {
    if (translated.includes(eng.toLowerCase())) {
      translated = translated.replace(eng.toLowerCase(), heb);
    }
  });
  
  // Then handle individual words
  Object.entries(translations).forEach(([eng, heb]) => {
    const regex = new RegExp(`\\b${eng}\\b`, 'gi');
    translated = translated.replace(regex, heb);
  });
  
  // Capitalize first letter
  return translated.charAt(0).toUpperCase() + translated.slice(1);
};

// Helper to translate category names
const translateCategory = (category: string): string => {
  const categories: Record<string, string> = {
    'floor_plan': 'תוכנית קומה',
    'section': 'חתך',
    'detail': 'פרט',
    'elevation': 'חזית',
    'rebar_details': 'פרטי חיזוק',
    'room_layout': 'פריסת חדר',
    'structural_detail': 'פרט קונסטרוקטיבי',
    'unknown': 'לא ידוע',
  };
  
  return categories[category.toLowerCase()] || category;
};

// Helper to translate segment types
const translateType = (type: string): string => {
  const types: Record<string, string> = {
    'floor_plan': 'תוכנית קומה',
    'section': 'חתך',
    'detail': 'פרט חיזוק',
    'elevation': 'חזית',
    'legend': 'מקרא',
    'table': 'טבלה',
    'unknown': 'לא ידוע',
  };
  
  return types[type?.toLowerCase()] || type || 'לא ידוע';
};

function App() {
  const [stage, setStage] = useState<WorkflowStage>('upload');
  const [decompositionId, setDecompositionId] = useState<string | null>(null);
  const [projectId] = useState<string>('demo-project-001');
  const [validationProgress, setValidationProgress] = useState<{
    total: number;
    current: number;
    currentSegment: string;
  } | null>(null);
  const [validationResult, setValidationResult] = useState<any>(null);
  const [validationHistory, setValidationHistory] = useState<any[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [showRequirementsModal, setShowRequirementsModal] = useState(false);
  
  const handleDecompositionComplete = (decompId: string) => {
    setDecompositionId(decompId);
    setStage('decomposition_review');
  };
  
  const handleApprovalComplete = async (approvedSegmentIds: string[]) => {
    setStage('validation');
    setValidationProgress({
      total: approvedSegmentIds.length,
      current: 0,
      currentSegment: 'מתחיל בדיקה...'
    });
    
    try {
      const response = await fetch('/api/v1/segments/validate-segments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decomposition_id: decompositionId,
          approved_segment_ids: approvedSegmentIds,
        }),
      });
      
      if (!response.ok) throw new Error('Validation failed');
      
      const result = await response.json();
      
      const decompResponse = await fetch(`/api/v1/decomposition/${decompositionId}`);
      if (!decompResponse.ok) throw new Error('Failed to fetch decomposition data');
      const decompData = await decompResponse.json();
      
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
      console.error('Validation error:', error);
      alert('שגיאה בבדיקת הסגמנטים');
      setStage('decomposition_review');
    }
  };
  
  const loadHistory = async () => {
    try {
      const response = await fetch('/api/v1/segments/validations');
      if (!response.ok) throw new Error('Failed to load history');
      const data = await response.json();
      const latest = (data.validations || []).slice(0, 10);
      setValidationHistory(latest);
      setStage('history');
    } catch (error) {
      console.error('History error:', error);
      alert('שגיאה בטעינת היסטוריה');
    }
  };
  
  const loadValidationResults = async (validationId: string) => {
    console.log('Loading validation:', validationId);
    try {
      setIsLoadingHistory(true);
      
      // Load the validation results
      const response = await fetch(`/api/v1/segments/validation/${validationId}`);
      console.log('Validation response status:', response.status);
      
      if (!response.ok) throw new Error('Failed to load validation');
      
      const result = await response.json();
      console.log('Validation result:', result);
      
      // Enrich with segment data if decomposition_id exists
      if (result.decomposition_id) {
        const decompResponse = await fetch(`/api/v1/decomposition/${result.decomposition_id}`);
        if (decompResponse.ok) {
          const decompData = await decompResponse.json();
          
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
          setDecompositionId(result.decomposition_id);
        } else {
          setValidationResult(result);
        }
      } else {
        setValidationResult(result);
      }
      
      setStage('results');
    } catch (error) {
      console.error('Load validation error:', error);
      alert('שגיאה בטעינת תוצאות הבדיקה');
    } finally {
      setIsLoadingHistory(false);
    }
  };
  
  const resetWorkflow = () => {
    setStage('upload');
    setDecompositionId(null);
    setValidationResult(null);
    setValidationProgress(null);
  };

  const steps = [
    { number: 1, title: 'העלאה', description: 'העלאת קובץ התכנית' },
    { number: 2, title: 'סגמנטציה', description: 'זיהוי חלקי התכנית' },
    { number: 3, title: 'אישור', description: 'בחירת סגמנטים' },
    { number: 4, title: 'בדיקה', description: 'וולידציה מול תקנים' },
  ];

  const currentStepNumber = 
    stage === 'upload' ? 1 :
    stage === 'decomposition_review' ? 3 :
    stage === 'validation' ? 4 :
    stage === 'results' ? 4 : 1;

  return (
    <div className="min-h-screen bg-background text-text-primary font-sans antialiased" dir="rtl">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center shadow-sm">
                <Shield className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-text-primary tracking-tight">בדיקת ממ״ד</h1>
                <p className="text-sm text-text-muted">מערכת וולידציה אוטומטית</p>
              </div>
            </div>
            
            {stage !== 'history' && (
              <Button 
                variant="ghost" 
                size="sm"
                icon={<History className="w-4 h-4" />}
                onClick={loadHistory}
              >
                היסטוריה
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-12">
        {/* Step Indicator - Show only in workflow stages */}
        {stage !== 'history' && (
          <StepIndicator currentStep={currentStepNumber} steps={steps} />
        )}

        {/* Upload Stage */}
        {stage === 'upload' && (
          <div className="grid gap-8 lg:grid-cols-3 items-start">
            <div className="lg:col-span-2 space-y-6">
              <Card padding="lg" className="shadow-lg shadow-primary/5 border-border">
                <DecompositionUpload 
                  projectId={projectId}
                  onDecompositionComplete={handleDecompositionComplete}
                />
              </Card>

              <Card padding="md" className="bg-background border-dashed border-border">
                <div className="flex flex-wrap items-center gap-4">
                  <div className="rounded-lg bg-white px-4 py-3 shadow-sm border border-border">
                    <p className="text-xs text-text-muted font-medium mb-1">שלבי עבודה</p>
                    <p className="font-semibold text-text-primary">העלאה → אישור → בדיקה → תוצאות</p>
                  </div>
                  <div className="text-sm text-text-muted leading-relaxed max-w-xl">
                    שמור על סדר עבודה: העלה קובץ, אשר סגמנטים, הרץ בדיקות וקבל דוח מפורט עם כיסוי תקנים.
                  </div>
                </div>
              </Card>
            </div>

            <div className="space-y-4">
              <Card padding="md" className="bg-white/80 backdrop-blur border-border">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <p className="text-sm text-text-muted font-medium">תמיכה מלאה</p>
                    <p className="text-lg font-semibold text-text-primary">מוכנים להתחיל</p>
                  </div>
                  <Shield className="w-6 h-6 text-primary" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg bg-primary/5 border border-primary/10 p-3">
                    <p className="text-xs text-text-muted font-medium">תקנים</p>
                    <p className="font-semibold text-text-primary">16</p>
                  </div>
                  <div className="rounded-lg bg-background border border-border p-3">
                    <p className="text-xs text-text-muted font-medium">קבצים נתמכים</p>
                    <p className="font-semibold text-text-primary">PDF · DWF · PNG</p>
                  </div>
                </div>
              </Card>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-4">
                <Card padding="md" className="text-left hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <Sparkles className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-text-primary">AI מתקדם</p>
                      <p className="text-xs text-text-muted mt-1">GPT-5.1 Reasoning</p>
                    </div>
                  </div>
                </Card>
                <div 
                  className="cursor-pointer"
                  onClick={() => {
                    console.log('Opening requirements modal...');
                    setShowRequirementsModal(true);
                  }}
                >
                  <Card 
                    padding="md" 
                    className="text-left hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start gap-4">
                      <div className="w-10 h-10 rounded-lg bg-success/10 flex items-center justify-center flex-shrink-0">
                        <BookOpen className="w-5 h-5 text-success" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-text-primary">66 דרישות</p>
                        <p className="text-xs text-text-muted mt-1">כל תקני ממ"ד</p>
                      </div>
                    </div>
                  </Card>
                </div>
                <Card padding="md" className="text-left hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <TrendingUp className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-text-primary">דוח מפורט</p>
                      <p className="text-xs text-text-muted mt-1">כיסוי דרישות</p>
                    </div>
                  </div>
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* Decomposition Review Stage */}
        {stage === 'decomposition_review' && decompositionId && (
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-10">
              <h2 className="text-3xl font-bold text-text-primary mb-3 tracking-tight">
                בחר סגמנטים לבדיקה
              </h2>
              <p className="text-text-muted text-lg max-w-2xl mx-auto">
                המערכת זיהתה את החלקים הבאים בתכנית. אשר את הסגמנטים שברצונך לבדוק
              </p>
            </div>
            
            <DecompositionReview 
              decompositionId={decompositionId}
              onApprove={handleApprovalComplete}
              onReject={() => setStage('upload')}
            />
            
            <div className="mt-10 text-center">
              <Button 
                variant="ghost" 
                onClick={resetWorkflow}
              >
                חזור להעלאה
              </Button>
            </div>
          </div>
        )}

        {/* Validation Progress Stage */}
        {stage === 'validation' && validationProgress && (
          <div className="max-w-2xl mx-auto">
            <Card padding="lg" className="shadow-lg">
              <div className="text-center mb-10">
                <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-6">
                  <Loader2 className="w-10 h-10 text-primary animate-spin" />
                </div>
                <h2 className="text-2xl font-bold text-text-primary mb-2">
                  מריץ בדיקות...
                </h2>
                <p className="text-text-muted">
                  {validationProgress.currentSegment}
                </p>
              </div>
              
              <div className="space-y-4 max-w-md mx-auto">
                <ProgressBar 
                  value={validationProgress.current} 
                  max={validationProgress.total}
                  color="violet"
                  size="lg"
                  showLabel
                />
                <p className="text-sm text-center text-text-muted">
                  {validationProgress.current} מתוך {validationProgress.total} סגמנטים
                </p>
              </div>
            </Card>
          </div>
        )}

        {/* Results Stage */}
        {stage === 'results' && validationResult && (
          <div className="max-w-7xl mx-auto space-y-10">
            {/* Success Header */}
            <Card padding="lg" className="bg-gradient-to-r from-success/5 via-white to-primary/5 border-border shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
                <div className="flex items-center gap-5">
                  <div className="w-16 h-16 bg-success/10 rounded-2xl flex items-center justify-center border border-success/20">
                    <CheckCircle2 className="w-8 h-8 text-success" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold text-text-primary mb-1">הבדיקות הושלמו!</h2>
                    <p className="text-text-muted">ניתוח GPT-5.1 הושלם בהצלחה</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Badge variant="success">עברו {validationResult.passed || 0} בדיקות</Badge>
                  <Badge variant="info">{validationResult.total_segments} סגמנטים נותחו</Badge>
                  <Badge variant="warning">{validationResult.warnings || 0} אזהרות</Badge>
                </div>
              </div>
            </Card>

            <div className="grid gap-8 lg:grid-cols-3">
              <div className="lg:col-span-2 space-y-6">
                {/* Analyzed Segments Section */}
                {validationResult.segments && validationResult.segments.length > 0 && (
                  <Card padding="lg" className="shadow-md border-border">
                    <h3 className="text-xl font-bold text-text-primary mb-6">
                      סגמנטים שנותחו ({validationResult.segments.length})
                    </h3>
                    
                    <div className="space-y-6">
                      {validationResult.segments.map((segment: any, idx: number) => {
                        const analysis = segment.analysis_data || {};
                        const classification = analysis.classification || {};
                        const validation = segment.validation || {};
                        
                        // Determine segment status
                        const hasRelevantRequirements = classification.relevant_requirements && classification.relevant_requirements.length > 0;
                        const isNotApplicable = segment.status === 'analyzed' && !hasRelevantRequirements;
                        const isSuccess = segment.status === 'analyzed' && validation.passed && hasRelevantRequirements;
                        const isError = segment.status === 'error';
                        
                        return (
                          <div 
                            key={segment.segment_id || idx} 
                            className={`border rounded-xl overflow-hidden ${
                              isSuccess ? 'border-success/30' : 
                              isError ? 'border-error/30' :
                              isNotApplicable ? 'border-blue-200' :
                              'border-border'
                            }`}
                          >
                            {/* Segment Header */}
                            <div className={`px-5 py-4 border-b flex items-start gap-4 ${
                              isSuccess ? 'bg-success/5 border-success/20' :
                              isError ? 'bg-error/5 border-error/20' :
                              isNotApplicable ? 'bg-blue-50 border-blue-200' :
                              'bg-gray-50 border-border'
                            }`}>
                              {/* Thumbnail */}
                              {segment.thumbnail_url && (
                                <img 
                                  src={segment.thumbnail_url} 
                                  alt={`Segment ${idx + 1}`}
                                  className="w-24 h-24 object-cover rounded-lg border border-border shadow-sm"
                                />
                              )}
                              
                              <div className="flex-1">
                                <div className="flex items-start justify-between gap-3 mb-2">
                                  <div>
                                    <h4 className="font-semibold text-text-primary text-lg">
                                      {translateType(segment.type)}
                                    </h4>
                                    <p className="text-sm text-text-muted mt-1">
                                      {translateDescription(segment.description || segment.type)}
                                    </p>
                                  </div>
                                  
                                  {isSuccess && (
                                    <Badge variant="success">
                                      <CheckCircle2 className="w-4 h-4" />
                                      <span className="mr-1">עבר</span>
                                    </Badge>
                                  )}
                                  {isNotApplicable && (
                                    <Badge variant="neutral">
                                      <span className="mr-1">לא רלוונטי</span>
                                    </Badge>
                                  )}
                                  {isError && (
                                    <Badge variant="error">
                                      <AlertCircle className="w-4 h-4" />
                                      <span className="mr-1">שגיאה</span>
                                    </Badge>
                                  )}
                                  {!isSuccess && !isError && !isNotApplicable && (
                                    <Badge variant="warning">בדיקה</Badge>
                                  )}
                                </div>
                                
                                {/* Classification Info */}
                                {classification.primary_category && (
                                  <div className="mt-3 flex flex-wrap gap-2 items-center">
                                    <span className="text-xs text-text-muted">קטגוריה:</span>
                                    <Badge variant="neutral" size="sm">
                                      {translateCategory(classification.primary_category)}
                                    </Badge>
                                    {classification.relevant_requirements && classification.relevant_requirements.length > 0 ? (
                                      <span className="text-xs text-text-muted">
                                        • {classification.relevant_requirements.length} דרישות רלוונטיות
                                      </span>
                                    ) : (
                                      <span className="text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
                                        • 0 דרישות רלוונטיות (סגמנט מידע)
                                      </span>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                            
                            {/* Analysis Details */}
                            {segment.status === 'analyzed' && (
                              <div className="p-5 space-y-4">
                                {/* Relevant Requirements Checked */}
                                {classification.relevant_requirements && classification.relevant_requirements.length > 0 && (
                                  <div>
                                    <h5 className="text-sm font-semibold text-text-primary mb-3">
                                      דרישות שנבדקו:
                                    </h5>
                                    <div className="flex flex-wrap gap-2">
                                      {classification.relevant_requirements.map((reqId: string) => (
                                        <Badge key={reqId} variant="info" size="sm">
                                          {reqId}
                                        </Badge>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                
                                {/* Validation Results */}
                                {validation.violations && validation.violations.length > 0 && (
                                  <div>
                                    <h5 className="text-sm font-semibold text-error mb-3">
                                      בעיות שנמצאו ({validation.violations.length}):
                                    </h5>
                                    <div className="space-y-2">
                                      {validation.violations.map((violation: any, vIdx: number) => (
                                        <div 
                                          key={vIdx}
                                          className="bg-error/5 border border-error/20 rounded-lg p-3 text-sm"
                                        >
                                          <div className="flex items-start gap-2">
                                            <Badge variant="error" size="sm">{violation.rule_id}</Badge>
                                            <div className="flex-1">
                                              <p className="text-text-primary font-medium">
                                                {violation.description}
                                              </p>
                                              {violation.message && (
                                                <p className="text-text-muted text-xs mt-1">
                                                  {violation.message}
                                                </p>
                                              )}
                                            </div>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                
                                {/* Success Message with Details */}
                                {validation.passed && (!validation.violations || validation.violations.length === 0) && (
                                  <div className="space-y-3">
                                    {/* No relevant requirements case */}
                                    {(!classification.relevant_requirements || classification.relevant_requirements.length === 0) ? (
                                      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                                        <div className="flex items-start gap-3">
                                          <div className="w-5 h-5 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                            <span className="text-blue-600 text-xs font-bold">ℹ</span>
                                          </div>
                                          <div>
                                            <h5 className="text-sm font-semibold text-blue-900 mb-1">
                                              סגמנט זה לא נבדק
                                            </h5>
                                            <p className="text-xs text-blue-700 mb-2">
                                              סגמנט מסוג <span className="font-semibold">"{translateType(segment.type)}"</span>{' '}
                                              ({translateDescription(segment.description || segment.type)}) 
                                              אינו כולל דרישות בדיקה ספציפיות במערכת הנוכחית.
                                            </p>
                                            <p className="text-xs text-blue-600">
                                              <span className="font-semibold">הסבר:</span> פרטי חיזוק ופרטים טכניים הם מידע עזר לבונה 
                                              ואינם חלק מדרישות האישור של ממ"ד. הבדיקה מתמקדת בסגמנטים כמו: תכנית קומה, חתך, 
                                              חזית - שבהם נבדקות דרישות קירות, פתחים, מידות וכו'.
                                            </p>
                                          </div>
                                        </div>
                                      </div>
                                    ) : (
                                      /* Has relevant requirements - show success */
                                      <div className="bg-success/5 border border-success/20 rounded-lg p-4">
                                        <div className="flex items-start gap-3 mb-3">
                                          <CheckCircle2 className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
                                          <div>
                                            <h5 className="text-sm font-semibold text-success mb-1">
                                              כל הדרישות הרלוונטיות עברו בהצלחה!
                                            </h5>
                                            <p className="text-xs text-text-muted">
                                              הסגמנט עמד בכל {classification.relevant_requirements.length} הדרישות שנבדקו עבור הקטגוריה שלו
                                            </p>
                                          </div>
                                        </div>
                                        
                                        {/* Show what was checked */}
                                        <div className="bg-white rounded-lg p-3 border border-success/10">
                                          <p className="text-xs text-text-muted font-semibold mb-2">
                                            ✓ הדרישות שנבדקו ועברו:
                                          </p>
                                          <div className="flex flex-wrap gap-2">
                                            {classification.relevant_requirements.map((reqId: string) => {
                                              // Get requirement description from coverage report
                                              const requirement = validationResult.coverage?.requirements?.[reqId];
                                              return (
                                                <div 
                                                  key={reqId}
                                                  className="flex items-start gap-2 text-xs bg-success/5 border border-success/20 rounded-md px-2 py-1"
                                                  title={requirement?.description}
                                                >
                                                  <Badge variant="success" size="sm" className="text-xs">
                                                    {reqId}
                                                  </Badge>
                                                  {requirement && (
                                                    <span className="text-text-muted max-w-xs truncate">
                                                      {requirement.description}
                                                    </span>
                                                  )}
                                                </div>
                                              );
                                            })}
                                          </div>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                )}
                                
                                {/* LLM Reasoning */}
                                {analysis.reasoning && (
                                  <details className="text-sm">
                                    <summary className="cursor-pointer text-text-muted hover:text-text-primary font-medium">
                                      הסבר GPT-5.1
                                    </summary>
                                    <p className="mt-2 text-text-muted bg-background rounded-lg p-3 border border-border">
                                      {analysis.reasoning}
                                    </p>
                                  </details>
                                )}
                              </div>
                            )}
                            
                            {/* Error State */}
                            {segment.status === 'error' && (
                              <div className="p-5 bg-error/5 text-error text-sm">
                                <AlertCircle className="w-4 h-4 inline ml-2" />
                                שגיאה בניתוח הסגמנט: {segment.error || 'לא ידוע'}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </Card>
                )}
                
                {/* Coverage Report */}
                {validationResult.coverage && (
                  <Card padding="lg" className="shadow-md border-border">
                    <h3 className="text-xl font-bold text-text-primary mb-6">
                      כיסוי דרישות ממ״ד
                    </h3>
                    
                    {/* Coverage Statistics */}
                    <div className="bg-background rounded-xl p-6 mb-8 border border-border">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                        <div className="bg-white rounded-lg p-4 shadow-sm border border-border text-center">
                          <div className="text-3xl font-bold text-primary">
                            {validationResult.coverage.statistics.coverage_percentage}%
                          </div>
                          <div className="text-xs text-text-muted mt-1 font-medium">כיסוי דרישות</div>
                        </div>
                        <div className="bg-white rounded-lg p-4 shadow-sm border border-border text-center">
                          <div className="text-3xl font-bold text-success">
                            {validationResult.coverage.statistics.passed}
                          </div>
                          <div className="text-xs text-text-muted mt-1 font-medium">עברו בדיקה</div>
                        </div>
                        <div className="bg-white rounded-lg p-4 shadow-sm border border-border text-center">
                          <div className="text-3xl font-bold text-error">
                            {validationResult.coverage.statistics.failed}
                          </div>
                          <div className="text-xs text-text-muted mt-1 font-medium">נכשלו</div>
                        </div>
                        <div className="bg-white rounded-lg p-4 shadow-sm border border-border text-center">
                          <div className="text-3xl font-bold text-text-muted">
                            {validationResult.coverage.statistics.not_checked}
                          </div>
                          <div className="text-xs text-text-muted mt-1 font-medium">לא נבדקו</div>
                        </div>
                      </div>
                      
                      <ProgressBar 
                        value={validationResult.coverage.statistics.coverage_percentage}
                        max={100}
                        color="violet"
                        size="lg"
                      />
                      <p className="text-center text-sm text-text-muted mt-3">
                        {validationResult.coverage.statistics.checked} מתוך {validationResult.coverage.statistics.total_requirements} דרישות נבדקו
                      </p>
                    </div>
                    
                    {/* Requirements by Category */}
                    <div className="space-y-4 mb-8">
                      <h4 className="text-lg font-semibold text-text-primary">דרישות לפי קטגוריה</h4>
                      {Object.entries(validationResult.coverage.by_category || {}).map(([category, requirements]: [string, any]) => (
                        <div key={category} className="border border-border rounded-xl overflow-hidden">
                          <div className="bg-gray-50 px-5 py-3 border-b border-border">
                            <h5 className="font-semibold text-text-primary">{category}</h5>
                          </div>
                          <div className="divide-y divide-border">
                            {requirements.map((req: any) => (
                              <RequirementItem key={req.requirement_id} req={req} />
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                    
                    {/* Missing Segments */}
                    {validationResult.coverage.missing_segments_needed?.length > 0 && (
                      <div className="bg-warning/5 rounded-xl p-6 border border-warning/20">
                        <div className="flex items-start gap-3 mb-4">
                          <AlertCircle className="w-5 h-5 text-warning mt-0.5" />
                          <div>
                            <h4 className="font-semibold text-warning mb-1">
                              נדרש להוספה להשלמת הבדיקה
                            </h4>
                            <p className="text-sm text-warning/80">
                              הדרישות הבאות לא נבדקו מכיוון שלא נמצאו סגמנטים רלוונטיים
                            </p>
                          </div>
                        </div>
                        <div className="space-y-3">
                          {validationResult.coverage.missing_segments_needed.map((missing: any, i: number) => (
                            <div 
                              key={i}
                              className="bg-white rounded-lg p-4 border border-warning/20 shadow-sm"
                            >
                              <div className="flex items-start gap-3">
                                <Badge variant="warning" size="sm">
                                  {missing.requirement_id}
                                </Badge>
                                <div className="flex-1">
                                  <p className="text-sm text-text-primary font-medium mb-1">
                                    {missing.description}
                                  </p>
                                  <p className="text-xs text-text-muted">
                                    <span className="font-semibold">דרוש:</span> {missing.needed_segment_type}
                                  </p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </Card>
                )}
              </div>

              <div className="space-y-4">
                <Card padding="md" className="space-y-4 border-border">
                  <h4 className="text-lg font-semibold text-text-primary">סטטוס כללי</h4>
                  <div className="grid grid-cols-1 gap-3">
                    <StatCard 
                      label="סגמנטים נותחו"
                      value={validationResult.total_segments}
                      icon={<FileText className="w-5 h-5" />}
                      color="blue"
                    />
                    <StatCard 
                      label="הושלמו בהצלחה"
                      value={validationResult.passed || 0}
                      icon={<CheckCircle2 className="w-5 h-5" />}
                      color="green"
                    />
                    <StatCard 
                      label="אזהרות"
                      value={validationResult.warnings || 0}
                      icon={<AlertCircle className="w-5 h-5" />}
                      color="amber"
                    />
                  </div>
                </Card>

                <Card padding="md" className="bg-background border-border">
                  <p className="text-sm text-text-muted">
                    <span className="font-semibold text-text-primary">מזהה בדיקה:</span>
                    <span className="ml-2 font-mono text-xs">{validationResult.validation_id}</span>
                  </p>
                </Card>

                <Card padding="md" className="space-y-3 border-border">
                  <h4 className="text-lg font-semibold text-text-primary">פעולות מהירות</h4>
                  <Button
                    variant="secondary"
                    size="md"
                    icon={<History className="w-5 h-5" />}
                    onClick={loadHistory}
                    fullWidth
                  >
                    היסטוריה
                  </Button>
                  <Button
                    variant="primary"
                    size="md"
                    icon={<Plus className="w-5 h-5" />}
                    onClick={resetWorkflow}
                    fullWidth
                  >
                    בדיקה חדשה
                  </Button>
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* History Stage */}
        {stage === 'history' && (
          <div className="max-w-6xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <div>
                <h2 className="text-3xl font-bold text-text-primary mb-2 tracking-tight">
                  היסטוריית בדיקות
                </h2>
                <p className="text-text-muted">
                  כל הבדיקות שבוצעו עד כה - לחץ על בדיקה כדי לראות את התוצאות
                </p>
              </div>
              <Button
                variant="primary"
                icon={<Plus className="w-5 h-5" />}
                onClick={resetWorkflow}
              >
                בדיקה חדשה
              </Button>
            </div>
            
            {isLoadingHistory && (
              <Card padding="lg" className="mb-6">
                <div className="flex items-center justify-center gap-3 text-primary">
                  <Loader2 className="w-6 h-6 animate-spin" />
                  <span className="font-medium">טוען תוצאות...</span>
                </div>
              </Card>
            )}
            
            {validationHistory.length === 0 ? (
              <Card padding="lg">
                <EmptyState
                  icon={<History className="w-8 h-8" />}
                  title="אין בדיקות קודמות"
                  description="התחל בדיקה חדשה כדי לראות אותה כאן"
                  action={{
                    label: 'התחל בדיקה',
                    onClick: resetWorkflow
                  }}
                />
              </Card>
            ) : (
              <div className="space-y-4">
                {validationHistory.map((validation: any) => (
                  <div
                    key={validation.id || validation.validation_id}
                    onClick={() => {
                      console.log('Card clicked! Validation ID:', validation.id);
                      loadValidationResults(validation.id);
                    }}
                    className="cursor-pointer"
                  >
                    <Card 
                      hover 
                      padding="md"
                      className="transition-all hover:shadow-lg hover:border-primary/30"
                    >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center">
                          <FileText className="w-6 h-6 text-primary" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-text-primary">
                            {validation.plan_name || 'תכנית ללא שם'}
                          </h3>
                          <p className="text-sm text-text-muted">
                            {new Date(validation.created_at).toLocaleDateString('he-IL', {
                              year: 'numeric',
                              month: 'long',
                              day: 'numeric'
                            })}
                          </p>
                          <p className="text-xs text-text-muted/60 font-mono">
                            ID: {validation.id?.substring(0, 12)}...
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge 
                          variant={
                            validation.status === 'pass' ? 'success' :
                            validation.status === 'fail' ? 'error' : 'warning'
                          }
                        >
                          {validation.status === 'pass' ? 'עבר' :
                           validation.status === 'fail' ? 'נכשל' : 'לבדיקה'}
                        </Badge>
                        <span className="text-sm text-text-muted">
                          {validation.total_segments || 0} סגמנטים
                        </span>
                      </div>
                    </div>
                  </Card>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Floating Action Button - Show in results stage */}
      {stage === 'results' && (
        <FloatingActionButton
          onClick={resetWorkflow}
          icon={<Plus className="w-6 h-6" />}
          label="בדיקה חדשה"
        />
      )}

      {/* Requirements Modal */}
      <RequirementsModal 
        isOpen={showRequirementsModal} 
        onClose={() => setShowRequirementsModal(false)} 
      />
    </div>
  );
}

export default App;
